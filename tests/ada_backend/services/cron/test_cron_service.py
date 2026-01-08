"""Tests for cron service frequency validation."""

import pytest

from ada_backend.services.cron.constants import CRON_MIN_INTERVAL_MINUTES
from ada_backend.services.cron.errors import CronValidationError
from ada_backend.services.cron.service import _validate_maximum_frequency


class TestCronFrequencyValidation:
    """Test cron frequency validation safeguard."""

    def test_validate_below_minimum_rejected(self):
        test_interval = max(1, CRON_MIN_INTERVAL_MINUTES // 2)

        with pytest.raises(CronValidationError) as exc_info:
            _validate_maximum_frequency(f"*/{test_interval} * * * *")

        error_message = str(exc_info.value)
        assert "runs too frequently" in error_message
        assert f"{test_interval}.0 minutes" in error_message
        assert f"Minimum allowed interval is {CRON_MIN_INTERVAL_MINUTES} minutes" in error_message

    def test_validate_just_below_minimum_rejected(self):
        if CRON_MIN_INTERVAL_MINUTES > 1:
            test_interval = CRON_MIN_INTERVAL_MINUTES - 1

            with pytest.raises(CronValidationError) as exc_info:
                _validate_maximum_frequency(f"*/{test_interval} * * * *")

            assert "runs too frequently" in str(exc_info.value)

    def test_validate_at_minimum_accepted(self):
        _validate_maximum_frequency(f"*/{CRON_MIN_INTERVAL_MINUTES} * * * *")

    def test_validate_above_minimum_accepted(self):
        test_interval = CRON_MIN_INTERVAL_MINUTES * 2
        _validate_maximum_frequency(f"*/{test_interval} * * * *")

    def test_validate_common_intervals_accepted(self):
        if CRON_MIN_INTERVAL_MINUTES <= 60:
            _validate_maximum_frequency("0 * * * *")

        if CRON_MIN_INTERVAL_MINUTES <= 720:
            _validate_maximum_frequency("0 0,12 * * *")

        if CRON_MIN_INTERVAL_MINUTES <= 1440:
            _validate_maximum_frequency("0 0 * * *")
            _validate_maximum_frequency("0 9 * * 1-5")

    def test_validate_custom_min_interval(self):
        custom_interval = max(5, CRON_MIN_INTERVAL_MINUTES // 2)

        _validate_maximum_frequency(f"*/{custom_interval} * * * *", min_interval_minutes=custom_interval)

        with pytest.raises(CronValidationError):
            _validate_maximum_frequency(f"*/{custom_interval} * * * *", min_interval_minutes=custom_interval + 1)

    def test_validate_invalid_cron_expression(self):
        with pytest.raises(CronValidationError):
            _validate_maximum_frequency("invalid cron expression")

    def test_constant_is_used_by_default(self):
        if CRON_MIN_INTERVAL_MINUTES > 1:
            test_interval = CRON_MIN_INTERVAL_MINUTES - 1
            with pytest.raises(CronValidationError) as exc_info:
                _validate_maximum_frequency(f"*/{test_interval} * * * *")
            assert str(CRON_MIN_INTERVAL_MINUTES) in str(exc_info.value)

        _validate_maximum_frequency(f"*/{CRON_MIN_INTERVAL_MINUTES} * * * *")

        test_interval_above = CRON_MIN_INTERVAL_MINUTES + max(5, CRON_MIN_INTERVAL_MINUTES // 2)
        _validate_maximum_frequency(f"*/{test_interval_above} * * * *")
