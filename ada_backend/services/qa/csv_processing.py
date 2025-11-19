import csv
import io
import json
from typing import BinaryIO

from ada_backend.services.qa.qa_error import CSVEmptyFileError, CSVMissingColumnError, CSVInvalidJSONError


def process_csv(csv_file: BinaryIO):

    text_file = io.TextIOWrapper(csv_file, encoding="utf-8", newline="")

    try:
        reader = csv.DictReader(text_file)
        required_columns = ["input", "expected_output"]
        found_columns = reader.fieldnames or []

        if not found_columns:
            raise CSVEmptyFileError()

        for column in required_columns:
            if column not in found_columns:
                raise CSVMissingColumnError(
                    column=column, found_columns=list(found_columns), required_columns=required_columns
                )

        row_count = 0
        for row_number, row in enumerate(reader, start=2):
            row_count += 1
            raw_json = row["input"]
            try:
                parsed_json = json.loads(raw_json)
            except json.JSONDecodeError:
                raise CSVInvalidJSONError()

            yield {
                "input": parsed_json,
                "expected_output": row["expected_output"],
            }

        if row_count == 0:
            raise CSVEmptyFileError()
    finally:
        text_file.detach()
