import threading
from typing import Any, Dict

from ada_ingestion_system.worker import base_worker
from ada_ingestion_system.worker.base_worker import BaseWorker, ProcessTaskOutcome


class DummyWorker(BaseWorker):
    def __init__(self, outcome: ProcessTaskOutcome | None = None, should_raise: bool = False):
        self.stream_name = "stream"
        self.max_concurrent = 1
        self.current_threads = 1
        self.lock = threading.Lock()
        self.worker_type = "dummy"
        self._outcome = outcome
        self._should_raise = should_raise
        self.dead_letter_calls = []
        self.dead_letter_hook_calls = []

    def get_required_fields(self) -> list[str]:
        return ["k"]

    def process_task(self, payload: Dict[str, Any]) -> ProcessTaskOutcome:
        if self._should_raise:
            raise RuntimeError("boom")
        return self._outcome or ProcessTaskOutcome.SUCCESS_ACK

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
    worker = DummyWorker(should_raise=True)
    monkeypatch.setattr(worker, "_get_delivery_count", lambda _: 1)
    monkeypatch.setattr(base_worker, "_MAX_DELIVERY_ATTEMPTS", 3)

    worker._process_and_ack({"k": "v"}, "1-0", {"data": "{}"})

    assert redis.acks == []
    assert worker.dead_letter_calls == []
