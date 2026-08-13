"""存储层：JSON 落盘（中间产物/结果）+ SQLite（运行元数据）。

- data/runs/{run_id}/*.json   —— 每阶段产物即时落盘，UI 可随时读取
- data/cache/*                —— 提交到仓库的离线演示缓存（meta.json 标 cache=true）
- data/app.db                 —— SQLite 运行元数据（gitignore）
"""
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .config import settings


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def new_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S") + "_" + uuid.uuid4().hex[:6]


def run_dir(run_id: str) -> Path:
    d = settings.data_dir / "runs" / run_id
    d.mkdir(parents=True, exist_ok=True)
    return d


# --------------------------------------------------------------------------
# JSON 产物
# --------------------------------------------------------------------------
def save_artifact(run_id: str, name: str, data: Any) -> Path:
    p = run_dir(run_id) / f"{name}.json"
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    return p


def load_artifact(run_id: str, name: str) -> Any:
    p = run_dir(run_id) / f"{name}.json"
    if not p.exists():
        p = settings.cache_dir / run_id / f"{name}.json"
    if not p.exists():
        return None
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)


def list_artifacts(run_id: str) -> list[str]:
    d = run_dir(run_id)
    # run_dir 会创建目录，需判断是否有真实产物；否则回退缓存目录
    if not d.exists() or not any(d.glob("*.json")):
        d = settings.cache_dir / run_id
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.json"))


def list_cache_runs() -> list[dict]:
    """扫描缓存目录中的离线演示运行（meta.json 标注 cache=true）。"""
    runs = []
    for d in settings.cache_dir.glob("*"):
        meta_file = d / "meta.json"
        if d.is_dir() and meta_file.exists():
            try:
                runs.append(json.loads(meta_file.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                continue
    return sorted(runs, key=lambda m: m.get("created_at", ""), reverse=True)


# --------------------------------------------------------------------------
# SQLite 运行元数据
# --------------------------------------------------------------------------
def _connect() -> sqlite3.Connection:
    settings.ensure_dirs()
    conn = sqlite3.connect(settings.db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = _connect()
    conn.execute(
        """CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            app_id TEXT, app_name TEXT, url TEXT, goal TEXT,
            provider TEXT, model TEXT, status TEXT,
            created_at TEXT, finished_at TEXT,
            cache INTEGER DEFAULT 0, cache_note TEXT, source TEXT,
            stages_json TEXT
        )"""
    )
    conn.commit()
    conn.close()


def save_run_meta(meta: dict[str, Any]) -> None:
    conn = _connect()
    conn.execute(
        """INSERT OR REPLACE INTO runs
           (run_id, app_id, app_name, url, goal, provider, model, status,
            created_at, finished_at, cache, cache_note, source, stages_json)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            meta.get("run_id"),
            meta.get("app_id"),
            meta.get("app_name"),
            meta.get("url"),
            meta.get("goal"),
            meta.get("provider"),
            meta.get("model"),
            meta.get("status"),
            meta.get("created_at"),
            meta.get("finished_at"),
            1 if meta.get("cache") else 0,
            meta.get("cache_note"),
            meta.get("source"),
            json.dumps(meta.get("stages", []), ensure_ascii=False, default=str),
        ),
    )
    conn.commit()
    conn.close()


def update_run_status(
    run_id: str,
    status: str,
    finished_at: Optional[str] = None,
    stages: Optional[list] = None,
) -> None:
    conn = _connect()
    if stages is not None:
        conn.execute(
            "UPDATE runs SET status=?, finished_at=COALESCE(?, finished_at), stages_json=? WHERE run_id=?",
            (status, finished_at, json.dumps(stages, ensure_ascii=False, default=str), run_id),
        )
    else:
        conn.execute(
            "UPDATE runs SET status=?, finished_at=COALESCE(?, finished_at) WHERE run_id=?",
            (status, finished_at, run_id),
        )
    conn.commit()
    conn.close()


def get_run_meta(run_id: str) -> Optional[dict]:
    conn = _connect()
    row = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
    conn.close()
    if row is None:
        return None
    meta = dict(row)
    meta["cache"] = bool(meta["cache"])
    try:
        meta["stages"] = json.loads(meta["stages_json"] or "[]")
    except json.JSONDecodeError:
        meta["stages"] = []
    meta.pop("stages_json", None)
    return meta


def list_runs(limit: int = 50) -> list[dict]:
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
    ).fetchall()
    conn.close()
    out = []
    for row in rows:
        meta = dict(row)
        meta["cache"] = bool(meta["cache"])
        meta.pop("stages_json", None)
        out.append(meta)
    return out
