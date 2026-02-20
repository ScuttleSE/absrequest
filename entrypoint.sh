#!/bin/sh
set -e

echo "Initialising database..."
python - <<'EOF'
from sqlalchemy import text
from run import app
from app import db
with app.app_context():
    db.create_all()
    # Safe column additions for existing installs (db.create_all skips existing tables)
    migrations = [
        "ALTER TABLE app_settings ADD COLUMN audible_language VARCHAR(50) NOT NULL DEFAULT 'english'",
    ]
    for sql in migrations:
        try:
            db.session.execute(text(sql))
            db.session.commit()
        except Exception:
            db.session.rollback()  # column already exists, ignore
print("Database tables ready.")
EOF

echo "Starting Gunicorn..."
exec gunicorn \
    --bind 0.0.0.0:5001 \
    --workers 1 \
    --threads 4 \
    --timeout 120 \
    run:app
