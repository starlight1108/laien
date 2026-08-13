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
            reviews: list[RawReview] = []
            errors: list[str] = []
            for i, d in enumerate(import_data):
                try:
                    r = RawReview(**{**d, "source": "import"})
                    reviews.append(r)
                except Exception as e:  # noqa: BLE001
                    errors.append(f"第 {i + 1} 条导入失败: {e}")
            ctx.save("raw_reviews", [r.model_dump() for r in reviews])
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
            try:
                result = await fetch_reviews(app_id, country)
            except Exception as e:  # noqa: BLE001
                raise StageError(f"采集失败: {e}") from e
            reviews = result["reviews"]
            ctx.save("raw_reviews", [r.model_dump() for r in reviews])
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
