"""App Store 数据采集。

数据源说明（合法、优于抓取页面可见内容）：
- iTunes Lookup API：应用元数据（名称、版本、评分分布等）
  GET https://itunes.apple.com/lookup?id={APP_ID}&country=us&entity=software
- Apple 官方客户评论 RSS Feed（JSON 格式）：评论正文
  GET https://itunes.apple.com/{country}/rss/customerreviews/page={N}/id={APP_ID}/sortBy=mostRecent/json
  注意：page 必须为路径参数；作为 query（?page=N）会被忽略并返回同一批数据。

局限（结果中如实标注）：
- 无认证、每页 50 条、最多约 10 页（约 500 条），仅覆盖近期评论；
- 无分页总量元数据，无法获知评论总数；
- 字段（版本、评分等）以 feed 实际返回为准。
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Optional

import httpx

from ..config import settings
from ..schemas import RawReview

logger = logging.getLogger(__name__)

APP_ID_RE = re.compile(r"/id(\d{6,})", re.IGNORECASE)
COUNTRY_RE = re.compile(r"/([a-z]{2})/app/", re.IGNORECASE)


class AppStoreError(Exception):
    pass


def parse_app_url(url: str) -> tuple[str, str]:
    """从 App Store 链接提取 (app_id, country)。"""
    if not url or "apps.apple.com" not in url:
        raise AppStoreError("链接不是有效的 App Store 链接")
    m = APP_ID_RE.search(url)
    if not m:
        raise AppStoreError("无法从链接中解析出应用 ID（需包含 /idxxxxx）")
    app_id = m.group(1)
    m2 = COUNTRY_RE.search(url)
    country = m2.group(1).lower() if m2 else "us"
    return app_id, country


async def lookup_app(
    app_id: str, country: str = "us", client: Optional[httpx.AsyncClient] = None
) -> dict:
    """获取应用元数据（名称、当前版本、评分分布等）。"""
    params = {"id": app_id, "country": country, "entity": "software"}
    own = client is None
    c = client or httpx.AsyncClient(timeout=settings.collect_timeout)
    try:
        resp = await c.get("https://itunes.apple.com/lookup", params=params)
        resp.raise_for_status()
        data = resp.json()
    finally:
        if own:
            await c.aclose()
    results = data.get("results") or []
    if not results:
        raise AppStoreError(f"未找到应用 id={app_id}（country={country}）")
    return results[0]


def _entry_to_review(entry: dict, country: str, source: str = "rss") -> RawReview:
    """将 RSS feed 的 entry 映射为 RawReview（支持嵌套 label 结构）。"""
    def _get(*path: str) -> str:
        v: object = entry
        for k in path:
            if isinstance(v, dict):
                v = v.get(k)
            else:
                return ""
        if isinstance(v, dict):
            return str(v.get("label") or "")
        return str(v or "")

    try:
        rating = int(float(_get("im:rating") or 0))
    except (TypeError, ValueError):
        rating = 0
    rating = max(1, min(5, rating)) if rating else 0
    return RawReview(
        review_id=_get("id") or f"{source}_{abs(hash(_get('content')))}",
        title=_get("title"),
        content=_get("content"),
        rating=rating,
        version=_get("im:version") or None,
        date=_get("updated") or None,
        author=_get("author", "name") or None,
        country=country,
        source=source,
    )


async def fetch_reviews(
    app_id: str,
    country: str = "us",
    max_pages: int | None = None,
    interval: float | None = None,
    client: Optional[httpx.AsyncClient] = None,
) -> dict:
    """通过 Apple 官方 RSS Review Feed 分页采集评论。

    返回: {"reviews": [RawReview...], "errors": [...], "pages_fetched": int,
           "total": int, "limitations": [...]}
    """
    max_pages = max_pages or settings.collect_max_pages
    interval = settings.collect_interval if interval is None else interval
    reviews: list[RawReview] = []
    errors: list[str] = []
    pages_fetched = 0
    own = client is None
    c = client or httpx.AsyncClient(timeout=settings.collect_timeout)
    try:
        for page in range(1, max_pages + 1):
            # 注意：page 必须作为路径参数（?page=N 会被忽略，返回同一批数据）
            url = (
                f"https://itunes.apple.com/{country}/rss/customerreviews/"
                f"page={page}/id={app_id}/sortBy=mostRecent/json"
            )
            try:
                resp = await c.get(url)
                if resp.status_code == 429:
                    errors.append(f"page {page}: rate limited (429)")
                    await asyncio.sleep(min(30, 2 ** page))
                    continue
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:  # noqa: BLE001
                errors.append(f"page {page}: {e}")
                break
            entries = (data.get("feed") or {}).get("entry") or []
            if not entries:
                break
            for e in entries:
                if "im:rating" not in e:
                    continue
                r = _entry_to_review(e, country)
                if r.rating:
                    reviews.append(r)
            pages_fetched += 1
            if len(entries) < 50:
                break
            await asyncio.sleep(interval)
    finally:
        if own:
            await c.aclose()

    return {
        "reviews": reviews,
        "errors": errors,
        "pages_fetched": pages_fetched,
        "total": len(reviews),
        "limitations": [
            f"Apple RSS Feed 每页最多 50 条，最多采集 {max_pages} 页（约 {max_pages * 50} 条），仅覆盖近期评论",
            "采集存在速率限制，部分页失败时已如实记录",
        ],
    }
