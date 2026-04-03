from ada_ingestion_system.worker.base_worker import ProcessTaskOutcome
from ada_ingestion_system.worker.webhook_worker import _classify_script_failure


def test_classify_script_failure_fatal_marker():
    outcome = _classify_script_failure("... WEBHOOK_FAILURE_CLASS=fatal error=bad payload ...")
    assert outcome == ProcessTaskOutcome.FAIL_FATAL_ACK


def test_classify_script_failure_defaults_retryable():
    outcome = _classify_script_failure("some random stderr without marker")
    assert outcome == ProcessTaskOutcome.FAIL_RETRY
