"""协作式暂停机制测试。

验证：pause_event 挂起/恢复、llm_call 暂停检查、fetch_reviews 页级暂停、
orchestrator 的 pause_run/resume_run 状态流转。
"""
import asyncio

import pytest

from app.pipeline.orchestrator import RunContext
from app.schemas import RunMeta


class FakeLLM:
    def __init__(self):
        self.calls = 0

    def complete_json(self, system, user, schema=None, temperature=None):
        self.calls += 1
        return {"ok": True}


def _make_ctx() -> RunContext:
    meta = RunMeta(run_id="test-pause", goal="测试")
    return RunContext("test-pause", meta, llm=FakeLLM())


async def test_pause_blocks_ensure_running():
    """暂停后 ensure_running 挂起，恢复后立即继续。"""
    ctx = _make_ctx()
    ctx.pause()
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(ctx.ensure_running(), timeout=0.1)
    ctx.resume()
    assert await ctx.ensure_running() is None


async def test_llm_call_waits_while_paused():
    """暂停时 llm_call 挂起（不发起调用），恢复后执行。"""
    ctx = _make_ctx()
    ctx.pause()
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(ctx.llm_call("sys", "user"), timeout=0.1)
    assert ctx.llm.calls == 0  # 暂停期间未执行 LLM
    ctx.resume()
    result = await ctx.llm_call("sys", "user")
    assert result == {"ok": True}
    assert ctx.llm.calls == 1


class _FakeResp:
    status_code = 200

    def raise_for_status(self):
        pass

    def json(self):
        # 空 feed：立即结束，只抓一页
        return {"feed": {"entry": []}}


class _FakeClient:
    def __init__(self):
        self.calls = 0

    async def get(self, url):
        self.calls += 1
        return _FakeResp()

    async def aclose(self):
        pass


async def test_fetch_reviews_waits_while_paused():
    """暂停时 fetch_reviews 每页前挂起，不发起请求；恢复后正常采集。"""
    from app.services.appstore import fetch_reviews

    ctx = _make_ctx()
    ctx.pause()
    client = _FakeClient()
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(
            fetch_reviews("123", client=client, pause_event=ctx.pause_event),
            timeout=0.1,
        )
    assert client.calls == 0  # 暂停时未发起任何请求
    ctx.resume()
    result = await fetch_reviews("123", client=client, pause_event=ctx.pause_event)
    assert client.calls == 1  # 恢复后发起一次请求（空 feed 立即结束）
    assert result["pages_fetched"] == 0


async def test_orchestrator_pause_resume_status(temp_settings, monkeypatch):
    """orchestrator 层：pause_run/resume_run 更新状态并广播事件。"""
    from app.pipeline.orchestrator import Orchestrator

    orch = Orchestrator()
    meta = orch.create_run(url=None, goal="测试")
    run_id = meta.run_id
    orch._ctx[run_id].meta.status = "running"  # 模拟运行中

    published = []

    async def fake_publish(run_id, event):
        published.append(event)

    monkeypatch.setattr(orch, "publish", fake_publish)

    # 暂停
    assert orch.pause_run(run_id) is True
    assert orch._ctx[run_id].meta.status == "paused"
    await asyncio.sleep(0)  # 让 create_task 的广播 task 执行
    assert any(e["type"] == "run_paused" for e in published)

    # 恢复
    assert orch.resume_run(run_id) is True
    assert orch._ctx[run_id].meta.status == "running"
    await asyncio.sleep(0)
    assert any(e["type"] == "run_resumed" for e in published)

    # 非 running 状态不可暂停
    orch._ctx[run_id].meta.status = "succeeded"
    assert orch.pause_run(run_id) is False

    # 非 paused 状态不可恢复
    assert orch.resume_run(run_id) is False

    orch.forget_run(run_id)