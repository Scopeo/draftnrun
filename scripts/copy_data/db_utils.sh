#!/bin/bash
# Common functions and variables for copy_data scripts

# Cache configuration
# TTL source of truth: ada_backend.latest.dump (single TTL for both DBs + Qdrant)
CACHE_DIR="/home/ec2-user/staging-cache/db-dumps"
BACKEND_DUMP_PATH="$CACHE_DIR/ada_backend.latest.dump"
INGESTION_DUMP_PATH="$CACHE_DIR/ada_ingestion.latest.dump"
TTL_MINUTES=1440  # 24 hours

# Ensure cache directory exists
mkdir -p "$CACHE_DIR"

# Check and install PostgreSQL 16 client tools if needed
ensure_pg_tools() {
  if ! command -v pg_dump &> /dev/null; then
    echo "===> Installing PostgreSQL 16 client tools"
    sudo dnf remove -y postgresql15* || true
    sudo dnf install -y postgresql16
  else
    echo "===> PostgreSQL 16 client tools already installed"
  fi
}

# Check dump age and TTL
# Single TTL source of truth: checks ada_backend.latest.dump age
# Returns 0 if cache is valid, 1 if expired or not found
check_dump_ttl() {
  local dump_file="$1"
  local dump_name="$2"
  if [ ! -f "$dump_file" ]; then
    echo "===> $dump_name: No cached dump found, will create new one"
    return 1
  fi
  local current_time=$(date +%s)
  local file_time=$(stat -c %Y "$dump_file")
  local age_seconds=$((current_time - file_time))
  local age_minutes=$((age_seconds / 60))
  local remaining_minutes=$((TTL_MINUTES - age_minutes))
  local age_hours=$((age_minutes / 60))
  local remaining_hours=$((remaining_minutes / 60))
  if [ $remaining_minutes -le 0 ]; then
    echo "===> $dump_name: Cache expired (age: ${age_hours}h), will refresh"
    return 1
  else
    echo "===> $dump_name: Cache age: ${age_hours}h, TTL remaining: ${remaining_hours}h (${remaining_minutes}m)"
    return 0
  fi
}

# Extract database connection parameters from PostgreSQL URL
# URL format: postgresql://user:pass@host:port/dbname
# Returns: host|port|user|pass|dbname
extract_db_params() {
  local url="$1"
  local user_pass_host=$(echo "$url" | sed -n 's|postgresql://\([^@]*\)@.*|\1|p')
  local user=$(echo "$user_pass_host" | cut -d: -f1)
  local pass=$(echo "$user_pass_host" | cut -d: -f2)
  local host_port=$(echo "$url" | sed -n 's|.*@\([^/]*\)/.*|\1|p')
  local host=$(echo "$host_port" | cut -d: -f1)
  local port=$(echo "$host_port" | cut -d: -f2)
  local dbname=$(echo "$url" | sed -n 's|.*/\([^/]*\)$|\1|p')
  
  port=${port:-5432}
  
  echo "$host|$port|$user|$pass|$dbname"
}


terminate_db_connections() {
  local db_url="$1"
  local db_name="$2"
  local params=$(extract_db_params "$db_url")
  local host=$(echo "$params" | cut -d'|' -f1)
  local port=$(echo "$params" | cut -d'|' -f2)
  local user=$(echo "$params" | cut -d'|' -f3)
  local pass=$(echo "$params" | cut -d'|' -f4)

  echo "===> Terminating active connections to $db_name"
  export PGPASSWORD="$pass"
  psql -h "$host" -p "$port" -U "$user" -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = '$db_name' AND pid <> pg_backend_pid();" > /dev/null 2>&1 || true
  unset PGPASSWORD
}


drop_and_create_db() {
  local db_url="$1"
  local db_name="$2"
  local params=$(extract_db_params "$db_url")
  local host=$(echo "$params" | cut -d'|' -f1)
  local port=$(echo "$params" | cut -d'|' -f2)
  local user=$(echo "$params" | cut -d'|' -f3)
  local pass=$(echo "$params" | cut -d'|' -f4)

  # Terminate active connections first
  terminate_db_connections "$db_url" "$db_name"

  echo "===> Dropping database $db_name"
  export PGPASSWORD="$pass"
  dropdb -h "$host" -p "$port" -U "$user" "$db_name" || true
  echo "===> Creating database $db_name"
  createdb -h "$host" -p "$port" -U "$user" "$db_name"
  unset PGPASSWORD
}

