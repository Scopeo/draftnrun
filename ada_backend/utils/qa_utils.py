import csv
import io
import json

from ada_backend.services.errors import CSVEmptyFileError, CSVMissingColumnError, CSVInvalidJSONError


def process_csv(csv_content: str):
    if not csv_content.strip():
        raise CSVEmptyFileError()
    reader = csv.DictReader(io.StringIO(csv_content))
    required_columns = ["input", "expected_output"]
    found_columns = reader.fieldnames or []

    for column in required_columns:
        if column not in found_columns:
            raise CSVMissingColumnError(
                column=column, found_columns=list(found_columns), required_columns=required_columns
            )
    for row_number, row in enumerate(reader, start=2):
        raw_json = row["input"]
        try:
            parsed_json = json.loads(raw_json)
        except json.JSONDecodeError:
            raise CSVInvalidJSONError()

        yield {
            "input": parsed_json,
            "expected_output": row["expected_output"],
        }
