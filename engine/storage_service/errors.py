class RowNotFoundError(Exception):
    """Raised when a row is not found in a database table."""

    def __init__(self, id_column_name: str, row_id: str, table_name: str):
        self.id_column_name = id_column_name
        self.row_id = row_id
        self.table_name = table_name
        super().__init__(f"Row with {id_column_name}='{row_id}' not found in table {table_name}")
