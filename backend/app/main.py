"""FastAPI 入口：API + SSE 进度 + 静态托管 Vue 构建产物。"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import settings
from .llm.client import LLMClient
from .llm.config_store import load_llm_config, load_provider_config, save_provider_config
from .llm.prompts import _GROUNDING_RULES  # noqa: F401  (确保提示词模块可导入)
from .pipeline.orchestrator import orchestrator
from .services.importing import ImportError_, normalize_import_item, parse_import_text
from .storage import get_run_meta, list_cache_runs, list_runs

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="App Review Insights", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------
class RunRequest(BaseModel):
    url: Optional[str] = None
    goal: str = ""
    provider: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None
    api_key: str = ""
    source: str = "url"  # url / import
    import_data: Optional[list[dict]] = None
    import_text: Optional[str] = None


class LLMTestRequest(BaseModel):
    provider: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    api_key: str = ""


class LLMModelsRequest(BaseModel):
    provider: Optional[str] = None
    base_url: Optional[str] = None
    api_key: str = ""


class LLMConfigRequest(BaseModel):
    provider: Optional[str] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    api_key: str = ""


# --------------------------------------------------------------------------
# Providers
# --------------------------------------------------------------------------
def _load_providers() -> list[dict]:
    p = Path(__file__).parent / "llm" / "providers.json"
    data = json.loads(p.read_text(encoding="utf-8"))
    return data["providers"]


PROVIDERS = _load_providers()


def _provider_base_url(provider_id: str) -> str:
    for p in PROVIDERS:
        if p["id"] == provider_id:
            return p.get("base_url", "")
    return ""


def _resolve_llm_config(
    provider: Optional[str], base_url: str, model: str, api_key: str
) -> tuple[str, str, str]:
    """LLM 参数兜底顺序：请求值 → 该提供商本地保存的配置槽位 → 提供商预置/环境变量。

    配置按提供商分槽保存，按 provider 精确查找 —— 切换提供商后绝不会串用
    另一家已保存的 Key / Base URL。
    """
    saved = load_provider_config(provider or "")
    if not base_url:
        if saved.get("base_url"):
            base_url = saved["base_url"]
        if not base_url:
            base_url = _provider_base_url(provider or "")
        if not base_url:
            base_url = settings.llm_base_url
    if not model:
        model = saved.get("model") or settings.llm_model
    if not api_key:
        api_key = saved.get("api_key") or settings.llm_api_key
    return base_url, model, api_key


@app.get("/api/health")
async def health() -> dict:
    return {"ok": True, "app": "app-review-insights"}


@app.get("/api/providers")
async def providers() -> dict:
    return {"providers": PROVIDERS}


@app.get("/api/llm/config")
async def get_llm_config() -> dict:
    """读取本地保存的全部提供商模型配置（按提供商分槽）。"""
    return load_llm_config()


@app.put("/api/llm/config")
async def put_llm_config(req: LLMConfigRequest) -> dict:
    """把模型配置写入本地 JSON 文件对应提供商的槽位（data/llm_config.json，已 gitignore）。"""
    if not req.provider:
        raise HTTPException(status_code=400, detail="缺少 provider")
    return save_provider_config(req.provider, req.model_dump())


@app.post("/api/llm/models")
async def llm_models(req: LLMModelsRequest) -> dict:
    """根据用户 Key 从提供商拉取可用模型列表；失败时降级为预置列表并说明。"""
    base_url, _, api_key = _resolve_llm_config(req.provider, req.base_url or "", "", req.api_key)
    if not base_url:
        return {"models": [], "source": "fallback", "error": "缺少 Base URL"}
    try:
        # 强制 15s 超时：网络挂起（如无外网）时快速降级，避免长时间等待
        models = await asyncio.wait_for(
            asyncio.to_thread(_fetch_models, base_url, api_key), timeout=15
        )
        return {"models": models, "source": "api"}
    except asyncio.TimeoutError:
        error = "连接超时（15s 内未响应），请检查网络或 Base URL"
    except Exception as e:  # noqa: BLE001
        error = str(e) or type(e).__name__
    fallback = []
    for p in PROVIDERS:
        if p["id"] == req.provider:
            fallback = list(p.get("models", []))
    return {"models": fallback, "source": "fallback", "error": error}


def _fetch_models(base_url: str, api_key: str) -> list[str]:
    """调用 OpenAI 兼容的 /models 端点（Ollama 本地同样支持）。

    降低超时与重试，使无效 Key/连接失败时快速降级到预置列表。
    """
    from openai import OpenAI

    client = OpenAI(
        base_url=base_url,
        api_key=api_key or "not-needed",
        timeout=20,
        max_retries=0,
    )
    data = client.models.list()
    names = [m.id for m in data.data]
    return sorted(names)


@app.post("/api/llm/test")
async def test_llm(req: LLMTestRequest) -> dict:
    base_url, model, api_key = _resolve_llm_config(
        req.provider, req.base_url or "", req.model or "", req.api_key
    )
    try:
        client = LLMClient(
            base_url=base_url,
            api_key=api_key,
            model=model,
            temperature=0,
            max_retries=1,
            timeout=30,
        )
        result = await asyncio.to_thread(client.test_connection)
        return result
    except Exception as e:  # noqa: BLE001
        return JSONResponse(status_code=400, content={"ok": False, "error": str(e)})


# --------------------------------------------------------------------------
# Runs
# --------------------------------------------------------------------------
@app.post("/api/runs")
async def create_run(req: RunRequest) -> dict:
    import_data = req.import_data
    if req.import_text:
        try:
            import_data = parse_import_text(req.import_text)
        except ImportError_ as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    elif import_data:
        # 逐条规范化（id/review_id 兼容 + 必填校验 + rating 归一）
        try:
            import_data = [
                normalize_import_item(item, i) for i, item in enumerate(import_data)
            ]
        except ImportError_ as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

    base_url, model, api_key = _resolve_llm_config(
        req.provider, req.base_url or "", req.model or "", req.api_key
    )
    try:
        meta = orchestrator.create_run(
            url=req.url,
            goal=req.goal,
            provider=req.provider,
            model=model or None,
            base_url=base_url or None,
            api_key=api_key,
            import_data=import_data,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    orchestrator.start(meta.run_id)
    return meta.model_dump(mode="json")


@app.get("/api/runs")
async def list_runs_api(limit: int = Query(50, ge=1, le=200)) -> dict:
    """列出实时运行与缓存演示运行（缓存明确标注）。"""
    runs = list_runs(limit)
    cached = list_cache_runs()
    seen = {r["run_id"] for r in runs}
    for c in cached:
        if c.get("run_id") not in seen:
            runs.append(c)
    return {"runs": runs}


@app.get("/api/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    meta = get_run_meta(run_id)
    if meta is None:
        # 回退到缓存演示运行
        meta = get_cache_meta(run_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="运行不存在")
    return meta


def get_cache_meta(run_id: str) -> Optional[dict]:
    """读取缓存演示运行的 meta.json（含 meta 文件回退的产物列表）。"""
    meta_file = settings.cache_dir / run_id / "meta.json"
    if not meta_file.exists():
        return None
    import json as _json

    meta = _json.loads(meta_file.read_text(encoding="utf-8"))
    meta["cache"] = True
    return meta


@app.get("/api/runs/{run_id}/events")
async def run_events(run_id: str) -> StreamingResponse:
    """SSE：阶段进度与中间结果事件流。"""
    if get_run_meta(run_id) is None:
        raise HTTPException(status_code=404, detail="运行不存在")
    queue = orchestrator.subscribe(run_id)

    async def gen():
        try:
            while True:
                event = await queue.get()
                yield f"data: {json.dumps(event, ensure_ascii=False, default=str)}\n\n"
                if event.get("type") == "run_end":
                    break
        except asyncio.CancelledError:
            pass

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/api/runs/{run_id}/artifacts/{name}")
async def get_artifact(run_id: str, name: str):
    """返回任意 JSON 可序列化产物（dict / list / 标量）。"""
    from .storage import load_artifact

    data = load_artifact(run_id, name)
    if data is None:
        raise HTTPException(status_code=404, detail=f"产物 {name} 不存在")
    return data


@app.get("/api/runs/{run_id}/artifacts")
async def list_artifact_names(run_id: str) -> dict:
    from .storage import list_artifacts

    return {"artifacts": list_artifacts(run_id)}


# --------------------------------------------------------------------------
# 静态托管（Vue 构建产物）
# --------------------------------------------------------------------------
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
else:

    @app.get("/")
    async def index() -> dict:
        return {
            "message": "App Review Insights API",
            "hint": "前端未构建（backend/app/static 不存在）。"
            "进入 frontend/ 执行 npm install && npm run build 后重启。",
            "docs": "/docs",
        }
