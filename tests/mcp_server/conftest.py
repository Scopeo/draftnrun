import pytest


class FakeMCP:
    def __init__(self):
        self.tools = {}
        self.resources = {}

    def tool(self):
        def decorator(func):
            self.tools[func.__name__] = func
            return func

        return decorator

    def resource(self, uri, name=None, description=None):
        def decorator(func):
            self.resources[uri] = {"func": func, "name": name, "description": description}
            return func

        return decorator


@pytest.fixture
def fake_mcp():
    return FakeMCP()
