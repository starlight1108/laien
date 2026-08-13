"""核心数据模型（Pydantic v2）。

所有阶段产物均以这些模型序列化为 JSON 落盘，保证可读、可校验、可追溯。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------
# 评论
# --------------------------------------------------------------------------
class RawReview(BaseModel):
    """采集/导入的原始评论（尚未清洗）。"""

    review_id: str
    title: str = ""
    content: str = ""
    rating: int = Field(ge=1, le=5)
    version: Optional[str] = None
    lang: Optional[str] = None
    country: Optional[str] = None
    date: Optional[str] = None
    author: Optional[str] = None
    source: str = "import"  # rss / import


class Review(RawReview):
    """清洗、去重、结构化后的评论。"""

    normalized_content: str = ""
    is_duplicate: bool = False
    dup_group: Optional[str] = None


# --------------------------------------------------------------------------
# 运行与阶段
# --------------------------------------------------------------------------
StageStatus = Literal[
    "pending", "running", "succeeded", "failed", "degraded", "revised", "skipped"
]


class StageResult(BaseModel):
    stage: str
    label: str = ""
    status: StageStatus = "pending"
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error: Optional[str] = None
    summary: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[str] = Field(default_factory=list)
    revisions: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# 发现 / 主题
# --------------------------------------------------------------------------
Confidence = Literal["high", "medium", "low"]


class Finding(BaseModel):
    """重大发现：必须携带证据、样本数、置信度、冲突证据，并区分模型/统计。"""

    id: str
    title: str
    summary: str
    kind: Literal["model_derived", "deterministic_stat"]
    evidence_review_ids: list[str] = Field(default_factory=list)
    supporting_count: int = 0
    confidence: Confidence = "medium"
    conflicting_review_ids: list[str] = Field(default_factory=list)
    uncertainty: Optional[str] = None
    assumption: bool = False
    source: str = ""


class Theme(BaseModel):
    id: str
    title: str
    description: str = ""
    review_ids: list[str] = Field(default_factory=list)
    confidence: Confidence = "medium"
    sentiment: Optional[str] = None  # positive / negative / mixed


# --------------------------------------------------------------------------
# PRD
# --------------------------------------------------------------------------
Priority = Literal["P0", "P1", "P2"]


class Requirement(BaseModel):
    id: str
    title: str
    description: str = ""
    priority: Priority = "P2"
    version: str = "V1"
    boundaries: str = ""
    finding_ids: list[str] = Field(default_factory=list)
    review_ids: list[str] = Field(default_factory=list)
    assumption: bool = False


class UpdatePlan(BaseModel):
    summary: str = ""
    versions: list[dict[str, Any]] = Field(default_factory=list)


class PRD(BaseModel):
    requirements: list[Requirement] = Field(default_factory=list)
    update_plan: UpdatePlan = Field(default_factory=UpdatePlan)


# --------------------------------------------------------------------------
# 测试用例
# --------------------------------------------------------------------------
class TestCase(BaseModel):
    id: str
    requirement_id: str
    review_ids: list[str] = Field(default_factory=list)
    preconditions: str = ""
    steps: list[str] = Field(default_factory=list)
    expected: str = ""
    verifies_issue: str = ""


# --------------------------------------------------------------------------
# 证据评估 / 追溯验证
# --------------------------------------------------------------------------
class EvidenceItem(BaseModel):
    finding_id: str
    status: str = "insufficient"  # sufficient / insufficient / conflicting
    supporting_count: int = 0
    coverage: Optional[str] = None
    note: str = ""


class EvidenceReport(BaseModel):
    items: list[EvidenceItem] = Field(default_factory=list)
    data_limitations: list[str] = Field(default_factory=list)
    overall: str = ""


class TraceabilityCheck(BaseModel):
    item_type: str  # finding / requirement / test_case
    item_id: str
    ok: bool = True
    issues: list[str] = Field(default_factory=list)
    action: str = "keep"  # keep / revised / removed / assumption


class TraceabilityReport(BaseModel):
    checks: list[TraceabilityCheck] = Field(default_factory=list)
    summary: dict[str, int] = Field(default_factory=dict)
    revisions: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# 运行元数据
# --------------------------------------------------------------------------
class RunMeta(BaseModel):
    run_id: str
    app_id: Optional[str] = None
    app_name: Optional[str] = None
    url: Optional[str] = None
    goal: str = ""
    provider: Optional[str] = None
    model: Optional[str] = None
    status: str = "pending"  # pending / running / succeeded / failed / degraded
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: Optional[datetime] = None
    cache: bool = False
    cache_note: Optional[str] = None
    source: str = "url"  # url / import
    stages: list[StageResult] = Field(default_factory=list)
