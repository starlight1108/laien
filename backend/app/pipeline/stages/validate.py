"""阶段 8：可追溯性验证（确定性规则，最后的防线）。

校验链路：评论 -> 发现 -> 需求 -> 测试用例
- 所有引用 ID 必须真实存在
- 无需求覆盖的发现 / 无发现的孤立需求 / 孤儿用例 -> 报告
- 不支持的结论 -> 修订或标注 assumption
"""
from __future__ import annotations

import logging

from ...schemas import TraceabilityCheck, TraceabilityReport
from ..orchestrator import BaseStage, RunContext

logger = logging.getLogger(__name__)


class ValidateStage(BaseStage):
    name = "validate"
    label = "8. 可追溯性验证"

    async def execute(self, ctx: RunContext) -> dict:
        cleaned = ctx.load("cleaned_reviews") or []
        findings = ctx.load("findings") or []
        prd = ctx.load("prd") or {}
        requirements = prd.get("requirements", []) or []
        test_cases = ctx.load("test_cases") or []

        valid_review_ids = {r["review_id"] for r in cleaned}
        checks: list[TraceabilityCheck] = []
        revisions: list[str] = []

        # ---- 1) 发现：证据引用真实 + 数量一致 ----
        for f in findings:
            issues = []
            fake_ids = [rid for rid in f.get("evidence_review_ids", []) if rid not in valid_review_ids]
            if fake_ids:
                issues.append(f"引用不存在的评论: {fake_ids[:5]}")
            if f.get("supporting_count", 0) != len(f.get("evidence_review_ids", [])):
                issues.append(
                    f"supporting_count({f.get('supporting_count')}) 与证据数"
                    f"({len(f.get('evidence_review_ids', []))}) 不一致"
                )
                f["supporting_count"] = len(f.get("evidence_review_ids", []))
                revisions.append(f"{f['id']}: supporting_count 已按证据数修订")
            checks.append(
                TraceabilityCheck(
                    item_type="finding", item_id=f.get("id", ""),
                    ok=not issues, issues=issues,
                    action="keep" if not issues else "revised",
                )
            )

        # ---- 2) 需求：引用发现与评论 ----
        finding_ids = {f["id"] for f in findings}
        req_finding_used: set[str] = set()
        for r in requirements:
            issues = []
            fake_fids = [fid for fid in r.get("finding_ids", []) if fid not in finding_ids]
            fake_rids = [rid for rid in r.get("review_ids", []) if rid not in valid_review_ids]
            if fake_fids:
                issues.append(f"引用不存在的发现: {fake_fids[:5]}")
            if fake_rids:
                issues.append(f"引用不存在的评论: {fake_rids[:5]}")
            if not r.get("finding_ids") or not r.get("review_ids"):
                if not r.get("assumption"):
                    r["assumption"] = True
                    revisions.append(f"{r['id']}: 无有效证据引用，已标注为假设")
                issues.append("无有效证据引用（已标注为假设）")
            req_finding_used.update(r.get("finding_ids", []))
            checks.append(
                TraceabilityCheck(
                    item_type="requirement", item_id=r.get("id", ""),
                    ok=not issues, issues=issues,
                    action="assumption" if (issues and r.get("assumption")) else ("revised" if issues else "keep"),
                )
            )

        # ---- 3) 测试用例：引用需求与评论 ----
        req_ids = {r["id"] for r in requirements}
        covered_reqs: set[str] = set()
        for tc in test_cases:
            issues = []
            if tc.get("requirement_id") not in req_ids:
                issues.append(f"引用不存在的需求: {tc.get('requirement_id')}")
            fake_rids = [rid for rid in tc.get("review_ids", []) if rid not in valid_review_ids]
            if fake_rids:
                issues.append(f"引用不存在的评论: {fake_rids[:5]}")
                tc["review_ids"] = [rid for rid in tc["review_ids"] if rid in valid_review_ids]
                revisions.append(f"{tc['id']}: 已移除不存在的评论引用")
            covered_reqs.add(tc.get("requirement_id", ""))
            checks.append(
                TraceabilityCheck(
                    item_type="test_case", item_id=tc.get("id", ""),
                    ok=not issues, issues=issues,
                    action="revised" if issues else "keep",
                )
            )

        # ---- 4) 覆盖性检查 ----
        uncovered_findings = [f["id"] for f in findings if f["id"] not in req_finding_used]
        if uncovered_findings:
            checks.append(
                TraceabilityCheck(
                    item_type="finding", item_id="(未覆盖)",
                    ok=False, issues=[f"以下发现未被任何需求引用: {uncovered_findings}"],
                    action="assumption",
                )
            )
        uncovered_reqs = [r["id"] for r in requirements if r["id"] not in covered_reqs]
        if uncovered_reqs:
            checks.append(
                TraceabilityCheck(
                    item_type="test_case", item_id="(未覆盖)",
                    ok=False, issues=[f"以下需求无测试用例覆盖: {uncovered_reqs}"],
                    action="keep",
                )
            )

        # ---- 5) 汇总 ----
        summary = {"total": len(checks), "ok": 0, "issues": 0}
        for c in checks:
            summary["ok" if c.ok else "issues"] += 1
        report = TraceabilityReport(
            checks=checks, summary=summary, revisions=revisions
        ).model_dump()

        # 回写修订后的产物
        ctx.save("findings", findings)
        ctx.save("prd", prd)
        ctx.save("test_cases", test_cases)
        ctx.save("traceability_report", report)
        self.revisions = revisions
        return report
