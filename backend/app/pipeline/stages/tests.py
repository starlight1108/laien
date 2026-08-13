"""阶段 7：测试用例生成（模型驱动 + 确定性校验）。

- LLM 依据 PRD 生成用例，每个用例关联需求与来源评论
- 用例须能验证"需求是否解决评论中的问题"
"""
from __future__ import annotations

import json
import logging

from ...llm.prompts import TESTS_SYSTEM, TESTS_USER_TEMPLATE
from ..orchestrator import BaseStage, RunContext, StageError

logger = logging.getLogger(__name__)

TESTS_SCHEMA = {
    "name": "test_cases_result",
    "schema": {
        "type": "object",
        "properties": {
            "test_cases": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "requirement_id": {"type": "string"},
                        "review_ids": {"type": "array", "items": {"type": "string"}},
                        "preconditions": {"type": "string"},
                        "steps": {"type": "array", "items": {"type": "string"}},
                        "expected": {"type": "string"},
                        "verifies_issue": {"type": "string"},
                    },
                    "required": [
                        "id", "requirement_id", "review_ids", "preconditions",
                        "steps", "expected", "verifies_issue",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["test_cases"],
        "additionalProperties": False,
    },
}


class TestsStage(BaseStage):
    name = "tests"
    label = "7. 生成测试用例"

    async def execute(self, ctx: RunContext) -> dict:
        if ctx.llm is None:
            raise StageError("未配置 LLM，无法生成测试用例", degraded=True)

        prd = ctx.load("prd") or {}
        requirements = prd.get("requirements", []) or []
        if not requirements:
            raise StageError("无 PRD 需求，无法生成测试用例（请检查阶段 6）")

        cleaned = ctx.load("cleaned_reviews") or []
        kept = [r for r in cleaned if not r.get("is_duplicate")]
        user = TESTS_USER_TEMPLATE.format(
            prd_json=json.dumps(prd, ensure_ascii=False),
            reviews_json=json.dumps(kept[:500], ensure_ascii=False, default=str),
        )
        data = await ctx.llm_call(TESTS_SYSTEM, user, schema=TESTS_SCHEMA)

        # ---- 确定性校验 ----
        valid_req_ids = {r["id"] for r in requirements}
        valid_review_ids = {r["review_id"] for r in cleaned}
        revisions: list[str] = []
        cases = data.get("test_cases", []) or []
        kept_cases = []
        for i, tc in enumerate(cases, 1):
            tc["id"] = f"TC-{i:02d}"
            if tc.get("requirement_id") not in valid_req_ids:
                revisions.append(f"{tc['id']}: 引用了不存在的需求 {tc.get('requirement_id')}，已跳过")
                continue
            tc["review_ids"] = [rid for rid in tc.get("review_ids", []) if rid in valid_review_ids]
            kept_cases.append(tc)

        # 未覆盖的需求补一个兜底用例（确定性生成，避免缺口）
        covered = {tc["requirement_id"] for tc in kept_cases}
        for req in requirements:
            if req["id"] not in covered:
                idx = len(kept_cases) + 1
                kept_cases.append(
                    {
                        "id": f"TC-{idx:02d}",
                        "requirement_id": req["id"],
                        "review_ids": (req.get("review_ids") or [])[:3],
                        "preconditions": "进入应用对应功能页面",
                        "steps": ["执行需求 " + req["id"] + " 描述的核心场景", "观察结果"],
                        "expected": "需求 " + req["id"] + " 的验收要点得到满足",
                        "verifies_issue": (req.get("description") or "")[:200],
                    }
                )

        ctx.save("test_cases", kept_cases)
        self.revisions = revisions
        return {"test_cases_count": len(kept_cases), "revisions": revisions}
