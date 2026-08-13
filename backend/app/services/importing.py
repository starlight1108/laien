"""导入数据解析：JSON / CSV 文本 -> list[dict]（RawReview 兼容）。

文档化格式：
- JSON: 数组或对象，每条含必填 id/title/content/rating，可选 version/lang/country/date/author
- CSV: 表头 id,title,content,rating,version,lang,country,date,author（UTF-8）
"""
from __future__ import annotations

import csv
import io
import json

REQUIRED_FIELDS = ("id", "title", "content", "rating")


class ImportError_(Exception):
    pass


def normalize_import_item(item: dict, index: int) -> dict:
    """对外导出：规范化单条导入数据（兼容 id/review_id，校验必填字段）。"""
    return _normalize(item, index)


def parse_import_text(text: str) -> list[dict]:
    """自动识别 JSON 或 CSV。"""
    if not text or not text.strip():
        raise ImportError_("导入内容为空")
    stripped = text.lstrip()
    if stripped.startswith(("[", "{")):
        return parse_json(text)
    return parse_csv(text)


def parse_json(text: str) -> list[dict]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise ImportError_(f"JSON 解析失败: {e}") from e
    if isinstance(data, dict):
        # 兼容 {"reviews": [...]} 包裹
        if "reviews" in data and isinstance(data["reviews"], list):
            data = data["reviews"]
        else:
            data = [data]
    if not isinstance(data, list):
        raise ImportError_("JSON 顶层应为数组或包含 reviews 数组的对象")
    out = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            raise ImportError_(f"第 {i + 1} 条不是对象")
        out.append(_normalize(item, i))
    return out


def parse_csv(text: str) -> list[dict]:
    try:
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
    except Exception as e:  # noqa: BLE001
        raise ImportError_(f"CSV 解析失败: {e}") from e
    if not rows:
        raise ImportError_("CSV 无数据行")
    out = []
    for i, row in enumerate(rows):
        out.append(_normalize({k: (v or "") for k, v in row.items()}, i))
    return out


def _normalize(item: dict, index: int) -> dict:
    # 兼容 id / review_id 字段名
    out = dict(item)
    if "review_id" in out and "id" not in out:
        out["id"] = out["review_id"]
    for field in REQUIRED_FIELDS:
        val = out.get(field)
        if val is None or str(val).strip() == "":
            raise ImportError_(f"第 {index + 1} 条缺少必填字段 '{field}'")
    # rating 规范化
    try:
        rating = int(float(out["rating"]))
    except (TypeError, ValueError) as e:
        raise ImportError_(f"第 {index + 1} 条 rating 非法: {out['rating']}") from e
    if not 1 <= rating <= 5:
        raise ImportError_(f"第 {index + 1} 条 rating 超出 1-5: {rating}")
    out["rating"] = rating
    out["review_id"] = str(out["id"])
    out.pop("id", None)
    return out
