"""阶段 2：采集评论数据。

- 在线采集：Apple 官方 RSS Review Feed（节流 + 退避）
- 导入模式：读取创建运行时传入的 import_data（JSON/CSV 已在前端/API 解析）
- 原始数据落盘 raw_reviews.json，附来源与局限说明
"""
from __future__ import annotations

import logging

from ...schemas import RawReview
from ...services.appstore import fetch_reviews
from ..orchestrator import BaseStage, RunContext, StageError

logger = logging.getLogger(__name__)


class CollectStage(BaseStage):
    name = "collect"
    label = "2. 采集评论数据"

    async def execute(self, ctx: RunContext) -> dict:
        meta = ctx.meta
        if meta.source == "import":
            import_data = ctx.load("import_data") or []
            total = len(import_data)
            reviews: list[RawReview] = []
            errors: list[str] = []
            for i, d in enumerate(import_data):
                try:
                    r = RawReview(**{**d, "source": "import"})
                    reviews.append(r)
                except Exception as e:  # noqa: BLE001
                    errors.append(f"第 {i + 1} 条导入失败: {e}")
                if total and (i + 1) % max(1, total // 10) == 0:
                    ctx.report_progress(
                        int((i + 1) / total * 95),
                        f"正在导入评论 {i + 1}/{total}",
                    )
            ctx.save("raw_reviews", [r.model_dump() for r in reviews])
            ctx.report_progress(100, f"导入完成，共 {len(reviews)} 条")
            summary = {
                "source": "import",
                "total": len(reviews),
                "errors": errors,
                "limitations": ["数据来自用户导入，来源与真实性由导入者负责"],
            }
        else:
            scope = ctx.load("scope") or {}
            app_id = scope.get("app_id") or meta.app_id
            country = scope.get("country", "us")
            if not app_id:
                raise StageError("缺少应用 ID，无法采集")
            ctx.report_progress(5, "正在连接 App Store 评论源")

            def _on_page(page: int, max_pages: int, collected: int) -> None:
                ctx.report_progress(
                    int(page / max_pages * 90),
                    f"正在采集第 {page}/{max_pages} 页，已获取 {collected} 条",
                )

            try:
                result = await fetch_reviews(
                    app_id,
                    country,
                    on_page=_on_page,
                    pause_event=ctx.pause_event,
                )
            except Exception as e:  # noqa: BLE001
                raise StageError(f"采集失败: {e}") from e
            reviews = result["reviews"]
            ctx.save("raw_reviews", [r.model_dump() for r in reviews])
            ctx.report_progress(100, f"采集完成，共 {len(reviews)} 条")
            summary = {
                "source": "rss",
                "app_id": app_id,
                "country": country,
                "total": len(reviews),
                "pages_fetched": result["pages_fetched"],
                "errors": result["errors"],
                "limitations": result["limitations"],
            }
        return summary
