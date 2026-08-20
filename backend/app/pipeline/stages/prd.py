"""阶段 6：更新计划与 PRD 生成（模型驱动 + 确定性校验）。

- LLM 基于发现生成需求、优先级、边界与版本拆分
- 代码校验 finding_ids / review_ids 真实性；无支撑的标记 assumption
"""
from __future__ import annotations

import json
import logging

from ...llm.prompts import PRD_SYSTEM, PRD_USER_TEMPLATE
from ..orchestrator import BaseStage, RunContext, StageError

logger = logging.getLogger(__name__)

PRD_SCHEMA = {
    "name": "prd_result",
    "schema": {
        "type": "object",
        "properties": {
            "update_plan": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "versions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "version": {"type": "string"},
                                "title": {"type": "string"},
                                "scope": {"type": "string"},
                                "rationale": {"type": "string"},
                            },
                            "required": ["version", "title", "scope", "rationale"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["summary", "versions"],
                "additionalProperties": False,
            },
            "requirements": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "priority": {"type": "string", "enum": ["P0", "P1", "P2"]},
                        "version": {"type": "string"},
                        "boundaries": {"type": "string"},
                        "finding_ids": {"type": "array", "items": {"type": "string"}},
                        "review_ids": {"type": "array", "items": {"type": "string"}},
                        "assumption": {"type": "boolean"},
                    },
                    "required": [
                        "id", "title", "description", "priority", "version",
                        "boundaries", "finding_ids", "review_ids", "assumption",
                    ],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["update_plan", "requirements"],
        "additionalProperties": False,
    },
}


class PRDStage(BaseStage):
    name = "prd"
    label = "6. 更新计划与 PRD"

    async def execute(self, ctx: RunContext) -> dict:
        if ctx.llm is None:
            raise StageError("未配置 LLM，无法生成 PRD", degraded=True)

        findings = ctx.load("findings") or []
        if not findings:
            raise StageError("无发现数据，无法生成 PRD（请检查阶段 4）")

        goal = ctx.goal() or "整体用户问题"
        ctx.report_progress(25, "正在基于发现生成需求与版本计划")
        user = PRD_USER_TEMPLATE.format(
            goal=goal,
            findings_json=json.dumps(findings, ensure_ascii=False),
        )
        data = await ctx.llm_call(PRD_SYSTEM, user, schema=PRD_SCHEMA)
        ctx.report_progress(70, "LLM 生成完成，正在校验引用真实性")

        # ---- 确定性校验 ----
        valid_finding_ids = {f["id"] for f in findings}
        valid_review_ids = self._valid_review_ids(ctx)
        revisions: list[str] = []
        requirements = data.get("requirements", []) or []
        for i, r in enumerate(requirements, 1):
            r["id"] = f"R-{i:02d}"
            # 过滤不存在的引用
            r["finding_ids"] = [fid for fid in r.get("finding_ids", []) if fid in valid_finding_ids]
            r["review_ids"] = [rid for rid in r.get("review_ids", []) if rid in valid_review_ids]
            if not r["finding_ids"] or not r["review_ids"]:
                if not r.get("assumption"):
                    r["assumption"] = True
                    revisions.append(f"{r['id']}: 缺少有效证据引用，已标记为假设")
            # 确保 version 有值
            r.setdefault("version", "V1")

        plan_versions = (data.get("update_plan") or {}).get("versions", []) or []
        if not plan_versions:
            versions = sorted({r.get("version", "V1") for r in requirements})
            plan_versions = [{"version": v, "title": f"版本 {v}", "scope": "", "rationale": "按需求优先级拆分"} for v in versions]
            if not plan_versions:
                plan_versions = [{"version": "V1", "title": "初始版本", "scope": "", "rationale": "暂无需求"}]

        prd = {
            "update_plan": {
                "summary": (data.get("update_plan") or {}).get("summary", ""),
                "versions": plan_versions,
            },
            "requirements": requirements,
        }
        ctx.save("prd", prd)
        self.revisions = revisions
        ctx.report_progress(100, f"PRD 生成完成：{len(requirements)} 条需求")
        return {
            "requirements_count": len(requirements),
            "versions": [v.get("version") for v in plan_versions],
            "revisions": revisions,
        }

    @staticmethod
    def _valid_review_ids(ctx: RunContext) -> set[str]:
        cleaned = ctx.load("cleaned_reviews") or []
        return {r["review_id"] for r in cleaned}
