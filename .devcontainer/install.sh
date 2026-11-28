#!/usr/bin/env bash
# Runs once when a Codespace is created: installs MySQL 8 and the Python packages.
set -euo pipefail
cd "$(dirname "$0")/.."
sudo apt-get update -qq
sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq mysql-server python3-venv python3-pip python-is-python3 >/dev/null
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
git config core.hooksPath .githooks
