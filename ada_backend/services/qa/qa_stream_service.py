import asyncio
import json
import logging
import threading
from dataclasses import dataclass, field
from typing import AsyncGenerator
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database.models import QASession, RunStatus
from ada_backend.database.setup_db import get_db_session
from ada_backend.repositories.qa_session_repository import get_qa_session
from ada_backend.repositories.quality_assurance_repository import get_outputs_by_graph_runner
from ada_backend.utils.redis_client import get_redis_client

LOGGER = logging.getLogger(__name__)

TERMINAL_EVENT_TYPES = ("qa.completed", "qa.failed")
PING_TIMEOUT_SECONDS = 60


def _is_stream_terminal(data) -> bool:
    try:
        evt = json.loads(data) if isinstance(data, str) else data
        if isinstance(evt, dict):
            return evt.get("type") in TERMINAL_EVENT_TYPES or evt.get("fatal") is True
    except (json.JSONDecodeError, TypeError):
        pass
    return False


@dataclass
class QASubscription:
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    stop_event: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)

    def stop(self):
        self.stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)


def get_validated_qa_session(session: Session, session_id: UUID, project_id: UUID) -> QASession | None:
    qa_session = get_qa_session(session, session_id)
    if not qa_session or qa_session.project_id != project_id:
        return None
    return qa_session


def build_catchup_events(db_session: Session, qa_session: QASession) -> list[str]:
    if qa_session.status == RunStatus.PENDING:
        return []
    if not qa_session.graph_runner_id or not qa_session.dataset_id:
        return []
    outputs = get_outputs_by_graph_runner(db_session, qa_session.dataset_id, qa_session.graph_runner_id)
    events: list[str] = []
    for input_id, output in outputs:
        is_error = bool(output and output.startswith("Error: "))
        events.append(json.dumps({
            "type": "qa.entry.completed",
            "input_id": str(input_id),
            "output": output,
            "success": not is_error,
            "error": output if is_error else None,
        }))
    return events


def build_terminal_event(qa_session: QASession) -> str | None:
    if qa_session.status == RunStatus.COMPLETED:
        return json.dumps({
            "type": "qa.completed",
            "summary": {
                "total": qa_session.total,
                "passed": qa_session.passed,
                "failed": qa_session.failed,
                "success_rate": (qa_session.passed / qa_session.total * 100) if qa_session.total else 0.0,
            },
        })
    if qa_session.status == RunStatus.FAILED:
        return json.dumps({
            "type": "qa.failed",
            "error": qa_session.error or {"message": "Unknown error", "type": "UnknownError"},
        })
    return None


def reconstruct_session_replay(db_session: Session, qa_session: QASession) -> tuple[list[str], str | None]:
    catchup = build_catchup_events(db_session, qa_session)
    terminal = build_terminal_event(qa_session)
    return catchup, terminal


def _redis_subscriber_loop(
    session_id: UUID,
    queue: asyncio.Queue,
    loop: asyncio.AbstractEventLoop,
    stop_event: threading.Event,
    subscribed_event: threading.Event,
) -> None:
    client = get_redis_client()
    if not client:
        LOGGER.warning("Redis subscriber session_id=%s: no Redis client", session_id)
        subscribed_event.set()
        loop.call_soon_threadsafe(
            queue.put_nowait,
            json.dumps({"type": "error", "fatal": True, "message": "Redis unavailable"}),
        )
        return
    pubsub = client.pubsub()
    channel = f"qa:{session_id}"
    pubsub.subscribe(channel)
    subscribed_event.set()
    try:
        while not stop_event.is_set():
            message = pubsub.get_message(timeout=0.5)
            if message and message.get("type") == "message":
                data = message.get("data")
                if data is not None:
                    loop.call_soon_threadsafe(queue.put_nowait, data)
                    if _is_stream_terminal(data):
                        break
    finally:
        try:
            pubsub.unsubscribe(channel)
            pubsub.close()
        except Exception as e:
            LOGGER.debug("PubSub cleanup for %s: %s", channel, e)


async def subscribe_to_session_stream(session_id: UUID) -> QASubscription | None:
    if not get_redis_client():
        return None

    sub = QASubscription()
    subscribed_event = threading.Event()
    loop = asyncio.get_event_loop()

    thread = threading.Thread(
        target=_redis_subscriber_loop,
        args=(session_id, sub.queue, loop, sub.stop_event, subscribed_event),
        daemon=False,
    )
    thread.start()
    sub._thread = thread

    await asyncio.get_event_loop().run_in_executor(None, subscribed_event.wait, 2.0)

    with get_db_session() as fresh_session:
        fresh_qa_session = get_qa_session(fresh_session, session_id)
        if fresh_qa_session:
            for event in build_catchup_events(fresh_session, fresh_qa_session):
                sub.queue.put_nowait(event)
            terminal = build_terminal_event(fresh_qa_session)
            if terminal:
                sub.queue.put_nowait(terminal)

    return sub


def _extract_completed_input_id(data) -> str | None:
    try:
        evt = json.loads(data) if isinstance(data, str) else data
        if isinstance(evt, dict) and evt.get("type") == "qa.entry.completed":
            return evt.get("input_id")
    except (json.JSONDecodeError, TypeError):
        pass
    return None


async def stream_events(queue: asyncio.Queue) -> AsyncGenerator[str, None]:
    seen_completed: set[str] = set()
    while True:
        try:
            data = await asyncio.wait_for(queue.get(), timeout=PING_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            yield json.dumps({"type": "ping"})
            continue

        input_id = _extract_completed_input_id(data)
        if input_id:
            if input_id in seen_completed:
                continue
            seen_completed.add(input_id)

        message = data if isinstance(data, str) else json.dumps(data)
        yield message

        if _is_stream_terminal(data):
            return
