# AGENTS.md — App Review Insights

把 App Store 评论转化为**有证据支撑的 PRD 与可追溯测试用例**的 Web 应用：FastAPI 后端（多阶段流水线 + LLM）+ Vue 3 前端。

> 文档使用中文。详细设计见 [docs/设计方案.md](docs/设计方案.md)，需求见 [docs/需求文档.md](docs/需求文档.md)，使用说明见 [README.md](README.md)。本文件只记录代理需要、且不易从代码直接发现的约定。

## 常用命令

```bash
# 后端测试（asyncio_mode=auto，testpaths=tests）
cd backend && pytest

# 启动后端（仅提供 API，端口 8000）
cd backend && uvicorn app.main:app --app-dir . --port 8000

# 前端开发（5173 端口，/api 代理到 8000；自带 HMR 热重载，改 frontend/src/* 即时生效，无需 build）
# 需同时启动后端（8000），浏览器访问 http://127.0.0.1:5173
cd frontend && npm run dev

# 前端构建 —— 产物输出到 backend/app/static（已 gitignore，不入库），仅部署时执行
cd frontend && npm run build

# 重新生成离线缓存示例（需先联网真实采集一次）
python backend/scripts/generate_cache.py --source <run_id> --limit 300
```

环境要求：Python 3.11+、Node 18+。

## 架构速览

- **后端**（`backend/app/`）：`main.py` 为唯一入口（REST + SSE）；`config.py` 环境配置；`schemas.py` Pydantic 模型；`storage.py` JSON 产物落盘 + SQLite 元数据 + 缓存回退；`pipeline/orchestrator.py` 负责调度；`llm/` 为 OpenAI 兼容客户端与提示词；`services/` 为采集/清洗/统计/导入。
- **流水线**：`orchestrator.py::_register_stages()` 注册 **8 个执行阶段**（scope→collect→clean→analyze→evidence→prd→tests→validate）；需求文档的"10 阶段"= 8 个执行阶段 + 2 个 UI 展示环节（执行进度 / 交付物展示，由前端承担）。**不要在前端硬编码阶段数量/名称**，按后端返回的 `stages` 数组渲染。每阶段继承 `BaseStage`，产物通过 `RunContext.save(name, data)` 即时落盘。
- **LLM 调用**：`RunContext.llm_call()` 用 `asyncio.to_thread` 跑同步 `LLMClient.complete_json`，避免阻塞事件循环；含重试/降级/JSON Schema 校验。
- **前端**（`frontend/src/`）：Vue 3 组合式 API（`<script setup>`），**无 router / Pinia / Vuex / axios**。页面切换靠 `store.js` 的 `reactive` 单例（`currentRun` 决定 HomeView/RunView）+ `activeTab` tab 切换；网络用原生 `fetch` 与 `EventSource`。

## 前后端契约

- **API**：`GET /api/providers`、`GET/PUT /api/llm/config`（模型配置本地持久化）、`POST /api/runs`（创建）、`GET /api/runs/{id}`、`GET /api/runs`、`GET /api/runs/{id}/artifacts/{name}`、`POST /api/llm/test`、`POST /api/llm/models`、`POST /api/runs/{id}/pause`、`POST /api/runs/{id}/resume`、`GET /api/runs/{id}/events`（SSE）。
- **SSE 事件**（`orchestrator.py` 发布）：
  - 阶段事件 = `StageResult` 序列化：含 `stage` / `label` / `status` / `summary` / `artifacts` / `revisions` 等字段（**没有** `phase`/`percent` 字段）。
  - 阶段内子进度：`StageResult` 含 `progress`(0-100) / `message`(当前子步骤) / `substeps` 字段，由阶段内 `ctx.report_progress()` 上报；**仅广播 SSE 不落盘**（`_publish_progress`），终态由 `_update_stage` 落盘时收敛 `progress=100`。前端 `ProgressPanel` 据此渲染整体/阶段进度条与实时耗时。
  - 运行事件：`{"type":"run_start",...}`（前端未处理）、`{"type":"run_end","status":...}`（前端据此更新状态，之后流结束）、`{"type":"run_paused"/"run_resumed",...}`（暂停/恢复，前端据此更新状态）。
- **状态值**：运行级 `pending/running/paused/succeeded/failed/degraded`；阶段级另有 `revised/skipped`。
- **暂停/恢复**：协作式暂停（`RunContext.pause_event` + `ensure_running()`），在 `llm_call` 前、阶段边界、`fetch_reviews` 每页前挂起；`pause_run`/`resume_run` 更新状态并广播。暂停中的运行不可删除（任务未完成）。
- **产物命名**：`scope`、`raw_reviews`、`cleaned_reviews`、`clean_report`、`themes`、`findings`、`evidence_report`、`prd`、`test_cases`、`traceability_report`、`import_data`。`validate` 阶段会**修订并重写** findings/prd/test_cases。
- **创建运行**：`POST /api/runs`（body 含 `url/goal/provider/model/base_url/api_key/import_text`）→ 再 `GET` 连 SSE。EventSource 只能 GET，不要把两者合并成单个 POST 流。

## 项目特定约定与坑

- **前端开发用 dev server 热重载，交付时才 `npm run build`**：开发调试应启动 `cd frontend && npm run dev`（5173，`/api` 代理到 8000，HMR 即时生效），**不要**每次改动都构建；`backend/app/static` 为构建产物（已 gitignore，不入库），仅在部署前执行 `npm run build`。无前端测试与 lint，改动后用 build 验证一次。
- **Key 安全**：`api_key` 后端只存运行内存（`RunContext.api_key`），**禁止**写入日志、缓存、artifact、注释、`.env` 提交；用户模型配置（含 Key）由后端持久化到 `data/llm_config.json`（已 gitignore，POSIX 下权限 600），前端通过 `GET/PUT /api/llm/config` 读写。Key 在 POST JSON body 中传输（README 同此表述）。
- **离线缓存运行**：`meta.cache === true` 时前端**完全跳过 SSE 与轮询**（HomeView 第④卡片「历史分析记录」、RunView 顶部警告横幅、`listRuns` 返回合并列表都据此区分）。新增"实时刷新"逻辑必须跳过缓存运行。
- **数据目录以项目根为基准**：`config.py` 用 `PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent`，`data_dir/cache_dir/db_path/static_dir` 默认均相对项目根 —— 无论从 `backend/` 还是根目录启动 uvicorn 都读写仓库根 `data/`（根 `data/app.db` 现有 7 条历史运行）。可用 `DATA_DIR/CACHE_DIR/DB_PATH/STATIC_DIR` 环境变量覆盖；不要改成 CWD 相对，否则从 `backend/` 启动会读到空的 `backend/data`。
- **历史分析记录**：HomeView 第④卡片用 `GET /api/runs`（DB 运行 + 缓存运行合并），前端按 `created_at` 倒序展示状态/模型/时间，点击 `openRun(r)` 设 `store.currentRun` 重开；重开已完成的历史运行走 RunView 的 SSE+轮询兜底。
- **模型配置持久化**：`store.js` 用 `watch`（防抖 500ms + `hydrated` 守卫，首次从后端读取成功前不回写）把 `provider/base_url/model/api_key` PUT 到 `GET/PUT /api/llm/config`，后端按**提供商分槽**写入 `data/llm_config.json`（已 gitignore，结构 `{"providers": {id: {base_url, model, api_key}}}`）；`App.vue` 挂载时经 `await loadLlmConfig()` 恢复，`ProviderPanel` 切换提供商时经 `savedFor(id)` 载入该家配置。**Key 会明文落盘该 JSON 文件**（用户明确要求，文件不入库、仅本机），改动时保持该行为；兜底顺序：请求值 → 该提供商槽位 → 环境变量 —— 各提供商配置互不串用，切提供商绝不带出别家的 Key/Base URL。
- **SSE 无重连**：`api.js::streamRun` 的 EventSource 未监听 `onerror`，靠 RunView 的 3s 轮询兜底 —— 改 SSE 逻辑不要破坏该兜底。
- **产物是任意 JSON**：`getArtifact` 可能返回 dict/list/标量/null，前端面板统一用 `try/catch` + `loaded` 标志兜底，别改成"失败即报错"。
- **确定性 vs 模型推断**：findings 用 `deterministic_stat`（📊）与 `model_derived`（🤖）区分；语义产物必须引用**真实存在的 `review_id`**，无证据标 `assumption=true`，这是防幻觉核心，新增模型阶段必须遵守。
- **采集**：Apple RSS 的 `page` 必须是**路径参数**（`?page=N` 无效，已实测）；串行请求 + 节流（默认 1.5s）+ 429/5xx 指数退避。
- **测试隔离**：`tests/conftest.py` 提供 `temp_settings` fixture（把数据目录指向 tmp_path），新测试应使用它；LLM 阶段测试需 mock，不要发起真实网络/Key 请求。
- **前端样式**：全局 `src/style.css` 深色主题 CSS 变量（`--bg/--panel/--border/--accent/--green/--amber/--red/--purple/--muted`），组件复用 `card`、`badge ok/warn/err/info`、`small muted`、`empty` 等约定类。
- **模型 UI 状态机**：`ProviderPanel` 的"获取模型/测试连接"用 `store.llm.modelsState/testState`（`idle|loading|ok|fail`）；改模型 UI 时保持该语义。

## 文档偏差（改代码时留意）

- 需求文档/设计方案仍称"10 阶段"，已统一口径：8 个执行阶段 + 2 个 UI 展示环节（AGENTS.md/README 同此表述）。
- README 说 Key 经 POST body 传输，与实现一致（此前"经请求头发送"的说法已修正）。
