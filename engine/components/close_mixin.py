class CloseMixin:
    # TODO: Remove this mixin once all components are migrated to Component.
    async def close(self) -> None:
        pass
