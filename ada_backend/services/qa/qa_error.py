from uuid import UUID
from typing import Optional


class CSVMissingColumnError(Exception):
    """Raised when required column is missing from CSV header."""

    def __init__(self, column: str, found_columns: list[str], required_columns: list[str]):
        self.column = column
        self.found_columns = found_columns
        self.required_columns = required_columns
        super().__init__(
            f"Required column '{column}' not found in CSV header. "
            f"Found columns: {found_columns}. Required columns: {required_columns}"
        )


class CSVInvalidJSONError(Exception):
    """Raised when input column contains invalid JSON."""

    def __init__(self, row_number: Optional[int] = None):
        super().__init__(f"Invalid JSON in 'input' column. Expected a JSON object at row {row_number}")


class CSVInvalidPositionError(Exception):
    """Raised when position column contains invalid integer."""

    def __init__(self, row_number: Optional[int] = None):
        super().__init__(
            f"Invalid integer in 'position' column at row {row_number}. "
            "Expected an integer greater than or equal to 1."
        )


class CSVNonUniquePositionError(Exception):
    """Raised when position column contains non-unique values."""

    def __init__(self, duplicate_positions: list[int]):
        super().__init__(
            f"Duplicate positions found in CSV import: {duplicate_positions}. "
            f"Positions may be duplicated within the CSV file or conflict with existing positions in the dataset."
        )


class CSVEmptyFileError(Exception):
    """Raised when CSV file is empty."""

    def __init__(self):
        super().__init__("CSV file is empty")


class CSVExportError(Exception):
    """Raised when CSV export fails."""

    def __init__(self, dataset_id: UUID, message: str):
        self.dataset_id = dataset_id
        super().__init__(f"Failed to export CSV for dataset {dataset_id}: {message}")


class UnknownEvaluationTypeError(Exception):
    def __init__(self, evaluation_type: str):
        self.evaluation_type = evaluation_type
        super().__init__(f"Unknown evaluation_type: {evaluation_type}")


class VersionOutputEmptyError(Exception):
    def __init__(self, version_output_id: UUID):
        self.version_output_id = version_output_id
        super().__init__(f"Version output {version_output_id} has no output to evaluate")


class QADuplicatePositionError(Exception):
    """Raised when duplicate positions are found in QA dataset entries."""

    def __init__(self, duplicate_positions: list[int]):
        self.duplicate_positions = duplicate_positions
        super().__init__(f"Duplicate positions found in QA dataset: {duplicate_positions}")


class QAPartialPositionError(Exception):
    """Raised when partial positioning is detected (some entries have position, some don't)."""

    def __init__(self):
        super().__init__("Partial positioning is not allowed. Either provide positions for all entries or none.")
