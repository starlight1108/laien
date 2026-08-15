"""FastAPI 接口层测试（requests 库 + 后台 uvicorn 服务器）。

覆盖：health / providers / llm models / llm test / runs CRUD /
artifacts / SSE 事件流 / 缓存回退。orchestrator.start 被 mock，
避免真实流水线执行；数据目录重定向到临时目录，不污染真实数据。
"""
import json
import socket
import threading
import time

import pytest
import requests
import uvicorn

from app.main import app, orchestrator
from app.storage import save_artifact


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def server(temp_settings, monkeypatch):
    """后台线程启动 uvicorn 服务器，返回 base_url。

    与 TestClient 不同，requests 需要真实 HTTP 服务。服务器与测试
    同进程，因此 temp_settings 重定向的数据目录对其同样生效。
    """
    # start 置为 no-op：只验证接口契约，不真正跑流水线（离线、确定性）
    monkeypatch.setattr(orchestrator, "start", lambda run_id: None)

    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"

    # 等待服务就绪（uvicorn.started + health 双保险）
    for _ in range(200):
        if getattr(server, "started", False):
            break
        time.sleep(0.02)
    for _ in range(50):
        try:
            if requests.get(base + "/api/health", timeout=0.3).status_code == 200:
                break
        except requests.RequestException:
            time.sleep(0.05)

    yield base

    server.should_exit = True
    thread.join(timeout=5)


# --------------------------------------------------------------------------
# 基础端点
# --------------------------------------------------------------------------
def test_health(server):
    r = requests.get(server + "/api/health", timeout=5)
    assert r.status_code == 200
    assert r.json() == {"ok": True, "app": "app-review-insights"}


def test_providers(server):
    r = requests.get(server + "/api/providers", timeout=5)
    assert r.status_code == 200
    data = r.json()
    assert "providers" in data
    assert isinstance(data["providers"], list)
    for p in data["providers"]:
        assert "id" in p
        assert "name" in p


# --------------------------------------------------------------------------
# LLM 相关端点
# --------------------------------------------------------------------------
def test_llm_models_missing_base_url(server):
    """无 Base URL 时快速降级为预置列表并说明原因。"""
    r = requests.post(server + "/api/llm/models", json={}, timeout=5)
    assert r.status_code == 200
    data = r.json()
    assert data["source"] == "fallback"
    assert "error" in data


def test_llm_models_with_fetch(monkeypatch, server):
    """mock _fetch_models 成功时返回 API 来源的模型列表。"""
    monkeypatch.setattr("app.main._fetch_models", lambda base_url, api_key: ["gpt-4o", "gpt-4o-mini"])
    r = requests.post(
        server + "/api/llm/models",
        json={"base_url": "https://api.example.com/v1", "api_key": "sk-x"},
        timeout=5,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["source"] == "api"
    assert data["models"] == ["gpt-4o", "gpt-4o-mini"]


def test_llm_models_timeout_fallback(monkeypatch, server):
    """mock _fetch_models 抛超时异常时降级为预置列表。"""
    def slow(base_url, api_key):
        raise TimeoutError("timeout")

    monkeypatch.setattr("app.main._fetch_models", slow)
    r = requests.post(server + "/api/llm/models", json={"base_url": "https://api.example.com/v1"}, timeout=5)
    assert r.status_code == 200
    assert r.json()["source"] == "fallback"


def test_llm_test_ok(monkeypatch, server):
    """mock LLMClient 连接成功。"""
    class FakeClient:
        def __init__(self, **kwargs):
            self.model = kwargs.get("model", "m")

        def test_connection(self):
            return {"ok": True, "model": self.model, "latency_ms": 12}

    monkeypatch.setattr("app.main.LLMClient", FakeClient)
    r = requests.post(
        server + "/api/llm/test",
        json={"base_url": "https://api.example.com/v1", "model": "m1"},
        timeout=5,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["model"] == "m1"


def test_llm_test_error(monkeypatch, server):
    """mock LLMClient 抛异常时返回 400 与错误信息。"""
    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def test_connection(self):
            raise RuntimeError("bad key")

    monkeypatch.setattr("app.main.LLMClient", FakeClient)
    r = requests.post(server + "/api/llm/test", json={"base_url": "https://api.example.com/v1"}, timeout=5)
    assert r.status_code == 400
    assert r.json()["ok"] is False
    assert "bad key" in r.json()["error"]


# --------------------------------------------------------------------------
# 创建运行
# --------------------------------------------------------------------------
def test_create_run_with_import_text(server):
    r = requests.post(
        server + "/api/runs",
        json={"import_text": '[{"id": "1", "title": "t", "content": "c", "rating": 5}]'},
        timeout=5,
    )
    assert r.status_code == 200
    meta = r.json()
    assert meta["run_id"]
    assert meta["source"] == "import"
    assert meta["status"] == "pending"


def test_create_run_with_import_data(server):
    data = [{"id": "1", "title": "t", "content": "c", "rating": 4}]
    r = requests.post(server + "/api/runs", json={"import_data": data}, timeout=5)
    assert r.status_code == 200
    assert r.json()["source"] == "import"


def test_create_run_invalid_import_text(server):
    r = requests.post(server + "/api/runs", json={"import_text": "not json nor csv"}, timeout=5)
    assert r.status_code == 400
    assert "detail" in r.json()


def test_create_run_invalid_import_data(server):
    """缺少必填字段 rating 时返回 400。"""
    r = requests.post(
        server + "/api/runs",
        json={"import_data": [{"id": "1", "title": "t", "content": "c"}]},
        timeout=5,
    )
    assert r.status_code == 400
    assert "rating" in r.json()["detail"]


def test_create_run_with_url(server):
    r = requests.post(
        server + "/api/runs",
        json={"url": "https://apps.apple.com/cn/app/id123", "goal": "订阅"},
        timeout=5,
    )
    assert r.status_code == 200
    meta = r.json()
    assert meta["source"] == "url"
    assert meta["url"] == "https://apps.apple.com/cn/app/id123"


# --------------------------------------------------------------------------
# 查询运行
# --------------------------------------------------------------------------
def test_list_runs(server):
    r = requests.get(server + "/api/runs", timeout=5)
    assert r.status_code == 200
    assert "runs" in r.json()


def test_list_runs_contains_created(server):
    created = requests.post(
        server + "/api/runs",
        json={"import_text": '[{"id": "1", "title": "t", "content": "c", "rating": 3}]'},
        timeout=5,
    ).json()
    r = requests.get(server + "/api/runs", timeout=5)
    ids = [x["run_id"] for x in r.json()["runs"]]
    assert created["run_id"] in ids


def test_get_run(server):
    created = requests.post(
        server + "/api/runs",
        json={"import_text": '[{"id": "1", "title": "t", "content": "c", "rating": 3}]'},
        timeout=5,
    ).json()
    r = requests.get(server + f"/api/runs/{created['run_id']}", timeout=5)
    assert r.status_code == 200
    assert r.json()["run_id"] == created["run_id"]


def test_get_run_not_found(server):
    r = requests.get(server + "/api/runs/nonexistent_123", timeout=5)
    assert r.status_code == 404


# --------------------------------------------------------------------------
# 产物
# --------------------------------------------------------------------------
def test_get_artifact(server, temp_settings):
    created = requests.post(
        server + "/api/runs",
        json={"import_text": '[{"id": "1", "title": "t", "content": "c", "rating": 3}]'},
        timeout=5,
    ).json()
    run_id = created["run_id"]
    save_artifact(run_id, "scope", {"summary": "x", "filters": []})
    r = requests.get(server + f"/api/runs/{run_id}/artifacts/scope", timeout=5)
    assert r.status_code == 200
    assert r.json() == {"summary": "x", "filters": []}


def test_get_artifact_not_found(server):
    created = requests.post(
        server + "/api/runs",
        json={"import_text": '[{"id": "1", "title": "t", "content": "c", "rating": 3}]'},
        timeout=5,
    ).json()
    r = requests.get(server + f"/api/runs/{created['run_id']}/artifacts/does_not_exist", timeout=5)
    assert r.status_code == 404


def test_list_artifacts(server, temp_settings):
    created = requests.post(
        server + "/api/runs",
        json={"import_text": '[{"id": "1", "title": "t", "content": "c", "rating": 3}]'},
        timeout=5,
    ).json()
    run_id = created["run_id"]
    save_artifact(run_id, "scope", {})
    save_artifact(run_id, "themes", {})
    r = requests.get(server + f"/api/runs/{run_id}/artifacts", timeout=5)
    assert r.status_code == 200
    assert "scope" in r.json()["artifacts"]
    assert "themes" in r.json()["artifacts"]


# --------------------------------------------------------------------------
# SSE 事件流
# --------------------------------------------------------------------------
def test_run_events_not_found(server):
    r = requests.get(server + "/api/runs/nonexistent_123/events", timeout=5)
    assert r.status_code == 404


def test_run_events_streams_run_end(server, temp_settings):
    """预置 run_end 事件，验证 SSE 流能消费并结束（不挂起）。"""
    created = requests.post(
        server + "/api/runs",
        json={"import_text": '[{"id": "1", "title": "t", "content": "c", "rating": 3}]'},
        timeout=5,
    ).json()
    run_id = created["run_id"]
    queue = orchestrator.subscribe(run_id)
    queue.put_nowait({"type": "run_end", "run_id": run_id, "status": "succeeded"})

    r = requests.get(
        server + f"/api/runs/{run_id}/events",
        headers={"Accept": "text/event-stream"},
        stream=True,
        timeout=5,
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    lines = [ln for ln in r.iter_lines(decode_unicode=True) if ln.startswith("data: ")]
    assert len(lines) == 1
    event = json.loads(lines[0][len("data: "):])
    assert event["type"] == "run_end"
    assert event["status"] == "succeeded"
    r.close()


# --------------------------------------------------------------------------
# 缓存回退
# --------------------------------------------------------------------------
def test_get_run_falls_back_to_cache(server, temp_settings):
    """缓存演示运行：get_run 回退读取 cache meta，并标注 cache=true。"""
    run_id = "cache_demo_001"
    cache_dir = temp_settings.cache_dir / run_id
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "meta.json").write_text(
        json.dumps({"run_id": run_id, "goal": "演示", "status": "succeeded", "created_at": "2026-01-01T00:00:00Z"}),
        encoding="utf-8",
    )
    r = requests.get(server + f"/api/runs/{run_id}", timeout=5)
    assert r.status_code == 200
    meta = r.json()
    assert meta["run_id"] == run_id
    assert meta["cache"] is True


def test_list_runs_includes_cache(server, temp_settings):
    cache_dir = temp_settings.cache_dir / "cache_demo_002"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "meta.json").write_text(
        json.dumps({"run_id": "cache_demo_002", "goal": "演示", "status": "succeeded", "created_at": "2026-01-02T00:00:00Z"}),
        encoding="utf-8",
    )
    r = requests.get(server + "/api/runs", timeout=5)
    ids = [x["run_id"] for x in r.json()["runs"]]
    assert "cache_demo_002" in ids
