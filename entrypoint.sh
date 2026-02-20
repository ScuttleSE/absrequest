#!/bin/sh
set -e

echo "Running database migrations..."
# Initialise the migrations folder on first run, then apply all migrations.
if [ ! -d "migrations" ]; then
  echo "No migrations folder found — running flask db init..."
  flask db init
  flask db migrate -m "initial schema"
fi
flask db upgrade

echo "Starting Gunicorn..."
exec gunicorn \
    --bind 0.0.0.0:5001 \
    --workers 1 \
    --threads 4 \
    --timeout 120 \
    run:app
