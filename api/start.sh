#!/bin/sh
set -eu

# Run before serving requests: health must not pass against an old schema.
# Alembic uses transactional migrations; failed upgrades stop this container.
alembic upgrade head
python -m app.discovery_bootstrap
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
