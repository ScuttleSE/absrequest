#!/bin/sh
set -e

echo "Initialising database..."
python - <<'EOF'
from run import app
from app import db
with app.app_context():
    db.create_all()
print("Database tables ready.")
EOF

echo "Starting Gunicorn..."
exec gunicorn \
    --bind 0.0.0.0:5001 \
    --workers 1 \
    --threads 4 \
    --timeout 120 \
    run:app
