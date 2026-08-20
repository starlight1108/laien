"""阶段 4：动态分类与分析（模型驱动核心）。

流程：
1. 确定性统计层（代码计算，权威数字）
2. 批次语义标注：LLM 从评论中动态归纳主题（无预设分类）
3. 批次主题整合：多批结果合并去重（LLM）
4. 模型发现生成：基于主题与证据产出发现（LLM，kind=model_derived）
5. 确定性统计发现（代码生成，kind=deterministic_stat）
6. 复核：代码校验 review_ids 真实性、supporting_count 与证据数一致并修订

结论类型明确区分：模型结论 vs 确定性统计（kind 字段）。
"""
from __future__ import annotations

import json
import logging

from ...config import settings
from ...llm.prompts import (
    ANALYZE_SYSTEM,
    ANALYZE_USER_TEMPLATE,
    FINDINGS_SYSTEM,
    FINDINGS_USER_TEMPLATE,
    MERGE_THEMES_SYSTEM,
    _GROUNDING_RULES,
)
from ...schemas import Review
from ...services.stats import summary_stats
from ..orchestrator import BaseStage, RunContext, StageError

logger = logging.getLogger(__name__)

THEMES_SCHEMA = {
    "name": "themes_result",
    "schema": {
        "type": "object",
        "properties": {
            "themes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "review_ids": {"type": "array", "items": {"type": "string"}},
                        "sentiment": {"type": "string", "enum": ["negative", "positive", "mixed"]},
                        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                    },
                    "required": ["id", "title", "description", "review_ids", "sentiment", "confidence"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["themes"],
        "additionalProperties": False,
    },
}

FINDINGS_SCHEMA = {
    "name": "findings_result",
    "schema": {
        "type": "object",
        "properties": {
            "findings": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "title": {"type": "string"},
                        "summary": {"type": "string"},
                        "kind": {"type": "string", "enum": ["model_derived"]},
                        "evidence_review_ids": {"type": "array", "items": {"type": "string"}},
                        "supporting_count": {"type": "integer"},
                        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                        "conflicting_review_ids": {"type": "array", "items": {"type": "string"}},
                        "uncertainty": {"type": "string"},
                        "assumption": {"type": "boolean"},
                    },
                    "required": [
                        "id", "title", "summary", "kind", "evidence_review_ids",
                        "supporting_count", "confidence", "conflicting_review_ids",
                        "uncertainty", "assumption",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["findings"],
        "additionalProperties": False,
    },
}


def _compact(reviews: list[dict], limit: int = 300) -> list[dict]:
    """精简评论（截断正文）以控制 token。"""
    out = []
    for r in reviews:
        content = (r.get("content") or "")[:limit]
        out.append(
            {
                "review_id": r.get("review_id"),
                "title": (r.get("title") or "")[:80],
                "content": content,
                "rating": r.get("rating"),
                "version": r.get("version"),
            }
        )
    return out


class AnalyzeStage(BaseStage):
    name = "analyze"
    label = "4. 动态分类与分析"

    async def execute(self, ctx: RunContext) -> dict:
        if ctx.llm is None:
            raise StageError(
                "未配置 LLM（缺少模型或 API Key），无法执行模型驱动语义分析；"
                "请在输入页选择模型并填写 Key，或使用缓存运行查看示例结果",
                degraded=True,
            )

        cleaned = ctx.load("cleaned_reviews") or []
        kept = [r for r in cleaned if not r.get("is_duplicate")]
        if not kept:
            raise StageError("清洗后无可用评论数据（请检查数据来源）")

        goal = ctx.goal() or "整体用户问题"
        stats = summary_stats([Review(**r) for r in kept])

        # ---------- 1) 批次主题发现 ----------
        batch_size = settings.llm_batch_size
        batches = [kept[i : i + batch_size] for i in range(0, len(kept), batch_size)]
        n_batches = len(batches)
        all_themes: list[dict] = []
        stats_json = json.dumps(stats, ensure_ascii=False)

        # 子步骤清单：每个批次 + 后续关键步骤，前端据此展示批次级进度
        substeps: list[dict] = [
            {"label": f"批次 {i + 1} 主题发现", "status": "pending"}
            for i in range(n_batches)
        ]
        substeps += [
            {"label": "主题整合", "status": "pending"},
            {"label": "模型发现生成", "status": "pending"},
            {"label": "确定性统计发现", "status": "pending"},
            {"label": "证据复核", "status": "pending"},
        ]
        IDX_MERGE = n_batches
        IDX_FINDINGS = n_batches + 1
        IDX_STAT = n_batches + 2
        IDX_REVIEW = n_batches + 3
        ctx.report_progress(0, "准备分析", substeps)

        for idx, batch in enumerate(batches):
            substeps[idx]["status"] = "running"
            ctx.report_progress(
                int(idx / max(n_batches, 1) * 40),
                f"正在分析批次 {idx + 1}/{n_batches}（{len(batch)} 条评论）",
                substeps,
            )
            user = ANALYZE_USER_TEMPLATE.format(
                goal=goal,
                stats=stats_json,
                batch_index=idx + 1,
                batch_count=n_batches,
                batch_size=len(batch),
                reviews_json=json.dumps(_compact(batch), ensure_ascii=False),
            )
            data = await ctx.llm_call(ANALYZE_SYSTEM, user, schema=THEMES_SCHEMA)
            all_themes.extend(data.get("themes", []) or [])
            substeps[idx]["status"] = "succeeded"
            ctx.report_progress(
                int((idx + 1) / max(n_batches, 1) * 40),
                f"批次 {idx + 1} 完成",
                substeps,
            )

        # ---------- 2) 多批主题整合 ----------
        if n_batches > 1 and all_themes:
            substeps[IDX_MERGE]["status"] = "running"
            ctx.report_progress(45, "正在整合多批主题聚类结果", substeps)
            user = (
                "【分析目标】\n" + goal
                + "\n\n【各批次主题聚类结果】\n"
                + json.dumps(all_themes, ensure_ascii=False)
                + "\n\n请合并语义重复的主题，输出整合后的全局主题集。"
            )
            data = await ctx.llm_call(MERGE_THEMES_SYSTEM, user, schema=THEMES_SCHEMA)
            all_themes = data.get("themes", []) or []
            substeps[IDX_MERGE]["status"] = "succeeded"

        # ---------- 3) 校验主题引用的 review_id ----------
        ctx.report_progress(55, "正在校验主题引用的评论", substeps)
        valid_ids = {r["review_id"] for r in kept}
        for t in all_themes:
            t["review_ids"] = [rid for rid in t.get("review_ids", []) if rid in valid_ids]
        # 重编号
        for i, t in enumerate(all_themes, 1):
            t["id"] = f"T-{i:02d}"
        ctx.save("themes", all_themes)

        # ---------- 4) 模型发现生成 ----------
        model_findings: list[dict] = []
        if all_themes:
            substeps[IDX_FINDINGS]["status"] = "running"
            ctx.report_progress(65, "正在基于主题生成模型发现", substeps)
            # 为每个主题收集代表评论（控制 token）
            theme_reviews: dict[str, list[dict]] = {}
            for t in all_themes:
                rid_set = set(t.get("review_ids", []))
                theme_reviews[t["id"]] = [r for r in kept if r["review_id"] in rid_set][:8]
            user = FINDINGS_USER_TEMPLATE.format(
                goal=goal,
                themes_json=json.dumps(all_themes, ensure_ascii=False),
                reviews_json=json.dumps(
                    {
                        k: _compact(v, limit=220)
                        for k, v in theme_reviews.items()
                    },
                    ensure_ascii=False,
                ),
            )
            data = await ctx.llm_call(FINDINGS_SYSTEM, user, schema=FINDINGS_SCHEMA)
            model_findings = data.get("findings", []) or []
            for i, f in enumerate(model_findings, 1):
                f["id"] = f"F-{i:02d}"
                f["source"] = "analyze_stage"
            substeps[IDX_FINDINGS]["status"] = "succeeded"

        # ---------- 5) 确定性统计发现（代码生成） ----------
        substeps[IDX_STAT]["status"] = "running"
        ctx.report_progress(85, "正在生成确定性统计发现", substeps)
        stat_findings = self._stat_findings(kept, stats, valid_ids, len(model_findings))
        substeps[IDX_STAT]["status"] = "succeeded"

        # ---------- 6) 复核：ID 真实性 + supporting_count 一致性 ----------
        substeps[IDX_REVIEW]["status"] = "running"
        ctx.report_progress(92, "正在复核证据引用与数量一致性", substeps)
        revisions: list[str] = []
        findings = stat_findings + model_findings
        for f in findings:
            f["evidence_review_ids"] = [
                rid for rid in f.get("evidence_review_ids", []) if rid in valid_ids
            ]
            if f["kind"] == "model_derived":
                expected = len(f["evidence_review_ids"])
                if f.get("supporting_count", 0) != expected:
                    revisions.append(
                        f"{f['id']}: supporting_count {f.get('supporting_count')} "
                        f"修订为证据数 {expected}（确定性复核）"
                    )
                    f["supporting_count"] = expected
            f["conflicting_review_ids"] = [
                rid for rid in f.get("conflicting_review_ids", []) if rid in valid_ids
            ]
        # 只有模型发现才有 assumption 字段语义；统计发现强制 assumption=False
        for f in stat_findings:
            f["assumption"] = False

        substeps[IDX_REVIEW]["status"] = "succeeded"
        ctx.report_progress(100, f"分析完成：{len(findings)} 项发现", substeps)
        ctx.save("findings", findings)
        self.revisions = revisions
        return {
            "themes_count": len(all_themes),
            "findings_count": len(findings),
            "model_findings": len(model_findings),
            "stat_findings": len(stat_findings),
            "revisions": revisions,
            "stats": stats,
        }

    # ------------------------------------------------------------------
    @staticmethod
    def _stat_findings(kept: list[dict], stats: dict, valid_ids: set[str], start_idx: int) -> list[dict]:
        """确定性统计发现：仅基于代码统计，不依赖模型。"""
        findings: list[dict] = []
        idx = start_idx
        dist = stats.get("rating_distribution", {})
        low = int(dist.get("2", 0)) + int(dist.get("1", 0))
        high = int(dist.get("4", 0)) + int(dist.get("5", 0))
        if low > 0:
            idx += 1
            ids = [r["review_id"] for r in kept if r.get("rating") and r["rating"] <= 2][:20]
            findings.append({
                "id": f"F-{idx:02d}",
                "title": f"低分评论占比 {low}/{stats['total']}（确定性统计）",
                "summary": f"共有 {low} 条 1-2 星评论，占总评论 {stats['total']} 条的 "
                           f"{round(low / max(stats['total'], 1) * 100, 1)}%。",
                "kind": "deterministic_stat",
                "evidence_review_ids": ids,
                "supporting_count": low,
                "confidence": "high",
                "conflicting_review_ids": [r["review_id"] for r in kept
                                           if r.get("rating") and r["rating"] >= 4][:5],
                "uncertainty": "仅反映评分分布，不涉及具体原因（原因分析见模型结论）",
                "assumption": False,
                "source": "stats",
            })
        if high > 0:
            idx += 1
            findings.append({
                "id": f"F-{idx:02d}",
                "title": f"高评分评论占比 {high}/{stats['total']}（确定性统计）",
                "summary": f"共有 {high} 条 4-5 星评论，占总评论 {stats['total']} 条的 "
                           f"{round(high / max(stats['total'], 1) * 100, 1)}%。",
                "kind": "deterministic_stat",
                "evidence_review_ids": [r["review_id"] for r in kept
                                        if r.get("rating") and r["rating"] >= 4][:20],
                "supporting_count": high,
                "confidence": "high",
                "conflicting_review_ids": [r["review_id"] for r in kept
                                           if r.get("rating") and r["rating"] <= 2][:5],
                "uncertainty": None,
                "assumption": False,
                "source": "stats",
            })
        return findings
