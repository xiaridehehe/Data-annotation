#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
python3 -m venv .venv
.venv/bin/pip install -r backend/requirements.txt
npm --prefix frontend install
.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload &
api_pid=$!
trap 'kill "$api_pid"' EXIT
npm --prefix frontend run dev
