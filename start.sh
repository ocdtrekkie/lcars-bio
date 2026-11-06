#!/bin/sh
set -eu
cd /opt/lcars-bio
export HOME=/var
export BIO_DATA_DIR=/var/lcars-bio
export SANDSTORM=1
export PYTHONDONTWRITEBYTECODE=1
exec /opt/lcars-bio/.venv/bin/gunicorn --bind 127.0.0.1:8000 --workers 1 --threads 4 --worker-tmp-dir /tmp --access-logfile - app:app
