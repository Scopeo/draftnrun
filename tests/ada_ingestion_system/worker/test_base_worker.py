import threading
from typing import Any, Dict

import redis

from ada_ingestion_system.worker import base_worker
from ada_ingestion_system.worker.base_worker import BaseWorker, ProcessTaskOutcome

_UNSET = object()


class DummyWorker(BaseWorker):
    def __init__(
        self,
        outcome: ProcessTaskOutcome = ProcessTaskOutcome.SUCCESS_ACK,
        should_raise: bool = False,
        return_raw: object = _UNSET,
    ):
        self.stream_name = "stream"
        self.max_concurrent = 1
        self.current_threads = 1
        self.lock = threading.Lock()
        self.worker_type = "dummy"
        self._outcome = outcome
        self._should_raise = should_raise
        self._return_raw = return_raw
        self.dead_letter_calls = []
        self.dead_letter_hook_calls = []

    def get_required_fields(self) -> list[str]:
        return ["k"]

    def process_task(self, payload: Dict[str, Any]) -> ProcessTaskOutcome:
        if self._should_raise:
            raise RuntimeError("boom")
        if self._return_raw is not _UNSET:
            return self._return_raw  # type: ignore[return-value]
        return self._outcome

    def _dead_letter(self, message_id: str, fields: Dict[str, str], delivery_count: int, reason: str) -> None:
        self.dead_letter_calls.append((message_id, fields, delivery_count, reason))

    def _on_dead_letter(self, message_id: str, fields: Dict[str, str], reason: str = "") -> None:
        self.dead_letter_hook_calls.append((message_id, fields, reason))


class DummyRedis:
    def __init__(self):
        self.acks = []

    def xack(self, stream_name, group_name, message_id):
        self.acks.append((stream_name, group_name, message_id))


def test_success_acks_once(monkeypatch):
    redis = DummyRedis()
    monkeypatch.setattr(base_worker, "redis_client", redis)
    worker = DummyWorker(outcome=ProcessTaskOutcome.SUCCESS_ACK)

    worker._process_and_ack({"k": "v"}, "1-0", {"data": "{}"})

    assert redis.acks == [("stream", base_worker.CONSUMER_GROUP, "1-0")]


def test_fatal_acks_once(monkeypatch):
    redis = DummyRedis()
    monkeypatch.setattr(base_worker, "redis_client", redis)
    worker = DummyWorker(outcome=ProcessTaskOutcome.FAIL_FATAL_ACK)

    worker._process_and_ack({"k": "v"}, "1-0", {"data": "{}"})

    assert redis.acks == [("stream", base_worker.CONSUMER_GROUP, "1-0")]


def test_retry_under_threshold_does_not_ack(monkeypatch):
    redis = DummyRedis()
    monkeypatch.setattr(base_worker, "redis_client", redis)
    monkeypatch.setattr(base_worker.time, "sleep", lambda _: None)
    worker = DummyWorker(outcome=ProcessTaskOutcome.FAIL_RETRY)
    monkeypatch.setattr(worker, "_get_delivery_count", lambda _: 1)
    monkeypatch.setattr(base_worker, "_MAX_DELIVERY_ATTEMPTS", 3)

    worker._process_and_ack({"k": "v"}, "1-0", {"data": "{}"})

    assert redis.acks == []
    assert worker.dead_letter_calls == []


def test_retry_at_threshold_dead_letters_and_calls_hook(monkeypatch):
    redis = DummyRedis()
    monkeypatch.setattr(base_worker, "redis_client", redis)
    worker = DummyWorker(outcome=ProcessTaskOutcome.FAIL_RETRY)
    monkeypatch.setattr(worker, "_get_delivery_count", lambda _: 3)
    monkeypatch.setattr(base_worker, "_MAX_DELIVERY_ATTEMPTS", 3)
    fields = {"data": "{}"}

    worker._process_and_ack({"k": "v"}, "1-0", fields)

    assert worker.dead_letter_calls
    assert worker.dead_letter_hook_calls


def test_exception_defaults_to_retry_without_ack(monkeypatch):
    redis = DummyRedis()
    monkeypatch.setattr(base_worker, "redis_client", redis)
    monkeypatch.setattr(base_worker.time, "sleep", lambda _: None)
    worker = DummyWorker(should_raise=True)
    monkeypatch.setattr(worker, "_get_delivery_count", lambda _: 1)
    monkeypatch.setattr(base_worker, "_MAX_DELIVERY_ATTEMPTS", 3)

    worker._process_and_ack({"k": "v"}, "1-0", {"data": "{}"})

    assert redis.acks == []
    assert worker.dead_letter_calls == []


def test_none_return_triggers_retry_not_silent_ack(monkeypatch):
    """Returning None from process_task must not silently ACK the message."""
    redis = DummyRedis()
    monkeypatch.setattr(base_worker, "redis_client", redis)
    monkeypatch.setattr(base_worker.time, "sleep", lambda _: None)
    worker = DummyWorker(return_raw=None)
    monkeypatch.setattr(worker, "_get_delivery_count", lambda _: 1)
    monkeypatch.setattr(base_worker, "_MAX_DELIVERY_ATTEMPTS", 3)

    worker._process_and_ack({"k": "v"}, "1-0", {"data": "{}"})

    assert redis.acks == []
    assert worker.dead_letter_calls == []


def test_non_outcome_return_triggers_retry(monkeypatch):
    """Returning an arbitrary value from process_task must trigger retry."""
    redis = DummyRedis()
    monkeypatch.setattr(base_worker, "redis_client", redis)
    monkeypatch.setattr(base_worker.time, "sleep", lambda _: None)
    worker = DummyWorker(return_raw="not_an_outcome")
    monkeypatch.setattr(worker, "_get_delivery_count", lambda _: 1)
    monkeypatch.setattr(base_worker, "_MAX_DELIVERY_ATTEMPTS", 3)

    worker._process_and_ack({"k": "v"}, "1-0", {"data": "{}"})

    assert redis.acks == []
    assert worker.dead_letter_calls == []


def test_get_delivery_count_returns_max_on_redis_error(monkeypatch):
    class _FakeRedis:
        def xpending_range(self, *_args, **_kwargs):
            raise redis.exceptions.ConnectionError("connection lost")

    monkeypatch.setattr(base_worker, "redis_client", _FakeRedis())
    monkeypatch.setattr(base_worker, "_MAX_DELIVERY_ATTEMPTS", 5)
    worker = DummyWorker()

    assert worker._get_delivery_count("1-0") == 5


class _BreakLoop(BaseException):
    pass


def test_run_calls_reclaim_pending_periodically(monkeypatch):
    redis = DummyRedis()
    monkeypatch.setattr(base_worker, "redis_client", redis)
    monkeypatch.setattr(base_worker, "_PENDING_IDLE_THRESHOLD_MS", 10_000)

    worker = DummyWorker()
    worker.current_threads = 0
    monkeypatch.setattr(worker, "_consumer_name", lambda: "test-consumer")

    reclaim_calls: list[str] = []

    def fake_reclaim(consumer_name: str) -> None:
        reclaim_calls.append(consumer_name)
        if len(reclaim_calls) >= 2:
            raise _BreakLoop

    monkeypatch.setattr(worker, "_reclaim_pending", fake_reclaim)

    clock = [0.0]

    def fake_monotonic() -> float:
        val = clock[0]
        clock[0] += 11.0
        return val

    monkeypatch.setattr(base_worker.time, "monotonic", fake_monotonic)

    try:
        worker.run()
    except _BreakLoop:
        pass

    assert len(reclaim_calls) == 2
    assert all(c == "test-consumer" for c in reclaim_calls)
