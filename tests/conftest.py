"""Cấu hình pytest: thêm thư mục gốc repo vào sys.path để import trực tiếp các module game."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
