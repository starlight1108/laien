"""pytest 公共配置：把 backend 加入 path，使用临时数据目录。"""
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import pytest  # noqa: E402

from app.config import settings  # noqa: E402
from app.storage import init_db  # noqa: E402


@pytest.fixture()
def temp_settings(tmp_path, monkeypatch):
    """把数据目录指向临时目录，避免污染真实数据。"""
    monkeypatch.setattr(settings, "data_dir", tmp_path / "data")
    monkeypatch.setattr(settings, "cache_dir", tmp_path / "cache")
    monkeypatch.setattr(settings, "db_path", tmp_path / "app.db")
    settings.ensure_dirs()
    init_db()
    return settings
