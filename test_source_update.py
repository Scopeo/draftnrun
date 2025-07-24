#!/usr/bin/env python3
"""
Test script to verify that source creation and update functionality works correctly.
This script tests the separate create and update endpoints.
"""

import requests
import json
from uuid import uuid4
from datetime import datetime

# Configuration - update these values as needed
ADA_URL = "http://localhost:8000"  # Update with your actual ADA backend URL
INGESTION_API_KEY = "your-ingestion-api-key"  # Update with your actual API key
ORGANIZATION_ID = str(uuid4())  # Use a test organization ID


def test_create_and_update_source():
    """Test the create and update source endpoints"""

    # Test source data
    source_data = {
        "name": "test_source",
        "type": "local",
        "database_schema": "test_schema",
        "database_table_name": "test_table",
        "qdrant_collection_name": "test_collection",
        "qdrant_schema": {
            "chunk_id_field": "chunk_id",
            "content_field": "content",
            "file_id_field": "file_id",
            "last_edited_ts_field": "last_edited_ts",
            "metadata_fields_to_keep": ["metadata"],
        },
        "embedding_model_reference": "openai:text-embedding-3-large",
    }

    print(f"Testing create and update source for organization: {ORGANIZATION_ID}")
    print(f"Source name: {source_data['name']}")

    # First call - should create a new source
    print("\n1. Creating a new source")
    try:
        response = requests.post(
            f"{ADA_URL}/sources/{ORGANIZATION_ID}",
            json=source_data,
            headers={
                "x-ingestion-api-key": INGESTION_API_KEY,
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        source_id = response.json()
        print(f"✅ Source created successfully - Source ID: {source_id}")
    except Exception as e:
        print(f"❌ Source creation failed: {str(e)}")
        return

    # Second call - should update the existing source
    print("\n2. Updating the existing source")
    updated_source_data = source_data.copy()
    updated_source_data["database_table_name"] = "updated_test_table"
    updated_source_data["qdrant_collection_name"] = "updated_test_collection"

    try:
        response = requests.patch(
            f"{ADA_URL}/sources/{source_id}",
            json=updated_source_data,
            headers={
                "x-ingestion-api-key": INGESTION_API_KEY,
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        print(f"✅ Source updated successfully")

    except Exception as e:
        print(f"❌ Source update failed: {str(e)}")
        return

    # Verify the source exists and has last_updated_at field
    print("\n3. Verifying source details")
    try:
        response = requests.get(
            f"{ADA_URL}/sources/{ORGANIZATION_ID}",
            headers={
                "x-ingestion-api-key": INGESTION_API_KEY,
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        sources = response.json()

        # Find our test source
        test_source = None
        for source in sources:
            if source["id"] == source_id:
                test_source = source
                break

        if test_source:
            print(f"✅ Source found in list")
            print(f"   - ID: {test_source['id']}")
            print(f"   - Name: {test_source['name']}")
            print(f"   - Database table: {test_source['database_table_name']}")
            print(f"   - Qdrant collection: {test_source['qdrant_collection_name']}")
            print(f"   - Created at: {test_source['created_at']}")
            print(f"   - Updated at: {test_source['updated_at']}")
            print(f"   - Last updated at: {test_source.get('last_updated_at', 'Not set')}")

            if test_source.get("last_updated_at"):
                print("✅ last_updated_at field is present")
            else:
                print("⚠️  last_updated_at field is not present")

            # Check if the update was successful
            if (
                test_source["database_table_name"] == "updated_test_table"
                and test_source["qdrant_collection_name"] == "updated_test_collection"
            ):
                print("✅ Source was updated successfully")
            else:
                print("❌ Source was not updated correctly")
        else:
            print("❌ Source not found in list")

    except Exception as e:
        print(f"❌ Failed to get sources: {str(e)}")


def test_update_nonexistent_source():
    """Test updating a source that doesn't exist"""
    print("\n4. Testing update of non-existent source")

    fake_source_id = str(uuid4())
    source_data = {
        "name": "fake_source",
        "type": "local",
        "database_table_name": "fake_table",
        "qdrant_collection_name": "fake_collection",
        "qdrant_schema": {},
        "embedding_model_reference": "openai:text-embedding-3-large",
    }

    try:
        response = requests.patch(
            f"{ADA_URL}/sources/{fake_source_id}",
            json=source_data,
            headers={
                "x-ingestion-api-key": INGESTION_API_KEY,
                "Content-Type": "application/json",
            },
        )
        if response.status_code == 404:
            print("✅ Correctly returned 404 for non-existent source")
        else:
            print(f"❌ Expected 404 but got {response.status_code}")
    except Exception as e:
        print(f"❌ Update request failed: {str(e)}")


if __name__ == "__main__":
    print("Testing Source Creation and Update Functionality")
    print("=" * 60)

    # Check if configuration is set
    if ADA_URL == "http://localhost:8000":
        print("⚠️  Please update ADA_URL in the script with your actual backend URL")

    if INGESTION_API_KEY == "your-ingestion-api-key":
        print("⚠️  Please update INGESTION_API_KEY in the script with your actual API key")

    if ADA_URL == "http://localhost:8000" or INGESTION_API_KEY == "your-ingestion-api-key":
        print("\nPlease update the configuration variables and run the script again.")
        exit(1)

    test_create_and_update_source()
    test_update_nonexistent_source()
    print("\nTest completed!")
