from unittest.mock import patch

import pytest


# Mock cipher for testing
class MockCipher:
    def encrypt(self, data: bytes) -> bytes:
        return data

    def decrypt(self, data: bytes) -> bytes:
        return data


# Apply the mock cipher to all tests in this module
@pytest.fixture(autouse=True)
def mock_cipher():
    with patch("ada_backend.database.models.CIPHER", MockCipher()):
        yield
