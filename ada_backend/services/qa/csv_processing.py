import csv
import io
import json
from typing import BinaryIO, Dict, List, Optional

from ada_backend.services.qa.qa_error import (
    CSVEmptyFileError,
    CSVInvalidJSONError,
    CSVInvalidPositionError,
    CSVMissingDatasetColumnError,
)


def get_headers_from_csv(csv_file: BinaryIO) -> List[str]:
    text_file = io.TextIOWrapper(csv_file, encoding="utf-8", newline="")
    try:
        reader = csv.DictReader(text_file)
        found_columns = reader.fieldnames or []
        return found_columns
    finally:
        text_file.detach()
        csv_file.seek(0)


def process_csv(csv_file: BinaryIO, custom_columns_mapping: Optional[Dict[str, str]] = None):
    text_file = io.TextIOWrapper(csv_file, encoding="utf-8", newline="")
    try:
        reader = csv.DictReader(text_file)
        required_columns = ["input", "expected_output"]
        found_columns = reader.fieldnames or []

        if not found_columns:
            raise CSVEmptyFileError()

        for column in required_columns:
            if column not in found_columns:
                raise CSVMissingDatasetColumnError(
                    column=column, found_columns=list(found_columns), required_columns=required_columns
                )

        row_count = 0
        for row_number, row in enumerate(reader, start=2):
            row_count += 1
            raw_json = row["input"]
            try:
                parsed_json = json.loads(raw_json)
            except json.JSONDecodeError:
                raise CSVInvalidJSONError(row_number=row_number)
            position = None
            if "position" in row:
                raw_position = row["position"]
                try:
                    position = int(raw_position)
                    if position < 1:
                        raise CSVInvalidPositionError(row_number=row_number)
                except (TypeError, ValueError):
                    raise CSVInvalidPositionError(row_number=row_number)
            custom_columns_from_csv = None
            if custom_columns_mapping:
                custom_columns_from_csv = {}
                for col_id, column_name in custom_columns_mapping.items():
                    if column_name not in row:
                        raise CSVMissingDatasetColumnError(
                            column=column_name, found_columns=list(found_columns), required_columns=required_columns
                        )
                    custom_columns_from_csv[col_id] = row[column_name]
            yield {
                "input": parsed_json,
                "expected_output": row["expected_output"],
                "position": position,
                "custom_columns": custom_columns_from_csv,
            }

        if row_count == 0:
            raise CSVEmptyFileError()
    finally:
        text_file.detach()
