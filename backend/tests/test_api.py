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


@pytest.fixture(scope="session")
def server():
    """后台线程启动 uvicorn 服务器，返回 base_url（整个会话仅启动一次）。

    与 TestClient 不同，requests 需要真实 HTTP 服务。服务器与测试同进程：
    请求处理时动态读取 settings 单例，因此各测试的 temp_settings 数据目录
    重定向依然生效，函数级隔离不变。44 个测试反复启停服务器会显著拖慢套件，
    故用 session 级只启动一次。
    """
    # start 置为 no-op：只验证接口契约，不真正跑流水线（离线、确定性）
    def _noop_start(*args) -> None:
        return None

    original_start = orchestrator.start
    orchestrator.start = _noop_start

    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"

    # 等待服务就绪（uvicorn.started + health 双保险），超时则明确报错而非静默继续
    started = False
    for _ in range(200):
        if getattr(server, "started", False):
            started = True
            break
        time.sleep(0.02)
    healthy = False
    for _ in range(50):
        try:
            if requests.get(base + "/api/health", timeout=0.3).status_code == 200:
                healthy = True
                break
        except requests.RequestException:
            time.sleep(0.05)
    assert started and healthy, "uvicorn 服务器启动失败或 /api/health 未就绪"

    yield base

    server.should_exit = True
    thread.join(timeout=5)
    orchestrator.start = original_start


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
    """mock _fetch_models 抛超时异常时降级为空列表并说明（不再回退预置模型列表）。"""
    def slow(base_url, api_key):
        raise TimeoutError("timeout")

    monkeypatch.setattr("app.main._fetch_models", slow)
    r = requests.post(
        server + "/api/llm/models",
        json={"provider": "openai", "base_url": "https://api.example.com/v1"},
        timeout=5,
    )
    assert r.status_code == 200
    data = r.json()
    assert data["source"] == "fallback"
    assert data["models"] == []
    assert "error" in data


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
# LLM 配置持久化（本地 JSON 文件，按提供商分槽，已 gitignore）
# --------------------------------------------------------------------------
def test_llm_config_empty_default(server, temp_settings):
    """文件不存在时返回空分槽结构。"""
    r = requests.get(server + "/api/llm/config", timeout=5)
    assert r.status_code == 200
    assert r.json() == {"providers": {}}


def test_llm_config_roundtrip(server, temp_settings):
    """PUT 写入本地文件对应提供商槽位，GET 能读回同一份配置。"""
    cfg = {
        "provider": "openai",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o",
        "api_key": "sk-secret",
    }
    r = requests.put(server + "/api/llm/config", json=cfg, timeout=5)
    assert r.status_code == 200
    # 响应为槽位内容（不含 provider 本身）
    assert r.json() == {"base_url": cfg["base_url"], "model": cfg["model"], "api_key": cfg["api_key"]}
    # 文件落在临时数据目录，结构为按提供商分槽
    config_file = temp_settings.data_dir / "llm_config.json"
    assert config_file.exists()
    assert json.loads(config_file.read_text(encoding="utf-8")) == {"providers": {"openai": {
        "base_url": cfg["base_url"], "model": cfg["model"], "api_key": cfg["api_key"],
    }}}

    r = requests.get(server + "/api/llm/config", timeout=5)
    assert r.status_code == 200
    assert r.json()["providers"]["openai"] == {
        "base_url": cfg["base_url"], "model": cfg["model"], "api_key": cfg["api_key"],
    }


def test_llm_config_requires_provider(server, temp_settings):
    """PUT 未指定 provider 时返回 400。"""
    r = requests.put(server + "/api/llm/config", json={"base_url": "https://x/v1"}, timeout=5)
    assert r.status_code == 400


def test_llm_config_saves_empty_fields(server, temp_settings):
    """清空 Key 后写入空字符串，应如实保存（允许保存"无 Key"状态）。"""
    config_file = temp_settings.data_dir / "llm_config.json"
    requests.put(
        server + "/api/llm/config",
        json={"provider": "ollama", "base_url": "http://127.0.0.1:11434/v1", "model": "", "api_key": ""},
        timeout=5,
    )
    slots = requests.get(server + "/api/llm/config", timeout=5).json()["providers"]
    assert slots["ollama"] == {"base_url": "http://127.0.0.1:11434/v1", "model": "", "api_key": ""}
    assert json.loads(config_file.read_text(encoding="utf-8"))["providers"]["ollama"]["api_key"] == ""


def test_llm_models_uses_saved_config(monkeypatch, server, temp_settings):
    """请求未带 base_url/api_key 时，兜底使用该提供商本地保存的配置。"""
    requests.put(
        server + "/api/llm/config",
        json={"provider": "openai", "base_url": "https://saved.example.com/v1", "api_key": "sk-saved"},
        timeout=5,
    )
    seen = {}

    def fake(base_url, api_key):
        seen["base_url"] = base_url
        seen["api_key"] = api_key
        return ["gpt-4o"]

    monkeypatch.setattr("app.main._fetch_models", fake)
    r = requests.post(server + "/api/llm/models", json={"provider": "openai"}, timeout=5)
    assert r.status_code == 200
    assert r.json()["source"] == "api"
    assert seen["base_url"] == "https://saved.example.com/v1"
    assert seen["api_key"] == "sk-saved"


def test_provider_config_not_leaked(monkeypatch, server, temp_settings):
    """切换提供商后兜底不会串用另一家已保存的 Key / Base URL（回归：deepseek Key 误用于别家）。"""
    requests.put(
        server + "/api/llm/config",
        json={"provider": "deepseek", "base_url": "https://api.deepseek.com/v1", "api_key": "sk-ds"},
        timeout=5,
    )
    requests.put(
        server + "/api/llm/config",
        json={"provider": "openai", "base_url": "https://api.openai.com/v1", "api_key": "sk-oa"},
        timeout=5,
    )
    # 两家互不覆盖
    slots = requests.get(server + "/api/llm/config", timeout=5).json()["providers"]
    assert slots["deepseek"] == {"base_url": "https://api.deepseek.com/v1", "model": "", "api_key": "sk-ds"}
    assert slots["openai"] == {"base_url": "https://api.openai.com/v1", "model": "", "api_key": "sk-oa"}

    seen = {}

    def fake(base_url, api_key):
        seen["base_url"] = base_url
        seen["api_key"] = api_key
        return ["x"]

    monkeypatch.setattr("app.main._fetch_models", fake)
    # 请求指定 openai：兜底必须用 openai 槽位，而不是 deepseek 的 Key
    r = requests.post(server + "/api/llm/models", json={"provider": "openai"}, timeout=5)
    assert r.status_code == 200
    assert seen == {"base_url": "https://api.openai.com/v1", "api_key": "sk-oa"}


def test_llm_config_migrates_flat_format(server, temp_settings):
    """旧版扁平结构（单提供商）自动迁移为分槽结构，不丢 Key，且文件立即回写自愈。"""
    config_file = temp_settings.data_dir / "llm_config.json"
    config_file.write_text(
        json.dumps(
            {"provider": "deepseek", "base_url": "https://api.deepseek.com/v1",
             "model": "deepseek-chat", "api_key": "sk-old"}
        ),
        encoding="utf-8",
    )
    r = requests.get(server + "/api/llm/config", timeout=5)
    slots = r.json()["providers"]
    assert slots["deepseek"] == {"base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat", "api_key": "sk-old"}
    # 迁移同时回写磁盘：再次读取即是分槽结构
    assert json.loads(config_file.read_text(encoding="utf-8")) == {"providers": {"deepseek": {
        "base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat", "api_key": "sk-old",
    }}}


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
