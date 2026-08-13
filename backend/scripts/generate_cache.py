"""生成离线缓存示例运行（data/cache/）。

用途：在无外网 / 无 LLM Key 时，评审者可通过 UI「缓存运行」查看完整结果。
- 数据：真实采集自 Apple 官方 RSS Feed（复制自某次真实运行）
- 语义产物（主题/发现/PRD/测试用例）：为**演示用途**由本脚本按规则生成，
  并在 meta.json 中明确标注，绝不冒充实时模型输出。

用法：
    python -m scripts.generate_cache --source <run_id> [--limit 300]
"""
from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import settings  # noqa: E402
from app.pipeline.orchestrator import RunContext  # noqa: E402
from app.pipeline.stages.evidence import EvidenceStage  # noqa: E402
from app.pipeline.stages.validate import ValidateStage  # noqa: E402
from app.schemas import RunMeta  # noqa: E402
from app.storage import new_run_id, save_artifact  # noqa: E402

# 主题关键词规则（仅缓存演示用；实时运行使用模型动态归纳）
THEME_RULES = [
    ("订阅与付费", ["subscription", "cancel", "charge", "price", "pay", "money", "billing", "免费", "订阅", "扣费"]),
    ("崩溃与稳定性", ["crash", "startup", "freeze", "bug", "load", "崩溃", "闪退"]),
    ("广告体验", ["ad", "ads", "advert", "广告"]),
    ("训练内容", ["workout", "exercise", "yoga", "plan", "train", "routine", "训练", "瑜伽"]),
    ("正面反馈", ["love", "great", "best", "amazing", "excellent", "awesome", "好", "喜欢"]),
]


def build_themes(kept: list[dict]) -> list[dict]:
    themes: list[dict] = []
    for title, kws in THEME_RULES:
        members = []
        for r in kept:
            text = (r.get("content", "") + " " + r.get("title", "")).lower()
            if any(k.lower() in text for k in kws):
                members.append(r)
        if len(members) >= 2:
            themes.append(
                {
                    "id": f"T-{len(themes) + 1:02d}",
                    "title": title,
                    "description": f"缓存演示主题：按关键词规则归纳（{len(members)} 条评论）",
                    "review_ids": [r["review_id"] for r in members[:12]],
                    "sentiment": "positive" if title == "正面反馈" else "negative",
                    "confidence": "high" if len(members) >= 10 else "medium",
                }
            )
    return themes


def build_findings(themes: list[dict], stats: dict, valid_ids: set[str]) -> list[dict]:
    findings: list[dict] = []
    # 确定性统计发现
    dist = stats.get("rating_distribution", {})
    low = int(dist.get("1", 0)) + int(dist.get("2", 0))
    findings.append({
        "id": "F-01",
        "title": f"低分评论占比 {low}/{stats['total']}（确定性统计）",
        "summary": f"共 {low} 条 1-2 星评论。",
        "kind": "deterministic_stat",
        "evidence_review_ids": [],
        "supporting_count": low,
        "confidence": "high",
        "conflicting_review_ids": [],
        "uncertainty": "仅反映评分分布",
        "assumption": False,
        "source": "cache_demo_stats",
    })
    # 演示模型发现（明确标注为缓存演示）
    for i, t in enumerate(themes, start=2):
        rid_set = set(t["review_ids"]) & valid_ids
        findings.append({
            "id": f"F-{i:02d}",
            "title": f"[缓存演示] {t['title']} 相关反馈",
            "summary": f"缓存演示产物：基于规则归纳主题「{t['title']}」生成。实时运行时由 LLM 动态生成并附证据。",
            "kind": "model_derived",
            "evidence_review_ids": sorted(rid_set)[:8],
            "supporting_count": len(rid_set),
            "confidence": t["confidence"],
            "conflicting_review_ids": [],
            "uncertainty": "缓存演示产物，非实时模型输出",
            "assumption": False,
            "source": "cache_demo",
        })
    return findings


def build_prd(findings: list[dict]) -> dict:
    requirements = []
    for i, f in enumerate(findings[1:], start=1):  # 跳过纯统计发现
        requirements.append({
            "id": f"R-{i:02d}",
            "title": f"优化：{f['title'].replace('[缓存演示] ', '')}",
            "description": "缓存演示需求，实时运行时由 LLM 基于证据生成",
            "priority": "P0" if i == 1 else "P1",
            "version": "V1" if i == 1 else "V2",
            "boundaries": "缓存演示边界",
            "finding_ids": [f["id"]],
            "review_ids": (f.get("evidence_review_ids") or [])[:4],
            "assumption": False,
        })
    if not requirements:
        requirements = [{
            "id": "R-01", "title": "演示需求", "description": "无主题时生成",
            "priority": "P2", "version": "V1", "boundaries": "",
            "finding_ids": [], "review_ids": [], "assumption": True,
        }]
    return {
        "update_plan": {
            "summary": "缓存演示更新计划（按证据强度拆分 V1/V2）",
            "versions": [
                {"version": "V1", "title": "核心问题修复", "scope": "高优先级需求", "rationale": "证据最强"},
                {"version": "V2", "title": "体验优化", "scope": "次优先级需求", "rationale": "影响面较小"},
            ],
        },
        "requirements": requirements,
    }


def build_test_cases(prd: dict) -> list[dict]:
    cases = []
    for i, r in enumerate(prd["requirements"], start=1):
        cases.append({
            "id": f"TC-{i:02d}",
            "requirement_id": r["id"],
            "review_ids": (r.get("review_ids") or [])[:3],
            "preconditions": "进入应用对应功能页面",
            "steps": [f"执行需求 {r['id']} 的核心场景", "观察结果"],
            "expected": f"需求 {r['id']} 的验收要点得到满足",
            "verifies_issue": (r.get("description") or "")[:200],
        })
    return cases


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="源 run_id（真实采集运行）")
    parser.add_argument("--limit", type=int, default=300, help="缓存评论上限")
    args = parser.parse_args()

    src = settings.data_dir / "runs" / args.source
    if not src.exists():
        print(f"源运行不存在: {src}")
        sys.exit(1)

    run_id = new_run_id()
    cache_dir = settings.cache_dir / run_id
    cache_dir.mkdir(parents=True, exist_ok=True)

    # 复制真实数据产物
    for name in ("scope", "raw_reviews", "cleaned_reviews", "clean_report"):
        p = src / f"{name}.json"
        if p.exists():
            shutil.copy(p, cache_dir / f"{name}.json")

    cleaned = json.loads((cache_dir / "cleaned_reviews.json").read_text(encoding="utf-8"))
    kept = [r for r in cleaned if not r.get("is_duplicate")][: args.limit]
    valid_ids = {r["review_id"] for r in kept}

    meta = RunMeta(
        run_id=run_id,
        app_id=json.loads((cache_dir / "scope.json").read_text(encoding="utf-8")).get("app_id"),
        goal="整体用户问题（缓存演示）",
        source="url",
        status="succeeded",
        cache=True,
        cache_note="离线缓存样例：评论数据真实采集自 Apple RSS Feed；主题/发现/PRD/测试用例为规则生成的演示产物，非实时模型输出",
        stages=[
            {"stage": "scope", "label": "1. 确定分析范围", "status": "succeeded"},
            {"stage": "collect", "label": "2. 采集评论数据", "status": "succeeded"},
            {"stage": "clean", "label": "3. 清洗·去重·结构化", "status": "succeeded"},
            {"stage": "analyze", "label": "4. 动态分类与分析", "status": "succeeded"},
            {"stage": "evidence", "label": "5. 证据充分性评估", "status": "succeeded"},
            {"stage": "prd", "label": "6. 更新计划与 PRD", "status": "succeeded"},
            {"stage": "tests", "label": "7. 生成测试用例", "status": "succeeded"},
            {"stage": "validate", "label": "8. 可追溯性验证", "status": "succeeded"},
        ],
    )

    ctx = RunContext(run_id, meta, llm=None)
    ctx.save("themes", build_themes(kept))
    ctx.save("findings", build_findings(ctx.load("themes"), _stats(kept), valid_ids))
    # 证据评估与追溯验证复用阶段 5/8 逻辑（各自内部保存产物）
    asyncio.run(EvidenceStage().execute(ctx))
    ctx.save("prd", build_prd(ctx.load("findings")))
    ctx.save("test_cases", build_test_cases(ctx.load("prd")))
    asyncio.run(ValidateStage().execute(ctx))
    ctx.save("meta", meta.model_dump(mode="json"))

    # RunContext.save 写入 data/runs/{run_id}，统一复制到缓存目录后清理
    src_run = settings.data_dir / "runs" / run_id
    if src_run.exists():
        for f in src_run.glob("*.json"):
            shutil.copy(f, cache_dir / f.name)
        shutil.rmtree(src_run)

    print(f"缓存运行已生成: {cache_dir}")
    print(f"评论 {len(kept)} 条, 主题 {len(ctx.load('themes'))} 个, "
          f"发现 {len(ctx.load('findings'))} 项, 需求 {len(ctx.load('prd')['requirements'])} 条, "
          f"用例 {len(ctx.load('test_cases'))} 条")


def _stats(kept: list[dict]) -> dict:
    from collections import Counter

    ratings = Counter(r.get("rating") for r in kept if r.get("rating"))
    return {
        "total": len(kept),
        "rating_distribution": {str(i): ratings.get(i, 0) for i in range(1, 6)},
    }


if __name__ == "__main__":
    main()
