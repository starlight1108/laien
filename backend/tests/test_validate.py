"""阶段 8 追溯验证测试（确定性规则）。"""
from app.pipeline.orchestrator import RunContext, orchestrator
from app.pipeline.stages.validate import ValidateStage
from app.schemas import RunMeta
from app.storage import get_run_meta, load_artifact


def _ctx(temp_settings):
    meta = RunMeta(run_id="test_run", goal="测试")
    ctx = RunContext("test_run", meta)
    ctx.save(
        "cleaned_reviews",
        [
            {"review_id": "r1", "content": "a", "rating": 2},
            {"review_id": "r2", "content": "b", "rating": 5},
        ],
    )
    ctx.save(
        "findings",
        [
            {
                "id": "F-01", "title": "f1", "summary": "s", "kind": "model_derived",
                "evidence_review_ids": ["r1"], "supporting_count": 1,
                "confidence": "medium", "conflicting_review_ids": [],
                "uncertainty": None, "assumption": False, "source": "x",
            }
        ],
    )
    ctx.save(
        "prd",
        {
            "update_plan": {"summary": "p", "versions": [{"version": "V1", "title": "v", "scope": "s", "rationale": "r"}]},
            "requirements": [
                {
                    "id": "R-01", "title": "req", "description": "d", "priority": "P0",
                    "version": "V1", "boundaries": "b", "finding_ids": ["F-01"],
                    "review_ids": ["r1"], "assumption": False,
                }
            ],
        },
    )
    ctx.save(
        "test_cases",
        [
            {
                "id": "TC-01", "requirement_id": "R-01", "review_ids": ["r1"],
                "preconditions": "p", "steps": ["s"], "expected": "e", "verifies_issue": "v",
            }
        ],
    )
    return ctx


async def test_validate_ok_chain(temp_settings):
    ctx = _ctx(temp_settings)
    stage = ValidateStage()
    report = await stage.execute(ctx)
    assert report["summary"]["total"] == 3
    assert all(c["ok"] for c in report["checks"])


async def test_validate_fixes_supporting_count(temp_settings):
    ctx = _ctx(temp_settings)
    findings = ctx.load("findings")
    findings[0]["supporting_count"] = 99  # 与实际证据数不符
    ctx.save("findings", findings)
    stage = ValidateStage()
    await stage.execute(ctx)
    assert ctx.load("findings")[0]["supporting_count"] == 1
    assert any("supporting_count" in r for r in stage.revisions)


async def test_validate_marks_assumption_for_unreferenced_requirement(temp_settings):
    ctx = _ctx(temp_settings)
    prd = ctx.load("prd")
    prd["requirements"][0]["finding_ids"] = []
    prd["requirements"][0]["review_ids"] = []
    ctx.save("prd", prd)
    stage = ValidateStage()
    await stage.execute(ctx)
    assert ctx.load("prd")["requirements"][0]["assumption"] is True


async def test_full_pipeline_without_llm(temp_settings):
    """无 LLM 配置时：阶段 1-3/5/8 可完成，模型阶段降级，结果透明标注。"""
    meta = orchestrator.create_run(
        goal="订阅",
        import_data=[
            {"id": "1", "title": "t", "content": "I can't cancel my subscription easily", "rating": 1},
            {"id": "2", "title": "t", "content": "Great app for home workouts", "rating": 5},
            {"id": "3", "title": "t", "content": "The subscription price is too high", "rating": 2},
        ],
    )
    await orchestrator._run(meta.run_id)

    final = get_run_meta(meta.run_id)
    assert final["status"] == "degraded"
    assert load_artifact(meta.run_id, "raw_reviews") is not None
    assert load_artifact(meta.run_id, "cleaned_reviews") is not None
    assert load_artifact(meta.run_id, "clean_report") is not None
    assert load_artifact(meta.run_id, "traceability_report") is not None
    stages = {s["stage"]: s["status"] for s in final["stages"]}
    assert stages["scope"] == "succeeded"
    assert stages["collect"] == "succeeded"
    assert stages["clean"] == "succeeded"
    assert stages["analyze"] == "degraded"
    assert stages["prd"] == "degraded"
    assert stages["tests"] == "degraded"
