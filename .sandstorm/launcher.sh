#!/bin/bash
set -euo pipefail
VENV=/opt/app-venv
cd /opt/app

export HOME=/var
export BIO_DATA_DIR=/var/lcars-bio
export SANDSTORM=1
export PYTHONDONTWRITEBYTECODE=1

# Change app.py to your app's filename
$VENV/bin/python3 app.py

exit 0
