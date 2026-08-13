"""阶段 1：确定分析范围。

依据用户目标 + 可用数据（元数据、评论规模）确定分析范围。
确定性规则：解析目标约束、解析链接、拉取应用元数据。
"""
from __future__ import annotations

import logging

from ..orchestrator import BaseStage, RunContext, StageError
from ...services.appstore import AppStoreError, lookup_app, parse_app_url

logger = logging.getLogger(__name__)


class ScopeStage(BaseStage):
    name = "scope"
    label = "1. 确定分析范围"

    async def execute(self, ctx: RunContext) -> dict:
        meta = ctx.meta
        result: dict = {"scope": ctx.scope_for_goal(ctx.goal())}

        if meta.source == "url" and meta.url:
            try:
                app_id, country = parse_app_url(meta.url)
            except AppStoreError as e:
                raise StageError(str(e)) from e
            meta.app_id = app_id
            result["app_id"] = app_id
            result["country"] = country
            # 拉取应用元数据（失败不阻塞，如实记录）
            try:
                info = await lookup_app(app_id, country)
                meta.app_name = info.get("trackName")
                result["app_name"] = info.get("trackName")
                result["current_version"] = info.get("version")
                result["avg_rating"] = info.get("averageUserRating")
                result["rating_count"] = info.get("userRatingCount")
                result["primary_genre"] = info.get("primaryGenreName")
            except AppStoreError as e:
                result["metadata_error"] = str(e)
            except Exception as e:  # noqa: BLE001
                result["metadata_error"] = f"{type(e).__name__}: {e}"

        ctx.save("scope", result)
        return result
