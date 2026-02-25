# Visocode 系统架构图

> Updated: 2026-02-24

---

## 整体架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          Streamlit UI (app.py)                               │
│                                                                               │
│   pages/                                                                      │
│   ├── 🎬 Generate Video    ← 主功能: 输入 prompt → 触发 pipeline              │
│   └── 📊 Presentation      ← 项目介绍页 (白/蓝主题)                          │
└─────────────────────────────────────┬───────────────────────────────────────┘
                                      │ calls orchestrator.run()
┌─────────────────────────────────────▼───────────────────────────────────────┐
│                    WorkflowOrchestrator (LangGraph StateGraph)                │
│                                                                               │
│   GraphState: {user_prompt, current_code, error_message, retry_count,        │
│                output_path, status, drive_link, debugger_hint,                │
│                is_fallback, audit_retry_count}                                │
│                                                                               │
│  START                                                                        │
│    │                                                                          │
│    ▼                                                                          │
│  ┌──────────────────────────────────────────────────────┐                    │
│  │             generate_node                             │                    │
│  │  • 首次: user_prompt + RAG few-shot examples          │◄──────────────┐  │
│  │  • 重试: user_prompt + 上次代码 + 错误 + debugger_hint │               │  │
│  │  • LLM: Gemini 2.5 Pro (temperature=0.2)             │               │  │
│  └──────────────────────────────┬───────────────────────┘               │  │
│                                  │ current_code                          │  │
│    ┌─────────────────────────────▼───────────────────────┐              │  │
│    │               audit_node (fail-fast)                 │              │  │
│    │  ① SecurityAuditor (AST): 禁止 os/sys/subprocess/    │              │  │
│    │     eval/exec/open 等危险 import & 内置函数           │─── fail ────►│  │
│    │  ② LLMJudgeAuditor: Gemini 2.5 Flash 审核代码质量    │  (audit_retry│  │
│    │     检查 import 完整性、Scene 类结构、复杂度           │   count++)   │  │
│    └──────────┬──────────────────────────────────────────┘              │  │
│               │ pass                            │ fail >= max_retries    │  │
│               ▼                                 ▼                        │  │
│  ┌────────────────────────┐         ┌──────────────────────┐            │  │
│  │      execute_node      │         │    fallback_node      │            │  │
│  │  SandboxExecutor:      │         │  运行安全兜底脚本      │            │  │
│  │  • docker run          │ fail    │  (VisocodeMaxRetries  │            │  │
│  │  • manimcommunity/     │────────►│   Scene)              │            │  │
│  │    manim:stable        │         └──────────┬───────────┘            │  │
│  │  • --no-network        │                    │ success                 │  │
│  │  • memory: 512m        │                    │                         │  │
│  │  • timeout: 120s       │ success            │                         │  │
│  └──────────┬─────────────┘                    │                         │  │
│             │ fail (retry_count++)              │                         │  │
│             ▼                                  │                         │  │
│  ┌────────────────────────┐                   │                          │  │
│  │     debugger_node      │                   │                          │  │
│  │  • _compress_traceback │                   │                          │  │
│  │  • LLM: DIAGNOSIS+FIX  │                   │                          │  │
│  │  • ApiLookup (RAG②)    │──────────────────────────────────────────►──┘  │
│  │    NameError/AttrError │  debugger_hint injected into next generate      │
│  └────────────────────────┘                   │                             │
│             │ (max_retries>=3)                 │                             │
│             ▼                                  │                             │
│  ┌────────────────────────────────────────────▼────────┐                    │
│  │                   upload_node                         │                    │
│  │   DriveUploader: Google Drive API v3                  │                    │
│  │   → 上传 .mp4 → 返回 webViewLink                      │                    │
│  └──────────────────────────────┬────────────────────────┘                   │
│                                  │                                             │
│                                 END                                            │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## RAG 系统（两路）

```
┌──────────────────────────── RAG 系统 (两路) ──────────────────────────────────┐
│                                                                                │
│  ① RunsRetriever (Few-shot, generate_node 首次调用)                            │
│     runs.json (成功运行历史)                                                   │
│     ──► sentence-transformers all-MiniLM-L6-v2                                │
│     ──► cosine similarity (numpy dot product)                                  │
│     ──► Top-2 similar examples 注入 prompt (cold start 优雅降级)               │
│                                                                                │
│  ② ApiLookup (Error-driven, debugger_node 调用)                                │
│     error traceback ──► regex 提取 symbol 名                                  │
│       (NameError / AttributeError / ImportError)                               │
│     ──► manim_api_index.json (57 条 Manim API 文档)                            │
│     ──► 精准注入 signature + example → debugger_hint                           │
│                                                                                │
└────────────────────────────────────────────────────────────────────────────────┘
```

### 两路 RAG 对比

| | RunsRetriever (Tier 1) | ApiLookup (Tier 2) |
|---|---|---|
| 触发时机 | generate_node 首次调用 | debugger_node 每次调用 |
| 数据来源 | runs.json (成功运行历史) | manim_api_index.json (57条静态文档) |
| 检索方式 | sentence-transformers 语义相似度 | regex 提取 + 精确匹配 |
| 向量维度 | 384-dim (all-MiniLM-L6-v2) | 无向量，纯 key-value |
| 作用 | 提供风格/结构指引 (few-shot) | 注入精确 API 文档消除猜测 |
| cold start | 优雅降级，返回 [] | 静态文件，始终可用 |

---

## 节点详细说明

### generate_node
- **模型**: Gemini 2.5 Pro (`temperature=0.2, top_p=0.95`)
- **首次**: 注入 RAG few-shot examples + user_prompt
- **重试**: previous_code + error_message + debugger_hint
- **输出**: `{current_code, error_message: "", debugger_hint: "", audit_retry_count: 0}`

### audit_node (fail-fast)
- **SecurityAuditor**: AST 静态扫描，禁止 `os/sys/subprocess/eval/exec/open` 等
- **LLMJudgeAuditor**: Gemini 2.5 Flash 语义审核，检查 import 完整性、Scene 结构
- **防无限循环**: `audit_retry_count >= max_retries` → 路由到 `fallback_node`

### execute_node
- **执行器**: `manimcommunity/manim:stable` Docker 容器
- **隔离**: `network_disabled=True`, `mem_limit=1g`, `cpu_quota=50000`, `timeout=120s`
- **命令**: `manim -qm --media_dir /manim/workspace scene.py [ClassName]`

### debugger_node
- **压缩 traceback**: `_compress_traceback()` 提取关键 5 行 + 错误分类标签
- **LLM 诊断**: Gemini 2.5 Flash → `DIAGNOSIS: ... / FIX: ...` 两行
- **API 注入**: `ApiLookup.suggest_for_error()` → 精确 Manim API 文档

### fallback_node
- 运行最小安全脚本 (`VisocodeMaxRetriesScene`)
- 确保用户始终获得输出，避免空白屏

### upload_node
- **OAuth**: `DriveUploaderOAuth` (token.json)
- **Service Account**: `DriveUploader` (credentials.json)
- 上传失败不影响主流程（best-effort）

---

## 基础设施

```
┌──────────────────────────── 基础设施 ────────────────────────────────────────┐
│  Docker: manimcommunity/manim:stable                                          │
│    - 容器内渲染, 隔离, 无网络, 512m RAM, 0.5 CPU                              │
│  Google Drive API: OAuth2 (token.json) + Service Account (credentials.json)   │
│  LLM: Gemini 2.5 Pro (生成) + Gemini 2.5 Flash (审核/调试)                   │
│  Deployment: Docker Compose                                                    │
│    - Port: 8501 (Streamlit)                                                   │
│    - Volume: /var/run/docker.sock (Docker-in-Docker)                          │
│    - Volume: ./manim_output (持久化输出 + runs.json)                          │
└────────────────────────────────────────────────────────────────────────────────┘
```

---

## 关键设计决策

| 决策 | 选择 | 原因 |
|------|------|------|
| 流程编排 | LangGraph StateGraph | 条件路由清晰，节点解耦，内置递归限制 |
| 双层审计 | AST + LLM Judge | AST 快速确定性 + LLM 语义检查互补 |
| 两个重试计数器 | audit_retry_count + retry_count | 审计失败 ≠ 执行失败，策略不同 |
| Debugger 节点 | traceback 压缩 + API 注入 | 减少 LLM 上下文噪声，提高修复精准度 |
| Docker 沙箱 | manimcommunity/manim | 隔离、安全、可复现 |
| 上传策略 | best-effort | 渲染成功是核心目标，上传失败不应阻断 |
| LLM 选型 | Pro 生成 + Flash 审核 | Pro 质量高，Flash 3-5× 更便宜用于简单决策 |

---

## 文件结构

```
visocode/
├── app.py                  # Streamlit UI + session 管理
├── orchestrator.py         # LangGraph 工作流 (主 pipeline)
├── executor.py             # Docker 沙箱 + LocalExecutor
├── auditor.py              # LLM Judge + AST 安全审计
├── generator.py            # 数据结构定义 (legacy)
├── retriever.py            # RAG: RunsRetriever + ApiLookup
├── uploader.py             # Google Drive 上传
├── run.py                  # CLI 入口
├── manim_api_index.json    # 手工整理的 Manim API 参考 (57条)
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── deploy.sh
└── docs/
    ├── ARCHITECTURE.md          ← 本文件
    ├── PRESENTATION_SLIDES.md
    ├── INTERVIEW_QUESTIONS.md
    └── RAG_AND_AGENTIC_STRATEGY.md
```
