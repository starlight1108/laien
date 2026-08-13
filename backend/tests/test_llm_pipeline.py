"""模型驱动阶段集成测试（使用 FakeLLM，不调用真实 API）。

验证：analyze(主题/发现) -> evidence -> prd -> tests -> validate 全链路，
以及统计结论与模型结论的区分、追溯校验。
"""
from app.pipeline.orchestrator import RunContext
from app.pipeline.stages.analyze import AnalyzeStage
from app.pipeline.stages.evidence import EvidenceStage
from app.pipeline.stages.prd import PRDStage
from app.pipeline.stages.tests import TestsStage
from app.pipeline.stages.validate import ValidateStage
from app.schemas import RunMeta


class FakeLLM:
    """按系统提示词返回对应的结构化 JSON。"""

    def __init__(self):
        self.calls = []

    def complete_json(self, system, user, schema=None, temperature=None):
        self.calls.append(system[:20])
        if "归纳" in system or "整合" in system:
            return {
                "themes": [
                    {
                        "id": "T-01", "title": "订阅问题", "description": "订阅取消与扣费问题",
                        "review_ids": ["2", "3", "7"], "sentiment": "negative", "confidence": "high",
                    }
                ]
            }
        if "重大发现" in system or "findings" in system.lower():
            return {
                "findings": [
                    {
                        "id": "F-01", "title": "订阅取消困难", "summary": "多条评论反映取消订阅流程复杂",
                        "kind": "model_derived", "evidence_review_ids": ["2", "7"],
                        "supporting_count": 2, "confidence": "high",
                        "conflicting_review_ids": [], "uncertainty": "", "assumption": False,
                    }
                ]
            }
        if "PRD" in system:
            return {
                "update_plan": {
                    "summary": "优先修复订阅相关问题",
                    "versions": [{"version": "V1", "title": "订阅修复", "scope": "订阅", "rationale": "证据最强"}],
                },
                "requirements": [
                    {
                        "id": "R-01", "title": "简化订阅取消流程", "description": "解决取消困难",
                        "priority": "P0", "version": "V1", "boundaries": "仅 iOS 端",
                        "finding_ids": ["F-01"], "review_ids": ["2", "7"], "assumption": False,
                    }
                ],
            }
        if "测试用例" in system:
            return {
                "test_cases": [
                    {
                        "id": "TC-01", "requirement_id": "R-01", "review_ids": ["2"],
                        "preconditions": "已订阅用户", "steps": ["进入设置", "点击取消订阅"],
                        "expected": "3 步内完成取消", "verifies_issue": "订阅可便捷取消",
                    }
                ]
            }
        return {}


def _ctx(temp_settings) -> RunContext:
    meta = RunMeta(run_id="llm_pipeline_test", goal="订阅")
    ctx = RunContext("llm_pipeline_test", meta, llm=FakeLLM())
    ctx.save(
        "cleaned_reviews",
        [
            {"review_id": "2", "content": "I cannot cancel my subscription easily", "rating": 1, "is_duplicate": False},
            {"review_id": "7", "content": "Hidden charges on my credit card", "rating": 1, "is_duplicate": False},
            {"review_id": "3", "content": "Subscription price is too high", "rating": 2, "is_duplicate": False},
        ],
    )
    return ctx


async def test_model_driven_full_chain(temp_settings):
    ctx = _ctx(temp_settings)

    # 阶段 4
    result = await AnalyzeStage().execute(ctx)
    assert result["themes_count"] == 1
    assert result["model_findings"] >= 1
    findings = ctx.load("findings")
    # 同时有统计发现与模型发现，且可区分
    assert any(f["kind"] == "deterministic_stat" for f in findings)
    assert any(f["kind"] == "model_derived" for f in findings)
    model_f = next(f for f in findings if f["kind"] == "model_derived")
    assert model_f["evidence_review_ids"] == ["2", "7"]
    assert model_f["supporting_count"] == 2  # 复核一致

    # 阶段 5
    await EvidenceStage().execute(ctx)
    evidence = ctx.load("evidence_report")
    assert evidence["items"]

    # 阶段 6
    prd_result = await PRDStage().execute(ctx)
    assert prd_result["requirements_count"] == 1
    prd = ctx.load("prd")
    assert prd["requirements"][0]["finding_ids"] == ["F-01"]

    # 阶段 7
    await TestsStage().execute(ctx)
    tests = ctx.load("test_cases")
    assert len(tests) >= 1
    assert tests[0]["requirement_id"] == "R-01"

    # 阶段 8
    report = await ValidateStage().execute(ctx)
    assert report["summary"]["total"] > 0
    assert all(c["ok"] for c in report["checks"] if c["item_id"] not in ("", "(未覆盖)"))


async def test_analyze_revises_supporting_count(temp_settings):
    """模型产出的 supporting_count 与实际证据数不符时，代码复核修订。"""
    ctx = _ctx(temp_settings)

    def fake_llm(system, user, schema=None, temperature=None):
        if "归纳" in system or "整合" in system:
            return {
                "themes": [
                    {
                        "id": "T-01", "title": "订阅问题", "description": "d",
                        "review_ids": ["2", "3"], "sentiment": "negative", "confidence": "high",
                    }
                ]
            }
        if "重大发现" in system:
            return {
                "findings": [
                    {
                        "id": "F-99", "title": "x", "summary": "s", "kind": "model_derived",
                        "evidence_review_ids": ["2", "3"], "supporting_count": 99,
                        "confidence": "medium", "conflicting_review_ids": [],
                        "uncertainty": "", "assumption": False,
                    }
                ]
            }
        return {"themes": []}

    # 覆盖 FakeLLM 返回不一致的 supporting_count
    ctx.llm.complete_json = fake_llm
    await AnalyzeStage().execute(ctx)
    findings = ctx.load("findings")
    model_f = next(f for f in findings if f["kind"] == "model_derived")
    assert model_f["supporting_count"] == 2  # 修订为证据数
    assert model_f["id"] == "F-01"  # 重编号
