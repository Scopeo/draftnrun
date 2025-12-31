import datetime
import random

import pytest


# Get a random timestamps + random suffix to create/erase objects in snowflake
@pytest.fixture
def timestamp_with_random_suffix():
    return f"{datetime.datetime.now().strftime('%Y_%m_%d_%H_%M_%S')}_{random.randint(0, 100)}"
