"""
Copy Qdrant collections from source to target using snapshots.

Determines which collections to copy in two ways:
- If SOURCE_DB_URL is provided: reads data_sources.qdrant_collection_name from source DB (only referenced collections)
- If SOURCE_DB_URL is NOT provided: lists ALL collections from the source Qdrant cluster

Then, for each collection:
1. Creates a snapshot in the source cluster
2. Downloads the snapshot file
3. Uploads and restores it in the target cluster

Usage (recommended with flags):

    uv run scripts/copy_data/copy_qdrant_collections.py \\
        --source-url  $SOURCE_QDRANT_CLUSTER_URL \\
        --source-key  $SOURCE_QDRANT_API_KEY \\
        --target-url  $TARGET_QDRANT_CLUSTER_URL \\
        --target-key  $TARGET_QDRANT_API_KEY \\
        [--source-db-url $SOURCE_DB_URL]

If flags are not provided, the script falls back to these env vars:

    SOURCE_QDRANT_CLUSTER_URL, SOURCE_QDRANT_API_KEY,
    TARGET_QDRANT_CLUSTER_URL, TARGET_QDRANT_API_KEY, SOURCE_DB_URL
"""

import argparse
import os
import sys
from pathlib import Path

import requests
from sqlalchemy import create_engine, text
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


def get_collections_from_db(db_url: str) -> set[str]:
    """Read unique collection names from data_sources.qdrant_collection_name in the given DB."""
    try:
        engine = create_engine(db_url)
        with engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT DISTINCT qdrant_collection_name FROM data_sources WHERE qdrant_collection_name IS NOT NULL"
                )
            )
            collections = {row[0] for row in result.fetchall() if row[0]}
        return collections
    except Exception as e:
        print(f"ERROR: Failed to read collections from DB: {e}", file=sys.stderr)
        sys.exit(1)


def get_collections_from_qdrant(base_url: str, api_key: str) -> set[str]:
    """List all collection names from a Qdrant cluster."""
    url = f"{base_url}/collections"
    headers = {"api-key": api_key}

    try:
        response = requests.get(url, headers=headers, timeout=60)
        response.raise_for_status()
        data = response.json()
        collections = {c.get("name") for c in data.get("result", {}).get("collections", []) if c.get("name")}
        return collections
    except Exception as e:
        print(f"ERROR: Failed to list collections from Qdrant: {e}", file=sys.stderr)
        sys.exit(1)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((requests.exceptions.ConnectionError, requests.exceptions.Timeout)),
)
def create_snapshot(base_url: str, api_key: str, collection_name: str) -> str:
    """Create a snapshot for a collection. Returns the snapshot name."""
    url = f"{base_url}/collections/{collection_name}/snapshots"
    headers = {"api-key": api_key}

    response = requests.post(url, headers=headers, timeout=300)
    response.raise_for_status()
    result = response.json()
    snapshot_name = result.get("result", {}).get("name")
    if not snapshot_name:
        raise ValueError(f"No snapshot name in response: {result}")
    return snapshot_name


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((requests.exceptions.ConnectionError, requests.exceptions.Timeout)),
)
def download_snapshot(
    base_url: str,
    api_key: str,
    collection_name: str,
    snapshot_name: str,
    dest_path: Path,
) -> None:
    """Download a snapshot file to disk."""
    url = f"{base_url}/collections/{collection_name}/snapshots/{snapshot_name}"
    headers = {"api-key": api_key}

    response = requests.get(url, headers=headers, timeout=600, stream=True)
    response.raise_for_status()

    dest_path.parent.mkdir(parents=True, exist_ok=True)
    with dest_path.open("wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((requests.exceptions.ConnectionError, requests.exceptions.Timeout)),
)
def delete_snapshot(
    base_url: str,
    api_key: str,
    collection_name: str,
    snapshot_name: str,
) -> None:
    """Delete a snapshot from a collection."""
    url = f"{base_url}/collections/{collection_name}/snapshots/{snapshot_name}"
    headers = {"api-key": api_key}

    response = requests.delete(url, headers=headers, timeout=60)
    response.raise_for_status()


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((requests.exceptions.ConnectionError, requests.exceptions.Timeout)),
)
def upload_snapshot(
    base_url: str,
    api_key: str,
    collection_name: str,
    snapshot_path: Path,
) -> None:
    """Upload and restore a snapshot file to a collection."""
    url = f"{base_url}/collections/{collection_name}/snapshots/upload?priority=snapshot"
    headers = {"api-key": api_key}

    with snapshot_path.open("rb") as f:
        files = {"snapshot": (snapshot_path.name, f, "application/octet-stream")}
        response = requests.post(url, headers=headers, files=files, timeout=600)
        response.raise_for_status()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Copy Qdrant collections from source to target using snapshots. "
        "Reads collections from source database (data_sources.qdrant_collection_name) if SOURCE_DB_URL provided."
    )

    parser.add_argument(
        "--source-url",
        dest="source_url",
        default=os.getenv("SOURCE_QDRANT_CLUSTER_URL"),
        help="Source Qdrant cluster URL (or SOURCE_QDRANT_CLUSTER_URL env var)",
    )
    parser.add_argument(
        "--source-key",
        dest="source_key",
        default=os.getenv("SOURCE_QDRANT_API_KEY"),
        help="Source Qdrant API key (or SOURCE_QDRANT_API_KEY env var)",
    )
    parser.add_argument(
        "--target-url",
        dest="target_url",
        default=os.getenv("TARGET_QDRANT_CLUSTER_URL"),
        help="Target Qdrant cluster URL (or TARGET_QDRANT_CLUSTER_URL env var)",
    )
    parser.add_argument(
        "--target-key",
        dest="target_key",
        default=os.getenv("TARGET_QDRANT_API_KEY"),
        help="Target Qdrant API key (or TARGET_QDRANT_API_KEY env var)",
    )
    parser.add_argument(
        "--source-db-url",
        dest="source_db_url",
        default=os.getenv("SOURCE_DB_URL"),
        help="Source DB URL (to read data_sources.qdrant_collection_name from source) (or SOURCE_DB_URL env var)",
    )
    parser.add_argument(
        "--snapshot-dir",
        dest="snapshot_dir",
        default="~/staging-cache/qdrant-snapshots",
        help="Directory to store snapshot files (default: ~/staging-cache/qdrant-snapshots)",
    )
    parser.add_argument(
        "--use-existing-snapshots",
        dest="use_existing_snapshots",
        action="store_true",
        help="If snapshot file exists locally, skip creation and use existing file",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    source_url = args.source_url
    source_key = args.source_key
    target_url = args.target_url
    target_key = args.target_key
    source_db_url = args.source_db_url

    if not all([source_url, source_key, target_url, target_key]):
        print("ERROR: Missing required configuration:", file=sys.stderr)
        print("  Flags:", file=sys.stderr)
        print("    --source-url", file=sys.stderr)
        print("    --source-key", file=sys.stderr)
        print("    --target-url", file=sys.stderr)
        print("    --target-key", file=sys.stderr)
        print("  Or env vars:", file=sys.stderr)
        print("    SOURCE_QDRANT_CLUSTER_URL", file=sys.stderr)
        print("    SOURCE_QDRANT_API_KEY", file=sys.stderr)
        print("    TARGET_QDRANT_CLUSTER_URL", file=sys.stderr)
        print("    TARGET_QDRANT_API_KEY", file=sys.stderr)
        sys.exit(1)

    source_url = source_url.rstrip("/")
    target_url = target_url.rstrip("/")

    if source_db_url:
        print("===> Reading collections from source database (data_sources.qdrant_collection_name)")
        collections = get_collections_from_db(source_db_url)
    else:
        print("===> No SOURCE_DB_URL provided, reading all collections from source Qdrant")
        collections = get_collections_from_qdrant(source_url, source_key)

    if not collections:
        print("===> No collections found, nothing to copy")
        sys.exit(0)

    print(f"===> Found {len(collections)} collections to copy: {', '.join(sorted(collections))}")

    snapshot_dir = Path(args.snapshot_dir).expanduser()
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    success_count = 0
    error_count = 0
    total_collections = len(collections)

    for idx, collection_name in enumerate(sorted(collections), 1):
        print(f"\n===> Processing collection ({idx}/{total_collections}): {collection_name}")
        snapshot_path = snapshot_dir / f"{collection_name}.snapshot"

        try:
            snapshot_name = None
            if args.use_existing_snapshots and snapshot_path.exists():
                print(f"  Using existing snapshot: {snapshot_path}")
            else:
                print("  Creating snapshot in source...")
                snapshot_name = create_snapshot(source_url, source_key, collection_name)
                print(f"  Snapshot created: {snapshot_name}")

                print("  Downloading snapshot...")
                download_snapshot(source_url, source_key, collection_name, snapshot_name, snapshot_path)
                print(f"  Snapshot downloaded to {snapshot_path}")

                if snapshot_name:
                    print("  Deleting snapshot from source to free space...")
                    try:
                        delete_snapshot(source_url, source_key, collection_name, snapshot_name)
                        print(f"  Snapshot {snapshot_name} deleted from source")
                    except Exception as e:
                        print(f"  Warning: Failed to delete snapshot from source (non-critical): {e}")

            print("  Uploading and restoring in target...")
            upload_snapshot(target_url, target_key, collection_name, snapshot_path)
            print(f"  ✓ Collection {collection_name} copied successfully")

            success_count += 1

        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:
                print(f"  ⚠ Warning: Collection {collection_name} not found in source, skipping (non-fatal)")
                continue
            else:
                print(f"  ✗ Failed to copy collection {collection_name}: {e}", file=sys.stderr)
                error_count += 1
                continue
        except Exception as e:
            print(f"  ✗ Failed to copy collection {collection_name}: {e}", file=sys.stderr)
            error_count += 1
            continue

    print(f"\n===> Copy completed: {success_count} successful, {error_count} failed")

    if error_count > 0:
        print("===> Some collections failed to copy, but continuing (non-fatal errors)", file=sys.stderr)
        sys.exit(0)


if __name__ == "__main__":
    main()
