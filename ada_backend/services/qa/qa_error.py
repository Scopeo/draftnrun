from typing import Optional
from uuid import UUID

from ada_backend.services.errors import ServiceError


class QAServiceError(ServiceError):
    status_code = 400


class CSVMissingDatasetColumnError(QAServiceError):
    """Raised when required column is missing from CSV header."""

    def __init__(self, column: str, found_columns: list[str], required_columns: list[str]):
        self.column = column
        self.found_columns = found_columns
        self.required_columns = required_columns
        super().__init__(
            f"Required column '{column}' not found in CSV header. "
            f"Found columns: {found_columns}. Required columns: {required_columns}"
        )


class CSVInvalidJSONError(QAServiceError):
    """Raised when input column contains invalid JSON."""

    def __init__(self, row_number: Optional[int] = None):
        super().__init__(f"Invalid JSON in 'input' column. Expected a JSON object at row {row_number}")


class CSVInvalidPositionError(QAServiceError):
    """Raised when position column contains invalid integer."""

    def __init__(self, row_number: Optional[int] = None):
        super().__init__(
            f"Invalid integer in 'position' column at row {row_number}. "
            "Expected an integer greater than or equal to 1."
        )


class CSVNonUniquePositionError(QAServiceError):
    """Raised when position column contains non-unique values."""

    def __init__(self, duplicate_positions: list[int]):
        super().__init__(
            f"Duplicate positions found in CSV import: {duplicate_positions}. "
            f"Positions may be duplicated within the CSV file or conflict with existing positions in the dataset."
        )


class CSVEmptyFileError(QAServiceError):
    """Raised when CSV file is empty."""

    def __init__(self):
        super().__init__("CSV file is empty")


class CSVExportError(QAServiceError):
    """Raised when CSV export fails."""

    status_code = 404

    def __init__(self, dataset_id: UUID, message: str):
        self.dataset_id = dataset_id
        super().__init__(f"Failed to export CSV for dataset {dataset_id}: {message}")


class UnknownEvaluationTypeError(QAServiceError):
    def __init__(self, evaluation_type: str):
        self.evaluation_type = evaluation_type
        super().__init__(f"Unknown evaluation_type: {evaluation_type}")


class VersionOutputEmptyError(QAServiceError):
    def __init__(self, version_output_id: UUID):
        self.version_output_id = version_output_id
        super().__init__(f"Version output {version_output_id} has no output to evaluate")


class QADuplicatePositionError(QAServiceError):
    """Raised when duplicate positions are found in QA dataset entries."""

    def __init__(self, duplicate_positions: list[int]):
        self.duplicate_positions = duplicate_positions
        super().__init__(f"Duplicate positions found in QA dataset: {duplicate_positions}")


class QAPartialPositionError(QAServiceError):
    """Raised when partial positioning is detected (some entries have position, some don't)."""

    def __init__(self):
        super().__init__("Partial positioning is not allowed. Either provide positions for all entries or none.")


class GroundtruthMissingError(QAServiceError):
    """Raised when groundtruth is missing for deterministic evaluation."""

    def __init__(self):
        super().__init__("No groundtruth provided for comparison")


class InvalidFormatError(QAServiceError):
    """Raised when a field format is invalid for evaluation."""

    def __init__(self, field_name: str, expected_format: str = "JSON"):
        super().__init__(f"Invalid {expected_format} format in {field_name}")


class QADatasetNotInProjectError(QAServiceError):
    """Raised when a dataset is not linked to the given project"""

    def __init__(self, project_id: UUID, dataset_id: UUID):
        self.project_id = project_id
        self.dataset_id = dataset_id
        super().__init__(f"Dataset {dataset_id} not found in project {project_id}")


class QADatasetNotInOrganizationError(QAServiceError):
    """Raised when a dataset does not belong to the given organization"""

    def __init__(self, organization_id: UUID, dataset_id: UUID):
        self.organization_id = organization_id
        self.dataset_id = dataset_id
        super().__init__(f"Dataset {dataset_id} not found in organization {organization_id}")


class QAColumnNotFoundError(QAServiceError):
    status_code = 404

    def __init__(self, dataset_id: UUID, column_id: UUID):
        self.dataset_id = dataset_id
        self.column_id = column_id
        super().__init__(f"Column {column_id} not found in dataset {dataset_id}")
