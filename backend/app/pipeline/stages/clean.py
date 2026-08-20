"""阶段 3：清洗、去重、结构化（确定性规则）。"""
from __future__ import annotations

from ...schemas import RawReview
from ...services.clean import clean_pipeline
from ..orchestrator import BaseStage, RunContext


class CleanStage(BaseStage):
    name = "clean"
    label = "3. 清洗·去重·结构化"

    async def execute(self, ctx: RunContext) -> dict:
        raw = ctx.load("raw_reviews") or []
        raw_objs = [RawReview(**d) for d in raw]
        out = clean_pipeline(
            raw_objs,
            on_step=lambda p, m: ctx.report_progress(p, m),
        )
        ctx.save("cleaned_reviews", [r.model_dump() for r in out["reviews"]])
        ctx.save("clean_report", out["report"])
        ctx.report_progress(100, f"清洗完成：保留 {out['report']['kept_count']} 条")
        return out["report"]
