"""数据清洗与去重（确定性规则，可解释、可复现）。

- 字段标准化：评分、日期、HTML 实体、控制字符、多余空白
- 精确去重：规范化文本 hash
- 近似去重：分片 Jaccard 相似度 >= 阈值（默认 0.85）
- 语言识别：轻量 langdetect（可离线），失败时标记 unknown

为何用规则而非模型：
  去重/标准化是确定性问题，规则结果可复现、可审计、无幻觉风险且零成本。
"""
from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from collections import Counter

from ..config import settings
from ..schemas import RawReview, Review

# --------------------------------------------------------------------------
# 文本规范化
# --------------------------------------------------------------------------
_EMOJI_RE = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F0FF\U0001F900-\U0001F9FF]"
)
_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[\W_]+", re.UNICODE)


def normalize_text(text: str) -> str:
    """用于去重比较的规范化文本：去 emoji、标点、空白、大小写归一。"""
    if not text:
        return ""
    t = unicodedata.normalize("NFKC", text)
    t = html.unescape(t)
    t = _EMOJI_RE.sub(" ", t)
    t = _PUNCT_RE.sub(" ", t)
    t = _WS_RE.sub(" ", t)
    return t.strip().lower()


def _shingles(text: str, k: int = 3) -> set[str]:
    """生成 k 字符分片。"""
    return {text[i : i + k] for i in range(len(text) - k + 1)}


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# --------------------------------------------------------------------------
# 清洗
# --------------------------------------------------------------------------
def clean_review(raw: RawReview) -> Review:
    content = raw.content or ""
    title = raw.title or ""
    # 去控制字符、HTML 标签与实体，压缩空白
    content = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", " ", content)
    content = re.sub(r"<[^>]+>", " ", content)
    content = html.unescape(content)
    content = _WS_RE.sub(" ", content).strip()
    title = re.sub(r"<[^>]+>", " ", title)
    title = _WS_RE.sub(" ", html.unescape(title)).strip()

    rating = raw.rating
    if not (1 <= rating <= 5):
        rating = 0

    review = Review(
        review_id=raw.review_id,
        title=title,
        content=content,
        rating=rating,
        version=(raw.version or "").strip() or None,
        lang=raw.lang,
        country=raw.country,
        date=raw.date,
        author=raw.author,
        source=raw.source,
        normalized_content=normalize_text(f"{title} {content}"),
    )
    return review


def detect_lang(review: Review) -> str:
    """轻量语言识别；失败/过短时返回 unknown。"""
    text = (review.content or "")[:500]
    if len(text) < 20:
        return "unknown"
    try:
        from langdetect import detect  # 延迟导入，避免强制依赖

        return detect(text)
    except Exception:  # noqa: BLE001
        return "unknown"


# --------------------------------------------------------------------------
# 去重
# --------------------------------------------------------------------------
def deduplicate(reviews: list[Review], threshold: float | None = None) -> list[Review]:
    """先精确去重，再近似去重。返回全部评论（重复项 is_duplicate=True 并记 dup_group）。"""
    threshold = settings.dedup_threshold if threshold is None else threshold
    exact_seen: set[str] = set()
    groups: list[dict] = []  # {"shingles": set, "group_id": str}

    # 1) 精确去重
    for r in reviews:
        norm = r.normalized_content
        if not norm:
            continue
        h = hashlib.sha256(norm.encode("utf-8")).hexdigest()
        if h in exact_seen:
            r.is_duplicate = True
        else:
            exact_seen.add(h)

    # 2) 近似去重：贪心聚类（按规范化长度降序，长文本更可靠）
    candidates = [r for r in reviews if not r.is_duplicate]
    candidates.sort(key=lambda r: len(r.normalized_content), reverse=True)
    for r in candidates:
        norm = r.normalized_content
        if len(norm) < 40:  # 过短不参与近似去重，避免误伤
            continue
        shingles = _shingles(norm)
        matched = None
        for g in groups:
            if jaccard(shingles, g["shingles"]) >= threshold:
                matched = g
                break
        if matched is not None:
            r.is_duplicate = True
            r.dup_group = matched["group_id"]
        else:
            group_id = f"g{len(groups) + 1:03d}"
            groups.append({"shingles": shingles, "group_id": group_id})
            r.dup_group = group_id

    # 保持原始顺序
    order = {id(r): i for i, r in enumerate(reviews)}
    return sorted(reviews, key=lambda r: order[id(r)])


def clean_pipeline(
    raw_reviews: list[RawReview],
    on_step=None,
) -> dict:
    """完整清洗流程：清洗 -> 语言识别 -> 去重。返回数据 + 报告。

    on_step: 可选同步回调 on_step(percent, message)，用于上报清洗进度（不 await）。
    """
    if on_step is not None:
        on_step(15, f"正在标准化与清洗 {len(raw_reviews)} 条评论")
    reviews = [clean_review(r) for r in raw_reviews]

    # 语言识别（仅对 lang 未知的）
    lang_counter: Counter = Counter()
    for r in reviews:
        if not r.lang or r.lang == "unknown":
            r.lang = detect_lang(r)
        if r.lang:
            lang_counter[r.lang] += 1
    if on_step is not None:
        on_step(55, "正在识别评论语言")

    before = len(reviews)
    deduped = deduplicate(reviews)
    dup_count = sum(1 for r in deduped if r.is_duplicate)
    kept = [r for r in deduped if not r.is_duplicate]
    if on_step is not None:
        on_step(85, f"正在去重（{before} → 保留 {len(kept)} 条）")

    report = {
        "input_count": before,
        "kept_count": len(kept),
        "duplicate_count": dup_count,
        "lang_distribution": dict(lang_counter.most_common()),
        "field_missing": {
            "version": sum(1 for r in kept if not r.version),
            "date": sum(1 for r in kept if not r.date),
            "author": sum(1 for r in kept if not r.author),
        },
    }
    return {"reviews": deduped, "kept": kept, "report": report}
