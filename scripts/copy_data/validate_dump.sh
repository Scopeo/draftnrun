#!/bin/bash
# Validates a PostgreSQL dump file
# Usage: validate_dump.sh <dump_path>
#   Returns 0 on success, 1 on failure

set -e

DUMP_PATH="${1:-}"

if [ -z "$DUMP_PATH" ]; then
  echo "ERROR: Dump path is required" >&2
  echo "Usage: validate_dump.sh <dump_path>" >&2
  exit 1
fi

# Verify dump was created successfully
if [ ! -f "$DUMP_PATH" ]; then
  echo "ERROR: Dump file was not created!" >&2
  exit 1
fi

# Check dump file is not empty
DUMP_SIZE=$(stat -c%s "$DUMP_PATH" 2>/dev/null || stat -f%z "$DUMP_PATH" 2>/dev/null || echo "0")
if [ "$DUMP_SIZE" -eq 0 ]; then
  echo "ERROR: Dump file is empty!" >&2
  exit 1
fi

# Verify dump integrity by listing its contents
echo "===> Verifying dump integrity..."
if ! pg_restore --list "$DUMP_PATH" > /dev/null 2>&1; then
  echo "ERROR: Dump file appears to be corrupted or invalid!" >&2
  exit 1
fi

# Show dump file info with timestamp to confirm it's fresh
DUMP_SIZE_HUMAN=$(du -h "$DUMP_PATH" | cut -f1)
DUMP_TIME=$(stat -c %Y "$DUMP_PATH" 2>/dev/null || stat -f %m "$DUMP_PATH" 2>/dev/null)
DUMP_DATE=$(date -d "@$DUMP_TIME" 2>/dev/null || date -r "$DUMP_TIME" 2>/dev/null || echo "unknown")
echo "===> ✅ Dump validation successful"
echo "===> Dump file size: $DUMP_SIZE_HUMAN ($DUMP_SIZE bytes)"
echo "===> Dump location: $DUMP_PATH"
echo "===> Dump created at: $DUMP_DATE (timestamp: $DUMP_TIME)"
echo "===> Dump integrity: OK"
