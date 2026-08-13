"""全局配置：从环境变量读取；UI 传入的模型配置在运行级优先于环境变量。

密钥安全：LLM_API_KEY 仅通过环境变量或 UI 请求头传入，绝不写入日志/缓存/数据库。
"""
import os
from dataclasses import dataclass, field
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    # ---- 数据目录 ----
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DATA_DIR", "data")))
    cache_dir: Path = field(default_factory=lambda: Path(os.getenv("CACHE_DIR", "data/cache")))
    db_path: Path = field(default_factory=lambda: Path(os.getenv("DB_PATH", "data/app.db")))

    # ---- LLM 默认值（环境变量兜底，UI 输入优先）----
    llm_base_url: str = field(default_factory=lambda: os.getenv("LLM_BASE_URL", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", ""))
    llm_api_key: str = field(default_factory=lambda: os.getenv("LLM_API_KEY", ""))

    # ---- 采集限流（合规）----
    collect_interval: float = field(default_factory=lambda: float(os.getenv("COLLECT_INTERVAL", "1.5")))
    collect_max_pages: int = field(default_factory=lambda: int(os.getenv("COLLECT_MAX_PAGES", "10")))
    collect_timeout: float = field(default_factory=lambda: float(os.getenv("COLLECT_TIMEOUT", "30")))

    # ---- LLM 调用参数 ----
    llm_temperature_analysis: float = field(default_factory=lambda: float(os.getenv("LLM_TEMPERATURE_ANALYSIS", "0.2")))
    llm_temperature_writing: float = field(default_factory=lambda: float(os.getenv("LLM_TEMPERATURE_WRITING", "0.4")))
    llm_max_retries: int = field(default_factory=lambda: int(os.getenv("LLM_MAX_RETRIES", "2")))
    llm_batch_size: int = field(default_factory=lambda: int(os.getenv("LLM_BATCH_SIZE", "200")))

    # ---- 证据与去重阈值 ----
    min_supporting_count: int = field(default_factory=lambda: int(os.getenv("MIN_SUPPORTING_COUNT", "3")))
    dedup_threshold: float = field(default_factory=lambda: float(os.getenv("DEDUP_THRESHOLD", "0.85")))

    # ---- 静态托管 ----
    static_dir: Path = field(default_factory=lambda: Path(os.getenv("STATIC_DIR", "backend/app/static")))

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "runs").mkdir(parents=True, exist_ok=True)


settings = Settings()
