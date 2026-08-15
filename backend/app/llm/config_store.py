"""LLM 模型配置本地持久化：按提供商分槽写入 data/llm_config.json（已 gitignore）。

替代前端 localStorage：由后端统一读写，同一服务的多设备/多浏览器共享一份配置。
Key 按提供商分别保存 —— 切换提供商时互不串用（避免把 A 家 Key 当 B 家发）。
文件结构：{"providers": {<provider_id>: {"base_url", "model", "api_key"}}}。
注意：api_key 明文存于此文件，仅限本机，禁止提交；POSIX 下写入时收紧权限 600。
"""
from __future__ import annotations

import json
import logging
import os

from ..config import settings

logger = logging.getLogger(__name__)

CONFIG_FIELDS = ("base_url", "model", "api_key")


def _config_file():
    # 运行期读取 settings.data_dir：测试经 temp_settings 重定向后可自动落临时目录
    return settings.data_dir / "llm_config.json"


def _clean_slot(cfg: dict) -> dict:
    return {f: (cfg.get(f) or "") for f in CONFIG_FIELDS}


def _write_file(payload: dict) -> None:
    """原子写入（临时文件 + rename），POSIX 下权限收紧为 600。"""
    path = _config_file()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except (OSError, NotImplementedError):
        pass  # Windows 无 POSIX 权限位，忽略
    os.replace(tmp, path)


def load_llm_config() -> dict:
    """读取本地保存的全部提供商配置：{"providers": {id: {base_url, model, api_key}}}。

    旧版扁平结构（单提供商 {provider, base_url, model, api_key}）自动迁移为分槽并
    立即回写自愈；文件不存在或损坏时返回空结构。
    """
    path = _config_file()
    if not path.exists():
        return {"providers": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        logger.warning("读取模型配置失败（%s）: %s", path, e)
        return {"providers": {}}
    if not isinstance(data, dict):
        return {"providers": {}}
    providers = data.get("providers")
    if not isinstance(providers, dict):
        # 旧版扁平结构 -> 迁移到分槽并立即回写（不依赖下次 PUT）
        provider_id = data.get("provider") or "default"
        providers = {provider_id: _clean_slot(data)}
        _write_file({"providers": providers})
    slots = {}
    for pid, raw in providers.items():
        if isinstance(raw, dict):
            slots[str(pid)] = _clean_slot(raw)
    return {"providers": slots}


def load_provider_config(provider_id: str) -> dict:
    """读取指定提供商的配置槽位（无则全空）。"""
    return load_llm_config()["providers"].get(provider_id or "", _empty_slot())


def _empty_slot() -> dict:
    return {f: "" for f in CONFIG_FIELDS}


def save_provider_config(provider_id: str, cfg: dict) -> dict:
    """原子写入单个提供商的配置槽位，POSIX 下权限收紧为 600。"""
    if not provider_id:
        raise ValueError("缺少 provider")
    settings.ensure_dirs()
    all_cfg = load_llm_config()
    clean = _clean_slot(cfg)
    all_cfg["providers"][provider_id] = clean
    _write_file(all_cfg)
    return clean
