#!/usr/bin/env bash
# Start MySQL and make sure the team database is ready. Safe to run any time.
#
#   bash scripts/setup_db.sh
#
# 1. starts the MySQL server if it is not running
# 2. imports db/boq_intelligence_dump.sql when the database is missing or the dump
#    file changed since the last import (re-import replaces the tables)
# 3. creates the MySQL user boq / boq for the program
# 4. writes .env from .env.example if there is none
#
# Used automatically by GitHub Codespaces (.devcontainer) and after `git pull`
# (.githooks/post-merge). Needs a Linux machine with MySQL 8 installed and sudo.
# Where MySQL root logs in with a password instead (GitHub Actions), set
# MYSQL_ROOT_OPTS, e.g.  MYSQL_ROOT_OPTS="-uroot -proot" bash scripts/setup_db.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DUMP="$ROOT/db/boq_intelligence_dump.sql"
MARKER="$HOME/.boq_imported_dump.sha256"
SUDO=""
[ "$(id -u)" -ne 0 ] && SUDO="sudo"
if [ -n "${MYSQL_ROOT_OPTS:-}" ]; then
  MYSQL="mysql $MYSQL_ROOT_OPTS --default-character-set=utf8mb4"
  PING="mysqladmin $MYSQL_ROOT_OPTS ping --silent"
else
  MYSQL="$SUDO mysql --default-character-set=utf8mb4"
  PING="$SUDO mysqladmin ping --silent"
fi

if ! $PING >/dev/null 2>&1; then
  echo "[setup_db] starting MySQL ..."
  $SUDO service mysql start >/dev/null
  for _ in $(seq 1 30); do
    $PING >/dev/null 2>&1 && break
    sleep 1
  done
fi

current_sha="$(sha256sum "$DUMP" | cut -d' ' -f1)"
db_exists="$($MYSQL -N -e "SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='boq_intelligence'")"
if [ "$db_exists" = "0" ] || [ "$(cat "$MARKER" 2>/dev/null)" != "$current_sha" ]; then
  echo "[setup_db] importing db/boq_intelligence_dump.sql ..."
  $MYSQL < "$DUMP"
  echo "$current_sha" > "$MARKER"
else
  echo "[setup_db] database is up to date with db/boq_intelligence_dump.sql"
fi

$MYSQL -e "CREATE USER IF NOT EXISTS 'boq'@'localhost' IDENTIFIED BY 'boq';
           GRANT ALL PRIVILEGES ON boq_intelligence.* TO 'boq'@'localhost';"

if [ ! -f "$ROOT/.env" ]; then
  sed -e 's/^DB_HOST=.*/DB_HOST=127.0.0.1/' \
      -e 's/^DB_USER=.*/DB_USER=boq/' \
      -e 's/^DB_PASSWORD=.*/DB_PASSWORD=boq/' \
      -e 's/^DB_NAME=.*/DB_NAME=boq_intelligence/' \
      "$ROOT/.env.example" > "$ROOT/.env"
  echo "[setup_db] created .env (user boq / boq, this machine only)"
fi
echo "[setup_db] ready: run  python main.py  or  python -m unittest -v"
