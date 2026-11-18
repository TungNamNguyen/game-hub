#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" >/dev/null 2>&1 && pwd)"
cd "$DIR"

if [ -f "$DIR/.venv/bin/python" ]; then
    PYTHON="$DIR/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON="python"
else
    echo "Python 3 khong tim thay tren may!"
    exit 1
fi

"$PYTHON" -c "import fastapi, uvicorn, websockets, PIL, multipart" 2>/dev/null || {
    echo "Dang cai dat thu vien tu requirements.txt..."
    "$PYTHON" -m pip install -r requirements.txt
}

echo "Khoi dong Game Hub tren localhost..."
exec "$PYTHON" server.py
