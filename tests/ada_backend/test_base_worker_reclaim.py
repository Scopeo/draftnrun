"""Regression tests for BaseWorker._reclaim_pending.

Bug: xautoclaim(count=100) bumped delivery count for ALL pending messages,
but only max_concurrent (e.g. 2) were dispatched.  Messages that couldn't
get a slot had their count inflated without being processed, leading to
premature dead-lettering after a few worker restarts.

Fix: xautoclaim is now called with count=1 in a loop that stops when
there is no more worker capacity, so only dispatchable messages have
their delivery count incremented.
"""

import types
from unittest.mock import patch

import pytest

from ada_ingestion_system.worker.base_worker import BaseWorker

MODULE = "ada_ingestion_system.worker.base_worker"


class _ConcreteWorker:
    """Minimal concrete subclass of BaseWorker for testing."""

    def __init__(self, stream_name: str, max_concurrent: int):
        # Bypass __init__ side-effects (Redis, Sentry) — we only test _reclaim_pending.
        import threading

        self.stream_name = stream_name
        self.max_concurrent = max_concurrent
        self.current_threads = 0
        self.lock = threading.Lock()
        self.worker_type = "test"
        self.dispatched: list[str] = []
        self.dead_lettered: list[str] = []

    def _can_process(self) -> bool:
        with self.lock:
            return self.current_threads < self.max_concurrent

    def _dispatch(self, message_id, fields, consumer_name):
        self.dispatched.append(message_id)

        with self.lock:
            self.current_threads += 1

    def _dead_letter(self, message_id, fields, delivery_count, reason):
        self.dead_lettered.append(message_id)

    def _on_dead_letter(self, message_id, fields, reason=""):
        pass


@pytest.fixture()
def worker():
    return _ConcreteWorker(stream_name="test_stream", max_concurrent=2)


@patch(f"{MODULE}.redis_client")
def test_reclaim_only_claims_what_can_be_dispatched(mock_redis, worker):
    """When 5 messages are pending, only max_concurrent (2) should be
    reclaimed via xautoclaim.  The other 3 must NOT have their delivery
    count bumped."""

    mock_redis.xpending_range.return_value = []

    claimed_messages = [
        ("msg-1", {"data": "{}"}),
        ("msg-2", {"data": "{}"}),
        ("msg-3", {"data": "{}"}),
        ("msg-4", {"data": "{}"}),
        ("msg-5", {"data": "{}"}),
    ]
    call_count = 0

    def xautoclaim_side_effect(*args, **kwargs):
        nonlocal call_count
        if call_count < len(claimed_messages):
            msg = claimed_messages[call_count]
            call_count += 1
            return (f"{call_count}-0", [msg], [])
        return ("0-0", [], [])

    mock_redis.xautoclaim.side_effect = xautoclaim_side_effect

    BaseWorker._reclaim_pending(worker, "consumer-1")

    assert len(worker.dispatched) == 2
    assert worker.dispatched == ["msg-1", "msg-2"]
    assert mock_redis.xautoclaim.call_count == 2


@patch(f"{MODULE}.redis_client")
def test_reclaim_does_not_inflate_undispatched_messages(mock_redis, worker):
    """Verify that messages beyond worker capacity are never passed to
    xautoclaim at all (count=1 loop stops early)."""

    mock_redis.xpending_range.return_value = []

    messages = [("msg-1", {"data": "{}"}), ("msg-2", {"data": "{}"})]
    idx = 0

    def xautoclaim_side_effect(*args, **kwargs):
        nonlocal idx
        if idx < len(messages):
            msg = messages[idx]
            idx += 1
            return (f"{idx}-0", [msg], [])
        return ("0-0", [], [])

    mock_redis.xautoclaim.side_effect = xautoclaim_side_effect

    BaseWorker._reclaim_pending(worker, "consumer-1")

    assert mock_redis.xautoclaim.call_count == 2
    assert len(worker.dispatched) == 2


@patch(f"{MODULE}.redis_client")
def test_reclaim_dead_letters_poison_messages_before_claiming(mock_redis, worker):
    """Poison messages (delivery_count >= MAX) should be dead-lettered
    and excluded from xautoclaim dispatch."""

    mock_redis.xpending_range.return_value = [
        {"message_id": "poison-1", "times_delivered": 3, "time_since_delivered": 120_000},
        {"message_id": "ok-1", "times_delivered": 1, "time_since_delivered": 120_000},
    ]
    mock_redis.xrange.return_value = [("poison-1", {"data": "{}"})]

    call_idx = 0

    def xautoclaim_one_then_empty(*args, **kwargs):
        nonlocal call_idx
        call_idx += 1
        if call_idx == 1:
            return ("0-0", [("ok-1", {"data": "{}"})], [])
        return ("0-0", [], [])

    mock_redis.xautoclaim.side_effect = xautoclaim_one_then_empty

    BaseWorker._reclaim_pending(worker, "consumer-1")

    assert "poison-1" in worker.dead_lettered
    assert "ok-1" in worker.dispatched
    assert "poison-1" not in worker.dispatched


@patch(f"{MODULE}.redis_client")
def test_reclaim_skips_poison_ids_from_xautoclaim(mock_redis, worker):
    """If xautoclaim returns a message that was already dead-lettered
    in the poison scan, it should be skipped (not dispatched)."""

    mock_redis.xpending_range.return_value = [
        {"message_id": "poison-1", "times_delivered": 5, "time_since_delivered": 120_000},
    ]
    mock_redis.xrange.return_value = [("poison-1", {"data": "{}"})]

    call_idx = 0

    def xautoclaim_returns_poison_then_good(*args, **kwargs):
        nonlocal call_idx
        call_idx += 1
        if call_idx == 1:
            return ("next-0", [("poison-1", {"data": "{}"})], [])
        if call_idx == 2:
            return ("0-0", [("good-1", {"data": "{}"})], [])
        return ("0-0", [], [])

    mock_redis.xautoclaim.side_effect = xautoclaim_returns_poison_then_good

    BaseWorker._reclaim_pending(worker, "consumer-1")

    assert "poison-1" not in worker.dispatched
    assert "good-1" in worker.dispatched


@patch(f"{MODULE}.redis_client")
def test_reclaim_uses_returned_start_id_across_iterations(mock_redis, worker):
    """xautoclaim returns a cursor (start_id) that must be forwarded to the
    next call so the scan progresses through the PEL instead of restarting
    from '0-0' every time."""

    mock_redis.xpending_range.return_value = []

    def xautoclaim_side_effect(*args, **kwargs):
        start = kwargs.get("start_id", args[4] if len(args) > 4 else None)
        if start == "0-0":
            return ("cursor-after-first", [("msg-1", {"data": "{}"})], [])
        if start == "cursor-after-first":
            return ("cursor-after-second", [("msg-2", {"data": "{}"})], [])
        return ("0-0", [], [])

    mock_redis.xautoclaim.side_effect = xautoclaim_side_effect

    BaseWorker._reclaim_pending(worker, "consumer-1")

    assert worker.dispatched == ["msg-1", "msg-2"]
    calls = mock_redis.xautoclaim.call_args_list
    assert len(calls) >= 2
    assert calls[0].kwargs["start_id"] == "0-0"
    assert calls[1].kwargs["start_id"] == "cursor-after-first"


@patch(f"{MODULE}.redis_client")
def test_reclaim_continues_on_empty_batch_with_nonzero_cursor(mock_redis, worker):
    """When xautoclaim returns no messages but a non-'0-0' cursor, the loop
    must continue scanning from that cursor instead of breaking.  This
    happens when count=1 scans PEL entries that aren't idle enough."""

    mock_redis.xpending_range.return_value = []

    responses = [
        ("50-0", [], []),
        ("100-0", [("msg-1", {"data": "{}"})], []),
        ("150-0", [], []),
        ("0-0", [("msg-2", {"data": "{}"})], []),
    ]
    call_idx = 0

    def xautoclaim_side_effect(*args, **kwargs):
        nonlocal call_idx
        if call_idx < len(responses):
            result = responses[call_idx]
            call_idx += 1
            return result
        return ("0-0", [], [])

    mock_redis.xautoclaim.side_effect = xautoclaim_side_effect

    BaseWorker._reclaim_pending(worker, "consumer-1")

    assert worker.dispatched == ["msg-1", "msg-2"]
    assert mock_redis.xautoclaim.call_count == 4

    calls = mock_redis.xautoclaim.call_args_list
    assert calls[0].kwargs["start_id"] == "0-0"
    assert calls[1].kwargs["start_id"] == "50-0"
    assert calls[2].kwargs["start_id"] == "100-0"
    assert calls[3].kwargs["start_id"] == "150-0"


@patch(f"{MODULE}.redis_client")
def test_reclaim_handles_empty_pel(mock_redis, worker):
    """When the PEL is empty, _reclaim_pending should be a no-op."""

    mock_redis.xpending_range.return_value = []
    mock_redis.xautoclaim.return_value = ("0-0", [], [])

    BaseWorker._reclaim_pending(worker, "consumer-1")

    assert worker.dispatched == []
    assert worker.dead_lettered == []
    assert mock_redis.xautoclaim.call_count == 1


class _LoopBreak(BaseException):
    pass


@patch(f"{MODULE}.time")
@patch(f"{MODULE}.redis_client")
def test_run_skips_xreadgroup_when_reclaim_fills_capacity(mock_redis, mock_time, worker):
    """When the periodic reclaim inside run() fills every worker slot,
    run() must skip xreadgroup and go to the capacity-full sleep instead."""

    worker._consumer_name = lambda: "test-consumer"
    worker._RECLAIM_INTERVAL_S = 30
    worker._reclaim_pending = types.MethodType(BaseWorker._reclaim_pending, worker)

    mock_time.monotonic.side_effect = [0, 31]

    def _sleep(secs):
        if secs == 0.5:
            raise _LoopBreak()

    mock_time.sleep.side_effect = _sleep

    xautoclaim_idx = 0

    def xautoclaim_side_effect(*args, **kwargs):
        nonlocal xautoclaim_idx
        xautoclaim_idx += 1
        if xautoclaim_idx == 1:
            return ("0-0", [], [])
        if xautoclaim_idx == 2:
            return ("next-0", [("msg-1", {"data": "{}"})], [])
        if xautoclaim_idx == 3:
            return ("0-0", [("msg-2", {"data": "{}"})], [])
        return ("0-0", [], [])

    mock_redis.xpending_range.return_value = []
    mock_redis.xautoclaim.side_effect = xautoclaim_side_effect

    with pytest.raises(_LoopBreak):
        BaseWorker.run(worker)

    assert mock_redis.xreadgroup.call_count == 0
    assert len(worker.dispatched) == 2
