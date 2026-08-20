# App Review Insights

把 App Store 用户评论转化为**有证据支撑的产品需求文档（PRD）与可追溯测试用例**的可运行 Web 应用。

输入一条美国区 App Store 应用链接（或导入 JSON/CSV 评论数据）+ 分析目标 + 模型配置，系统自动执行 **10 阶段工作流**，在 UI 中实时展示进度、中间产物与最终交付物。

> 核心能力：**模型驱动语义分析**（动态主题发现 / 问题整合 / 基于证据的发现 / PRD / 测试用例）+ **确定性规则**（采集 / 清洗去重 / 统计 / 可追溯性验证），结论严格区分"确定性统计"与"模型推断"。

---

## 功能特性

- 🔗 输入美国区 App Store 链接（内置示例 `workout-for-women-home-gym`），自动采集 Apple 官方 RSS Review Feed
- 📥 支持导入 **JSON / CSV** 评论数据集（格式见 [导入格式](#导入格式)）
- 🎯 自由指定分析目标/约束（订阅转化、可用性、特定版本、仅低分评论……），系统动态确定分析范围
- 🧠 **内置多 LLM 提供商**（OpenAI / Anthropic / DeepSeek / Gemini / 本地 Ollama / 自定义），选择后填写 Key 即可使用；Key 仅存本机（本地配置文件，不入库）
- 🔄 10 阶段流水线：范围确定 → 采集 → 清洗去重 → **模型驱动分析** → 证据评估 → PRD → 测试用例 → **可追溯性验证**，SSE 实时进度
- 🧾 每个发现均附**来源评论、样本数、置信度、冲突证据、不确定性**；统计结论与模型结论分区展示
- ✅ 评论 → 发现 → 需求 → 测试用例 全链路自动校验，无依据结论被删除 / 修订 / 标注为假设
- 💾 内置**离线缓存示例**（数据真实采集，语义产物明确标注为演示），无网 / 无 Key 时也可完整评审
- 📜 **历史分析记录**：以往运行（状态 / 模型 / 时间）在首页集中列出，一键重开查看全部中间产物与最终交付物
- 🔒 **模型配置持久化**：各提供商的 Base URL / 模型名 / API Key 独立保存到服务器本地 `data/llm_config.json`（已 gitignore，不入库），刷新不丢失、切换提供商不串用；Key 仅存本机，同一服务多设备/多浏览器共享同一份配置

---

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 18+（仅构建前端需要）

### 1. 安装后端依赖

```bash
cd backend
pip install -r requirements.txt
```


### 2. 构建前端

构建产物（`backend/app/static/`）为可再生成文件，**不入库**（已 gitignore）。首次使用或修改前端源码后需构建一次：

```bash
cd frontend
npm install
npm run build          # 产物输出到 backend/app/static
```

### 3. 启动

```bash
cd backend
uvicorn app.main:app --app-dir . --port 8000
```

打开 http://127.0.0.1:8000 即可使用。

### 4. 运行测试

```bash
cd backend
pytest
```

---

## 使用方法

1. **输入链接**：默认已填示例链接 `https://apps.apple.com/us/app/workout-for-women-home-gym/id839285684`，可改为任意美国区链接；或切换到"导入评论数据"上传 JSON/CSV 文件。
2. **设置目标**：填写分析目标（如"订阅转化"），或点击快捷标签。
3. **选择模型**：选择提供商 → 自动带出 Base URL 与模型 → 填写 API Key（Ollama 本地可留空）→ 可点"测试连接"。
4. 点击**开始**，观察 10 阶段进度；完成后在 Tab 中查看：
   - 原始评论 / 清洗数据 / 主题分类 / 发现（📊统计 vs 🤖模型）/ 证据报告 / PRD / 测试用例 / 追溯报告
5. **无网 / 无 Key**：首页"④ 离线缓存示例"可直接打开完整结果。

---

## 数据采集方法（数据源与局限）

**数据源**：Apple 官方接口，优于"抓取页面可见内容"：

| 接口 | 用途 |
| --- | --- |
| `https://itunes.apple.com/lookup?id={APP_ID}&country=us&entity=software` | 应用元数据（名称、版本、平均分、评分总数） |
| `https://itunes.apple.com/{country}/rss/customerreviews/page={N}/id={APP_ID}/sortBy=mostRecent/json` | 客户评论（JSON，每页 50 条） |

**实现要点**：
- `page` 必须作为**路径参数**（`?page=N` 会被忽略并返回同一批数据，已实测验证）。
- 串行请求 + 间隔节流（默认 1.5s）+ 429/5xx 指数退避，遵守速率限制。
- 每条评论映射字段：`id`、`title`、`content`、`im:rating`、`im:version`、`updated`、`author.name`。

**局限（结果中如实标注，不伪造数据）**：
- 无认证，每页 50 条，最多约 10 页（约 500 条），仅覆盖近期评论；
- 无评论总量元数据，无法获知"全部评论"规模；
- 字段以 feed 实际返回为准。

**导入数据**：来源与真实性由导入者负责，系统在结果中标注。

---

## 模型配置（AI 需求）

内置 Provider Registry（`backend/app/llm/providers.json`），统一 OpenAI 兼容协议：

| 提供商 | 默认 Base URL | 需 Key |
| --- | --- | --- |
| OpenAI | `https://api.openai.com/v1` | 是 |
| Anthropic (Claude) | `https://api.anthropic.com/v1` | 是 |
| DeepSeek | `https://api.deepseek.com/v1` | 是 |
| Google Gemini | `https://generativelanguage.googleapis.com/v1beta/openai` | 是 |
| Ollama（本地） | `http://localhost:11434/v1` | 否 |
| 自定义 | 用户填写 | 视厂商 |

**安全**：Key 经 POST body 传输，仅存于**本次运行的后端内存**与本地配置文件 `data/llm_config.json`（已 gitignore，仅本机可见，禁止提交）；禁止写入 `.env`、日志、缓存、数据库。环境变量仅作无 UI 兜底。

**防幻觉措施**：
- 所有语义输出使用 JSON Schema 结构化 + 客户端校验；
- 提示词硬性约束：只能引用输入中真实存在的 `review_id`，禁止编造；无证据必须标注 `assumption=true`；统计数字不得改写；
- 分析类任务温度 0.2、写作类 0.4；
- **确定性复核**：代码校验每个发现引用的评论 ID 真实性、`supporting_count` 与证据数一致（不一致自动修订并记录）；
- **阶段 8 可追溯性验证**：删除 / 修订 / 标注假设 三选一处理无依据结论。

**故障处理**：LLM 超时/限流 → 指数退避重试 2 次 → JSON 解析失败重新生成 1 次 → 仍失败则阶段**降级**为"证据不足/需模型"，结果透明标注，不伪造。

---

## 各阶段技术选型说明（为什么用规则 / 统计 / 模型）

| 阶段 | 方式 | 理由 |
| --- | --- | --- |
| 范围确定、URL 解析、目标约束 | 确定性规则 | 可复现、可审计、零成本 |
| 数据采集 | 规则 + 节流 | 合法接口、避免异常负载 |
| 字段标准化、精确/近似去重（Jaccard≥0.85）、语言识别 | 确定性规则 + 轻量检测 | 确定性问题，结果可复现、无幻觉风险 |
| 动态主题发现、问题整合、发现生成、PRD、测试用例 | **语言模型** | 语义理解、跨语言、泛化到未见过的输入与目标 |
| 统计指标（样本数、评分/版本分布） | 统计方法 | 精确、权威 |
| 证据充分性、可追溯性验证 | 确定性规则 | 最后的校验防线，删除/修订/标注假设 |

---

## 缓存数据（离线评审）

`data/cache/` 内置一个离线缓存运行：
- **数据真实**：评论采集自 Apple 官方 RSS Feed（Workout for Women，300 条）；
- **语义产物为演示**：主题 / 发现 / PRD / 测试用例由 `backend/scripts/generate_cache.py` 按规则生成，`meta.json` 标注 `cache=true` 与说明，UI 顶部有醒目"⚠ 缓存演示数据"横幅；
- 缓存**仅用于离线评审**，不替代联网 + Key 时对未见过的输入（新链接 / 新数据集 / 新目标）的实时处理能力。

重新生成缓存：

```bash
# 先真实采集一次（联网），再：
python backend/scripts/generate_cache.py --source <真实run_id> --limit 300
```

---

## 导入格式

**JSON**（数组，或 `{"reviews": [...]}` 包裹）：

```json
[
  {"id": "1", "title": "标题", "content": "正文", "rating": 2,
   "version": "8.5.0", "lang": "en", "country": "us", "date": "2026-06-01T10:00:00Z", "author": "alice"}
]
```

**CSV**（UTF-8，表头）：

```csv
id,title,content,rating,version,lang,country,date,author
1,标题,正文,2,8.5.0,en,us,2026-06-01T10:00:00Z,alice
```

必填：`id` / `title` / `content` / `rating`（1–5）；其余可选。导入数据同样经过清洗 → 去重 → 全流程分析。

---

## 项目结构

```
├── backend/
│   ├── app/
│   │   ├── main.py               # FastAPI 入口 + 静态托管 + SSE
│   │   ├── config.py             # 环境配置
│   │   ├── schemas.py            # Pydantic 数据模型（发现/PRD/用例…）
│   │   ├── storage.py            # JSON 落盘 + SQLite 元数据 + 缓存
│   │   ├── llm/
│   │   │   ├── client.py         # OpenAI 兼容客户端（重试/降级）
│   │   │   ├── providers.json    # Provider Registry
│   │   │   └── prompts.py        # 语义阶段系统提示词（防幻觉约束）
│   │   ├── services/
│   │   │   ├── appstore.py       # Apple RSS/Lookup 采集
│   │   │   ├── clean.py          # 清洗/去重
│   │   │   ├── importing.py      # JSON/CSV 导入
│   │   │   └── stats.py          # 确定性统计
│   │   └── pipeline/
│   │       ├── orchestrator.py   # 10 阶段状态机 + SSE + 线程池 LLM
│   │       └── stages/           # scope/collect/clean/analyze/evidence/prd/tests/validate
│   ├── scripts/generate_cache.py # 离线缓存示例生成
│   └── tests/                    # pytest（21 项：清洗/导入/追溯/模型驱动链路）
├── frontend/                     # Vue 3 + Vite（构建到 backend/app/static）
├── data/
│   ├── cache/                    # 离线缓存示例（提交）
│   └── runs/                     # 运行时数据（gitignore）
├── docs/                         # 需求文档 / 设计方案
├── .env.example
└── README.md
```

---

## 评估标准对照

| 评估点 | 实现 |
| --- | --- |
| 数据真实可复现、来源与局限清晰 | Apple 官方接口采集；局限在结果与本文档如实说明 |
| 清洗/分类/分析揭示具体用户问题 | 阶段 3 清洗去重 + 阶段 4 模型驱动主题/发现 |
| 模型驱动超越固定规则、可泛化 | 主题/问题/发现/PRD/用例均由 LLM 动态生成，无硬编码分类 |
| 发现区分证据/统计/模型/不确定性/矛盾 | `kind` 字段 + UI 分区 + 置信度/冲突/不确定性字段 |
| PRD 基于用户问题、边界/优先级/版本清晰 | 阶段 6 生成需求+版本拆分，引用发现与评论 |
| 测试用例覆盖 PRD 且可追溯到评论 | 阶段 7 用例关联需求与评论；阶段 8 双向校验 |
| UI 清晰展示工作流与结果、本地可运行 | 10 阶段进度 + 9 个交付物 Tab；一条命令启动 |
| 运行期展示模型驱动语义分析 | LLM 客户端、提示词、降级策略文档化并实际运行 |

---

## 技术栈

- 后端：Python 3.11+ / FastAPI / Pydantic v2 / httpx / openai SDK
- 前端：Vue 3 + Vite（FastAPI 静态托管）
- 存储：JSON 文件（产物）+ SQLite（运行元数据）
- 测试：pytest（含 pytest-asyncio）
