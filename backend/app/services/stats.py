"""确定性统计服务：所有统计由代码计算，权威且可复现。

模型结论不得改写这些数字；阶段 4 的复核也基于此。
"""
from __future__ import annotations

from collections import Counter
from typing import Iterable

from ..schemas import Review


def rating_distribution(reviews: Iterable[Review]) -> dict[str, int]:
    counts = Counter(r.rating for r in reviews if r.rating)
    return {str(i): counts.get(i, 0) for i in range(1, 6)}


def version_distribution(reviews: Iterable[Review], top_n: int = 10) -> dict[str, int]:
    counts = Counter((r.version or "unknown") for r in reviews)
    return dict(counts.most_common(top_n))


def lang_distribution(reviews: Iterable[Review]) -> dict[str, int]:
    counts = Counter((r.lang or "unknown") for r in reviews)
    return dict(counts.most_common())


def low_rating_reviews(reviews: Iterable[Review], max_rating: int = 2) -> list[Review]:
    return [r for r in reviews if r.rating and r.rating <= max_rating]


def high_rating_reviews(reviews: Iterable[Review], min_rating: int = 4) -> list[Review]:
    return [r for r in reviews if r.rating and r.rating >= min_rating]


def reviews_by_version(reviews: Iterable[Review], version: str) -> list[Review]:
    return [r for r in reviews if (r.version or "") == version]


def summary_stats(reviews: Iterable[Review]) -> dict:
    reviews = list(reviews)
    total = len(reviews)
    ratings = [r.rating for r in reviews if r.rating]
    avg = round(sum(ratings) / len(ratings), 2) if ratings else 0.0
    dates = [r.date for r in reviews if r.date]
    return {
        "total": total,
        "avg_rating": avg,
        "low_rating_count": len(low_rating_reviews(reviews)),
        "high_rating_count": len(high_rating_reviews(reviews)),
        "with_version": sum(1 for r in reviews if r.version),
        "date_min": min(dates) if dates else None,
        "date_max": max(dates) if dates else None,
        "rating_distribution": rating_distribution(reviews),
    }
