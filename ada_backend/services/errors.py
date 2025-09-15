from uuid import UUID


class CategoryNotFound(Exception):
    def __init__(self, category_id: UUID):
        self.category_id = category_id
        super().__init__(f"Category not found: {category_id}")


class DuplicateCategoryName(Exception):
    def __init__(self, name: str):
        self.name = name
        super().__init__(f"Category with name '{name}' already exists")


class InvalidCategoryUpdate(Exception):
    def __init__(self):
        super().__init__("At least one field (name or description) must be provided for update")
