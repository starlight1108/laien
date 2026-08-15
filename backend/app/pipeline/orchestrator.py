"""流水线编排器：10 阶段状态机 + 后台执行 + SSE 事件广播 + 断点重跑。

- 每阶段产物即时落盘，UI 可随时读取（失败也能看已完成部分）
- 阶段状态：pending -> running -> succeeded / failed / degraded / revised
- 事件通过 asyncio.Queue 广播，SSE 端点消费
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from ..config import settings
from ..llm.client import LLMClient, LLMError
from ..schemas import RunMeta, StageResult
from ..storage import (
    init_db,
    new_run_id,
    save_artifact,
    save_run_meta,
    update_run_status,
)

logger = logging.getLogger(__name__)


class StageError(Exception):
    """阶段执行失败（可被编排器捕获并降级）。"""

    def __init__(self, message: str = "", degraded: bool = False) -> None:
        super().__init__(message)
        self.degraded = degraded


class RunContext:
    """一次运行的共享上下文。"""

    def __init__(
        self,
        run_id: str,
        meta: RunMeta,
        llm: Optional[LLMClient] = None,
        api_key: str = "",
    ) -> None:
        self.run_id = run_id
        self.meta = meta
        self.llm = llm
        self.api_key = api_key  # 仅内存，禁止落盘
        self._artifacts: dict[str, Any] = {}

    def save(self, name: str, data: Any) -> None:
        save_artifact(self.run_id, name, data)
        self._artifacts[name] = data

    def load(self, name: str) -> Any:
        if name in self._artifacts:
            return self._artifacts[name]
        from ..storage import load_artifact

        data = load_artifact(self.run_id, name)
        self._artifacts[name] = data
        return data

    def goal(self) -> str:
        return self.meta.goal or ""

    async def llm_call(self, system: str, user: str, schema: Optional[dict] = None,
                       temperature: Optional[float] = None) -> dict:
        """在线程池中执行 LLM 调用，避免同步网络阻塞事件循环。"""
        if self.llm is None:
            raise StageError("未配置 LLM（缺少模型或 API Key）", degraded=True)
        return await asyncio.to_thread(
            self.llm.complete_json, system, user, schema, temperature
        )

    def scope_for_goal(self, goal: str) -> dict:
        """根据目标解析约束（确定性规则）。"""
        g = goal.lower()
        scope = {"filters": [], "focus": []}
        if "低分" in goal or "low" in g or "负评" in goal:
            scope["filters"].append({"field": "rating", "op": "lte", "value": 2, "label": "仅低分评论(≤2星)"})
        if "版本" in goal or "version" in g:
            scope["filters"].append({"field": "version", "op": "eq", "value": None, "label": "指定版本（待识别）"})
        for kw, label in (
            ("订阅", "订阅转化"),
            ("可用性", "可用性/易用性"),
            ("付费", "付费/价格"),
            ("性能", "性能/卡顿"),
            ("崩溃", "崩溃/闪退"),
            ("广告", "广告"),
        ):
            if kw in goal or kw in g:
                scope["focus"].append(label)
        scope["summary"] = f"目标:{goal or '(默认:整体用户问题)'}; 约束:{scope['filters'] or '无'}; 聚焦:{scope['focus'] or '整体'}"
        return scope


class BaseStage:
    name: str = ""
    label: str = ""

    async def execute(self, ctx: RunContext) -> dict:
        """返回该阶段的 summary；产物通过 ctx.save() 落盘。"""
        raise NotImplementedError


def _register_stages() -> list[type[BaseStage]]:
    from .stages.scope import ScopeStage
    from .stages.collect import CollectStage
    from .stages.clean import CleanStage
    from .stages.analyze import AnalyzeStage
    from .stages.evidence import EvidenceStage
    from .stages.prd import PRDStage
    from .stages.tests import TestsStage
    from .stages.validate import ValidateStage

    return [
        ScopeStage,
        CollectStage,
        CleanStage,
        AnalyzeStage,
        EvidenceStage,
        PRDStage,
        TestsStage,
        ValidateStage,
    ]


class Orchestrator:
    def __init__(self) -> None:
        init_db()
        self.STAGES = _register_stages()
        self._queues: dict[str, asyncio.Queue] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._ctx: dict[str, RunContext] = {}

    # ------------------------------------------------------------------
    # 运行管理
    # ------------------------------------------------------------------
    def create_run(
        self,
        url: Optional[str] = None,
        goal: str = "",
        provider: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        api_key: str = "",
        import_data: Optional[list[dict]] = None,
        app_id: Optional[str] = None,
        app_name: Optional[str] = None,
        cache: bool = False,
        cache_note: Optional[str] = None,
    ) -> RunMeta:
        run_id = new_run_id()
        meta = RunMeta(
            run_id=run_id,
            url=url,
            goal=goal,
            provider=provider,
            model=model,
            source="import" if import_data else "url",
            app_id=app_id,
            app_name=app_name,
            cache=cache,
            cache_note=cache_note,
            stages=[StageResult(stage=cls.name, label=cls.label) for cls in self.STAGES],
        )
        save_run_meta(meta.model_dump(mode="json"))
        # 记录导入数据（若提供），由 collect 阶段读取
        if import_data is not None:
            save_artifact(run_id, "import_data", import_data)
        self._queues[run_id] = asyncio.Queue()

        # 构造 LLM 客户端（UI 输入优先，其次环境变量）
        # 规则：必须提供 API Key（本地模型除外），否则不构建 -> 语义阶段降级，
        # 避免无 Key 时同步调用真实 API 阻塞事件循环。
        llm = None
        effective_url = base_url or settings.llm_base_url
        if effective_url:
            effective_key = api_key or settings.llm_api_key
            is_local = (
                "localhost" in effective_url
                or "127.0.0.1" in effective_url
                or (provider or "") == "ollama"
            )
            if effective_key or is_local:
                try:
                    llm = LLMClient(
                        base_url=effective_url,
                        api_key=effective_key,
                        model=model or settings.llm_model or "",
                        temperature=settings.llm_temperature_analysis,
                        max_retries=settings.llm_max_retries,
                    )
                except LLMError as e:
                    logger.warning("LLM 客户端构建失败（将降级）: %s", e)
            else:
                logger.warning("未提供 API Key（非本地模型），语义阶段将降级")

        ctx = RunContext(run_id, meta, llm=llm, api_key=api_key)
        # 用 setdefault 而非覆盖整表：并发创建多个运行时互不丢失上下文
        self._ctx.setdefault(run_id, ctx)
        return meta

    def start(self, run_id: str) -> None:
        """在后台启动工作流。"""
        if run_id in self._tasks and not self._tasks[run_id].done():
            return
        self._tasks[run_id] = asyncio.create_task(self._run(run_id))

    def subscribe(self, run_id: str) -> asyncio.Queue:
        q = self._queues.get(run_id)
        if q is None:
            q = asyncio.Queue()
            self._queues[run_id] = q
        return q

    async def publish(self, run_id: str, event: dict) -> None:
        q = self._queues.get(run_id)
        if q is not None:
            await q.put(event)

    def get_ctx(self, run_id: str) -> Optional[RunContext]:
        return self._ctx.get(run_id)

    def forget_run(self, run_id: str) -> None:
        """删除运行后的内存清理：取消未完成任务、移除事件队列与上下文。"""
        task = self._tasks.pop(run_id, None)
        if task is not None and not task.done():
            task.cancel()
        self._queues.pop(run_id, None)
        self._ctx.pop(run_id, None)

    # ------------------------------------------------------------------
    # 主流程
    # ------------------------------------------------------------------
    async def _run(self, run_id: str) -> None:
        ctx = self._ctx.get(run_id)
        if ctx is None:
            return
        update_run_status(run_id, "running")
        await self.publish(run_id, {"type": "run_start", "run_id": run_id})

        for i, stage_cls in enumerate(self.STAGES):
            stage = stage_cls()
            result = StageResult(stage=stage.name, label=stage.label)
            result.status = "running"
            result.started_at = datetime.now(timezone.utc)
            self._update_stage(ctx, i, result)
            try:
                summary = await stage.execute(ctx)
                result.status = "succeeded"
                result.summary = summary or {}
                result.artifacts = self._list_artifacts(ctx)
                if getattr(stage, "revisions", None):
                    result.revisions = stage.revisions
            except StageError as e:
                result.status = "degraded" if getattr(e, "degraded", False) else "failed"
                result.error = str(e)
                logger.warning("stage %s failed: %s", stage.name, e)
            except Exception as e:  # noqa: BLE001
                result.status = "failed"
                result.error = f"{type(e).__name__}: {e}"
                logger.exception("stage %s unexpected error", stage.name)
            finally:
                result.finished_at = datetime.now(timezone.utc)
                self._update_stage(ctx, i, result)

        meta = ctx.meta
        status = "succeeded"
        if any(s.status == "failed" for s in meta.stages):
            status = "failed"
        elif any(s.status == "degraded" for s in meta.stages):
            status = "degraded"
        meta.status = status
        meta.finished_at = datetime.now(timezone.utc)
        save_run_meta(meta.model_dump(mode="json"))
        update_run_status(run_id, status, finished_at=meta.finished_at.isoformat())
        await self.publish(
            run_id,
            {"type": "run_end", "run_id": run_id, "status": status},
        )

    def _update_stage(self, ctx: RunContext, index: int, result: StageResult) -> None:
        meta = ctx.meta
        while len(meta.stages) <= index:
            meta.stages.append(StageResult(stage="", label=""))
        meta.stages[index] = result
        save_run_meta(meta.model_dump(mode="json"))
        asyncio.get_event_loop().create_task(
            self.publish(run_id=ctx.run_id, event=result.model_dump(mode="json"))
        )

    @staticmethod
    def _list_artifacts(ctx: RunContext) -> list[str]:
        from ..storage import list_artifacts

        return list_artifacts(ctx.run_id)


orchestrator = Orchestrator()
