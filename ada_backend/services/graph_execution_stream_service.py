import asyncio
import json
import logging
import threading
from dataclasses import dataclass, field
from typing import AsyncGenerator
from uuid import UUID

from sqlalchemy.orm import Session

from ada_backend.database.models import Run, RunStatus
from ada_backend.utils.redis_client import get_redis_client

LOGGER = logging.getLogger(__name__)
PING_TIMEOUT_SECONDS = 25


@dataclass
class GraphExecutionSubscription:
    queue: asyncio.Queue = field(default_factory=asyncio.Queue)
    stop_event: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = field(default=None, init=False, repr=False)

    def stop(self):
        self.stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)


def get_running_runs(session: Session, project_id: UUID) -> list[dict]:
    runs = session.query(Run).filter(Run.project_id == project_id, Run.status == RunStatus.RUNNING).all()
    return [{"type": "run.active", "run_id": str(r.id), "graph_runner_id": None} for r in runs]


def _redis_subscriber_loop(
    project_id: UUID,
    queue: asyncio.Queue,
    loop: asyncio.AbstractEventLoop,
    stop_event: threading.Event,
    subscribed_event: threading.Event,
) -> None:
    client = get_redis_client()
    if not client:
        LOGGER.warning("Redis subscriber project_id=%s: no Redis client", project_id)
        subscribed_event.set()
        loop.call_soon_threadsafe(
            queue.put_nowait,
            json.dumps({"type": "error", "message": "Redis unavailable"}),
        )
        return
    pubsub = client.pubsub()
    channel = f"project-runs:{project_id}"
    pubsub.subscribe(channel)
    subscribed_event.set()
    try:
        while not stop_event.is_set():
            message = pubsub.get_message(timeout=0.5)
            if message and message.get("type") == "message":
                data = message.get("data")
                if data is not None:
                    loop.call_soon_threadsafe(queue.put_nowait, data)
    finally:
        try:
            pubsub.unsubscribe(channel)
            pubsub.close()
        except Exception as e:
            LOGGER.debug("PubSub cleanup for %s: %s", channel, e)


async def subscribe_to_project_stream(project_id: UUID) -> GraphExecutionSubscription | None:
    if not get_redis_client():
        return None

    sub = GraphExecutionSubscription()
    subscribed_event = threading.Event()
    loop = asyncio.get_event_loop()

    thread = threading.Thread(
        target=_redis_subscriber_loop,
        args=(project_id, sub.queue, loop, sub.stop_event, subscribed_event),
        daemon=False,
    )
    thread.start()
    sub._thread = thread

    await asyncio.get_event_loop().run_in_executor(None, subscribed_event.wait, 2.0)
    return sub


async def stream_events(queue: asyncio.Queue) -> AsyncGenerator[str, None]:
    while True:
        try:
            data = await asyncio.wait_for(queue.get(), timeout=PING_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            yield json.dumps({"type": "ping"})
            continue
        message = data if isinstance(data, str) else json.dumps(data)
        yield message
