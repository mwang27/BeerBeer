#!/usr/bin/env bash
# Postgres entrypoint hook: provisions the BeerBeer warehouse
# alongside the Superset metadata database.
set -euo pipefail

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "postgres" <<-EOSQL
    CREATE DATABASE beerbeer OWNER $POSTGRES_USER;
EOSQL

for f in /docker-entrypoint-initdb.d/sql/*.sql; do
    echo ">>> applying $f to beerbeer"
    psql -v ON_ERROR_STOP=1 \
         --username "$POSTGRES_USER" \
         --dbname   "beerbeer" \
         --file     "$f"
done
