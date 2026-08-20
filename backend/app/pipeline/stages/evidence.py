"""阶段 5：证据充分性评估（确定性规则 + 统计）。

- 每个发现：证据量是否达阈值、是否有冲突证据
- 数据局限：如实报告样本量、版本覆盖、语言分布、采集受限
- 不伪造数据
"""
from __future__ import annotations

from ...config import settings
from ...schemas import EvidenceItem, EvidenceReport
from ..orchestrator import BaseStage, RunContext


class EvidenceStage(BaseStage):
    name = "evidence"
    label = "5. 证据充分性评估"

    async def execute(self, ctx: RunContext) -> dict:
        findings = ctx.load("findings") or []
        cleaned = ctx.load("cleaned_reviews") or []
        clean_report = ctx.load("clean_report") or {}
        kept = [r for r in cleaned if not r.get("is_duplicate")]

        items: list[EvidenceItem] = []
        for i, f in enumerate(findings):
            ctx.report_progress(
                int((i + 1) / max(len(findings), 1) * 80),
                f"正在评估发现 {f.get('id', '')} 的证据充分性",
            )
            count = f.get("supporting_count", 0)
            conflicts = f.get("conflicting_review_ids") or []
            if f.get("assumption"):
                status = "insufficient"
                note = "该结论已标注为假设，缺乏直接证据支撑"
            elif conflicts:
                status = "conflicting"
                note = f"存在 {len(conflicts)} 条冲突证据，需谨慎解读"
            elif count >= settings.min_supporting_count:
                status = "sufficient"
                note = f"支持样本 {count} 条，达到阈值 {settings.min_supporting_count}"
            else:
                status = "insufficient"
                note = f"支持样本仅 {count} 条，低于阈值 {settings.min_supporting_count}，证据不足"

            # 版本覆盖评估
            versions = {r.get("version") for r in kept if r.get("version")}
            coverage = (
                f"覆盖版本数: {len(versions)}（{', '.join(sorted(versions)[:5])}{'…' if len(versions) > 5 else ''}）"
                if versions
                else "无版本信息"
            )
            items.append(
                EvidenceItem(
                    finding_id=f.get("id", ""),
                    status=status,
                    supporting_count=count,
                    coverage=coverage,
                    note=note,
                )
            )

        total = clean_report.get("input_count", 0)
        kept_count = clean_report.get("kept_count", 0)
        lang_dist = clean_report.get("lang_distribution", {})
        limitations = [
            f"本次共处理 {total} 条原始评论，去重后保留 {kept_count} 条",
            f"语言分布: {lang_dist or 'unknown'}",
            "Apple RSS Feed 仅覆盖近期评论，最多约 500 条，可能不反映全部用户",
            "模型结论仅基于已提供评论，不涉及未采集到的时间段或平台",
        ]
        insufficient = sum(1 for it in items if it.status == "insufficient")
        conflicting = sum(1 for it in items if it.status == "conflicting")
        overall = (
            f"共 {len(items)} 项发现：证据充分 {len(items) - insufficient - conflicting} 项，"
            f"证据不足 {insufficient} 项，存在冲突 {conflicting} 项。"
            f"{'（数据量有限或约束生效，部分结论不确定性较高）' if insufficient else ''}"
        )
        ctx.report_progress(100, "证据评估完成")
        report = EvidenceReport(
            items=items, data_limitations=limitations, overall=overall
        ).model_dump()
        ctx.save("evidence_report", report)
        return report
