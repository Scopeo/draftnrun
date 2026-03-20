"""CLI utilities for inspecting and replaying dead-lettered messages.

Usage:
    python -m ada_ingestion_system.worker.deadletter_utils list [--stream ada_ingestion_stream]
    python -m ada_ingestion_system.worker.deadletter_utils replay <message_id> [--stream ada_ingestion_stream]
    python -m ada_ingestion_system.worker.deadletter_utils purge --older-than-days 30 [--stream ada_ingestion_stream]
"""

import argparse
import json
import time

from ada_ingestion_system.worker.base_worker import redis_client

_DEADLETTER_SUFFIX = ":deadletter"


def list_dead_letters(stream_name: str) -> list[dict]:
    dl_stream = stream_name + _DEADLETTER_SUFFIX
    entries = redis_client.xrange(dl_stream, count=200)
    results = []
    for mid, fields in entries:
        entry = {"message_id": mid, **fields}
        results.append(entry)
    return results


def replay_dead_letter(message_id: str, stream_name: str) -> bool:
    """Move a dead-lettered message back to the main stream for reprocessing."""
    dl_stream = stream_name + _DEADLETTER_SUFFIX
    entries = redis_client.xrange(dl_stream, min=message_id, max=message_id, count=1)
    if not entries:
        print(f"Message {message_id} not found in {dl_stream}")
        return False

    _mid, fields = entries[0]
    original_data = {k: v for k, v in fields.items() if not k.startswith("_")}
    redis_client.xadd(stream_name, original_data)
    redis_client.xdel(dl_stream, message_id)
    print(f"Replayed message {message_id} back to {stream_name}")
    return True


def purge_dead_letters(stream_name: str, older_than_days: int) -> int:
    """Remove dead-letter entries older than the given number of days."""
    dl_stream = stream_name + _DEADLETTER_SUFFIX
    cutoff_ms = int((time.time() - older_than_days * 86400) * 1000)
    cutoff_id = f"{cutoff_ms}-0"
    entries = redis_client.xrange(dl_stream, max=cutoff_id)
    if not entries:
        print("No entries to purge.")
        return 0
    ids = [mid for mid, _ in entries]
    redis_client.xdel(dl_stream, *ids)
    print(f"Purged {len(ids)} entries older than {older_than_days} days from {dl_stream}")
    return len(ids)


def main():
    parser = argparse.ArgumentParser(description="Dead-letter queue utilities")
    parser.add_argument("action", choices=["list", "replay", "purge"])
    parser.add_argument("message_id", nargs="?", help="Message ID (for replay)")
    parser.add_argument("--stream", default="ada_ingestion_stream", help="Base stream name")
    parser.add_argument("--older-than-days", type=int, default=30, help="Purge threshold in days")
    args = parser.parse_args()

    if args.action == "list":
        entries = list_dead_letters(args.stream)
        for entry in entries:
            print(json.dumps(entry, indent=2, default=str))
        print(f"\nTotal: {len(entries)} dead-lettered messages")

    elif args.action == "replay":
        if not args.message_id:
            parser.error("replay requires a message_id argument")
        replay_dead_letter(args.message_id, args.stream)

    elif args.action == "purge":
        purge_dead_letters(args.stream, args.older_than_days)


if __name__ == "__main__":
    main()
