# Visocode — RAG 实现 & Agentic Workflow 面试策略

> **适用场景：** 技术面试中被问到 RAG、Agentic Workflow、Multi-Agent System 相关话题时的应对指南。
> 本文档分两部分：① RAG 的实现细节与设计决策；② Agentic Workflow 的话术框架（无需再写代码）。

---

## Part 1：RAG 实现

### 1.1 为什么在这里用 RAG

Manim 是一个高度特定领域的库。LLM 在生成 Manim 代码时有两类典型失败：

1. **API 幻觉**：使用了不存在的 Manim 方法、漏写 import
2. **风格偏差**：生成的动画结构不符合"在规定时间内能跑完"的约束

引入 RAG 的核心思路是：**用历史成功案例作为 few-shot 示例，给 LLM 提供"什么样的代码在这个系统里真的能跑成功"的具体参照**。这比在 system prompt 里堆规则更直接，因为示例本身就携带了所有隐含约束。

---

### 1.2 架构位置

```
User Prompt
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  generate_node（首次生成）                            │
│                                                     │
│  ┌──────────────────┐   ┌─────────────────────────┐ │
│  │  RunsRetriever   │   │  Gemini LLM             │ │
│  │                  │   │                         │ │
│  │  runs.json       │──►│  System Prompt          │ │
│  │  (embedding 检索) │   │  + Few-shot Examples    │ │
│  │                  │   │  + User Request         │ │
│  └──────────────────┘   └─────────────────────────┘ │
│                                                     │
│  ※ Retry 时不注入 RAG（error feedback 优先）          │
└─────────────────────────────────────────────────────┘
    │
    ▼
audit_node → execute_node → ...
```

**关键设计：RAG 只在首次生成时注入，Retry 时不注入。**

原因：Retry 时 LLM 已经有了具体的错误信息（traceback + debugger hint），这时候 few-shot 示例反而会分散注意力，干扰错误修复的焦点。

---

### 1.3 实现文件：`retriever.py`

```
retriever.py
└── class RunsRetriever
        ├── get_examples(user_prompt) → list[dict]   # 公共接口
        ├── _load_candidates()                        # 读 runs.json，过滤成功且有 code 的记录
        └── _encode(texts)                            # sentence-transformers 编码，L2 归一化
```

#### 检索流程

```
user_prompt
    │
    ▼ _encode()
query_vector (D,)
    │
    ▼ corpus_vecs @ query_vec  ← runs.json 所有成功记录的 prompt embeddings (N, D)
scores (N,)  ← 余弦相似度（已归一化，等同点积）
    │
    ▼ argsort 取 Top-K
[{prompt, code}, ...]
```

#### 关键实现决策

| 决策点 | 选择 | 原因 |
|--------|------|------|
| Embedding 模型 | `all-MiniLM-L6-v2` | 约 80MB，CPU 可用，语义相似度准确，推理快（100 条 < 1s） |
| 相似度计算 | 余弦相似度（归一化向量的点积） | 对向量长度不敏感，句子长短不影响结果 |
| 每次请求是否重新加载 runs.json | 是 | 文件小（≤100条），新成功案例无需重启即可被检索 |
| model 加载时机 | 懒加载（首次 `_encode` 时加载） | 不影响应用启动速度，不用时零开销 |
| 注入上限 | Top-2，每条 code 截断至 1200 chars | 控制 token 用量；2 个示例够用，更多会干扰 |

#### 冷启动处理

`runs.json` 里没有带 `code` 字段的成功记录时（全新部署或历史记录未存 code），`get_examples()` 返回空列表，`generate_node` 降级为 zero-shot 生成，**主流程不受任何影响**。

---

### 1.4 `orchestrator.py` 改动

在 `generate_node` 的首次生成路径中加入 RAG 注入：

```python
# 首次生成
examples = self._retriever.get_examples(state["user_prompt"])
if examples:
    parts = [
        f"Request: {ex['prompt']}\n```python\n{ex['code']}\n```"
        for ex in examples
    ]
    few_shot = (
        "Here are similar successful Manim scenes for reference "
        "(study style and structure — do NOT copy verbatim):\n\n"
        + "\n\n---\n\n".join(parts)
        + "\n\n---\n\n"
    )
else:
    few_shot = ""

user_content = (
    f"{few_shot}"
    f"Create a Manim animation scene for the following request:\n\n"
    f"{state['user_prompt']}"
)
```

注入策略的三个细节：

1. **"do NOT copy verbatim"**：防止 LLM 直接复制示例代码，强迫它理解后再创作
2. **`---` 分隔符**：明确区分每个示例，减少 LLM 把示例内容和任务混淆的概率
3. **few_shot 放在 user_content 开头而不是 system prompt**：用户消息比 system 消息更靠近生成位置，影响更直接

---

### 1.5 `app.py` 改动

`_append_run` 新增 `code` 参数，把生成的 Manim 代码持久化到 `runs.json`：

```python
def _append_run(prompt, status, video_path=None, drive_link="", attempts=0, code=""):
    ...
    runs.insert(0, {
        ...,
        "code": code,  # 新增：RAG 检索时使用
    })
```

成功时调用：
```python
_append_run(
    user_script,
    pipeline_result.status.value,
    video_path=video_path,
    drive_link=...,
    attempts=...,
    code=st.session_state.current_code,  # 新增
)
```

---

### 1.6 数据流：一次完整的 RAG 增强生成

```
第 1 次生成（冷启动）
    runs.json 无 code 记录 → get_examples() = [] → zero-shot 生成 → 成功
    → runs.json 写入 {prompt, code, status:"success", ...}

第 2 次类似请求
    get_examples("类似 prompt") → Top-2 similar
    → few-shot 注入 → LLM 参照风格生成 → 成功率↑
    → 新记录写入 runs.json

随时间积累
    runs.json 成功案例增多 → 检索覆盖范围增广 → RAG 效果持续改善
```

---

## Part 2：Agentic Workflow 面试话术

这部分**不需要再写代码**。现有架构已经完整体现了 Agentic Workflow 的三个核心特征，只需要知道怎么表达。

---

### 2.1 三个核心特征及对应实现

#### 特征 1：自主决策（Autonomous Decision-making）

Agent 根据环境反馈自主决定下一步行动，不依赖人工干预。

```
条件路由函数就是 Agent 的决策逻辑：

_route_after_audit():
    if audit_retry_count >= max_retries → fallback（放弃，走降级）
    elif error_message                  → generate（重试，带错误反馈）
    else                                → execute（通过，继续执行）

_route_after_execute():
    if status == "success"              → upload
    elif retry_count < max_retries      → debugger（失败，先分析）
    else                                → fallback
```

这不是简单的 if/else，而是基于**运行时观测结果**的自主判断，每个路由函数是一个独立的 decision-making 单元。

#### 特征 2：工具使用（Tool Use）

Agent 调用外部工具完成不同类型的任务。

```
生成工具：Gemini LLM API（通过 langchain-google-genai）
安全审计工具：AST 静态分析（SecurityAuditor）
质量判断工具：LLM Judge（LLMJudgeAuditor — 独立的 LLM 调用）
执行工具：Docker sandbox / 本地 manim CLI
存储工具：Google Drive API
检索工具：sentence-transformers + runs.json（RAG）
```

每个工具职责单一，通过 `GraphState` 共享数据，节点之间不直接耦合。

#### 特征 3：反思与自修正（Reflection & Self-correction）

Agent 观察自己的输出，发现错误，自主修正。

```
Observe:  execute_node 返回失败 → error_message 携带 traceback
Think:    debugger_node 分析根因 → 输出 "DIAGNOSIS: ... FIX: ..."
Act:      generate_node 读取 debugger_hint + error_message → 重写代码

这是完整的 Observe → Think → Act 循环，
每次循环后 Agent 的行为因为上一次的失败而改变。
```

---

### 2.2 一句话定义（面试开场用）

> "Visocode 是一个 multi-agent system，通过 LangGraph 编排六个专职节点（生成、安全审计、LLM Judge、调试、执行、上传），节点间通过共享状态（GraphState）通信，条件路由函数作为 decision-making 层，实现了 Observe-Think-Act 的完整自修正循环。"

---

### 2.3 和常见框架的对比（面试被追问时）

| 比较对象 | Visocode 的选择 | 理由 |
|---------|---------------|------|
| vs AutoGen | LangGraph 显式图 | 节点交互是确定性的，不需要 Agent 自由通信；显式图更易 debug 和测试 |
| vs CrewAI | LangGraph 显式图 | CrewAI 适合角色扮演型任务；本项目的流程是固定 DAG，显式图更合适 |
| vs 普通 while 循环 | LangGraph StateGraph | 分支逻辑复杂（审计失败/执行失败/熔断走不同路径），DAG 表达比嵌套 if/else 更清晰 |

---

### 2.4 RAG 和 Agentic Workflow 的关系（综合回答）

当面试官问"你的 Agentic Workflow 里有没有用到 RAG？"时：

> "有。RAG 集成在 generate_node 里——每次首次生成时，retriever 从历史成功案例里检索最相似的 Top-2 示例，注入 LLM 的 user message 作为 few-shot context。这让 Agent 在生成代码时不只依赖 system prompt 的规则，还能参照'什么样的代码在这个 pipeline 里真的能跑通'的具体例子，把外部知识库（runs.json）作为动态工具使用。"

---

## Part 3：今天不要做的事

| 想法 | 建议 | 原因 |
|------|------|------|
| 加 Planner Node | ❌ 不做 | 改动大，容易引入 bug，现有架构已有足够的 Agentic 故事 |
| 实现 `ManimCodeGenerator` | ❌ 不做 | 死代码，面试里直接说"预留接口，当前 generate_node 直接调 LLM" |
| 加任务队列（Celery） | ❌ 不做 | 今天时间不够做好，作为"If I had more time"讲即可 |
| 加更多 LangGraph 节点 | ❌ 不做 | 主流程已稳定，别在面试前冒险引入新路径 |
| 换更大的 embedding 模型 | ❌ 不做 | `all-MiniLM-L6-v2` 对这个场景完全够用，换模型只增加冷启动时间 |

---

## Part 4：今天的时间分配

```
上午
  2h  实现 retriever.py + requirements.txt
  1h  接入 orchestrator.py（__init__ + generate_node）
  1h  修改 app.py（_append_run 加 code 字段）

下午
  1h  跑 3-5 次验证（冷启动 → 首次成功 → 第二次类似请求看 RAG 效果）
  1h  更新 PRESENTATION_SLIDES.md 加 RAG 讲法
  剩余时间  收尾、保存、转移到下个项目
```

---

## Part 5：常见追问 & 回答

| 追问 | 回答要点 |
|------|---------|
| "embedding 用什么模型？为什么？" | `all-MiniLM-L6-v2`，80MB，CPU 可用，推理快，语义准确。如果规模扩大可以换 `text-embedding-3-small`（OpenAI）或 `voyage-code-2`（专门针对代码） |
| "相似度怎么计算？" | 余弦相似度。向量 L2 归一化后，余弦相似度等于点积，计算快且对向量长度不敏感 |
| "冷启动怎么处理？" | `get_examples()` 返回 `[]`，`generate_node` 里 `few_shot = ""`，自动降级为 zero-shot，主流程无感知 |
| "为什么只注入首次生成，不注入 retry？" | Retry 时 LLM 需要专注于修复具体错误（traceback + debugger hint），few-shot 示例会分散注意力，实验证明去掉更好 |
| "runs.json 里有多少条数据？" | 最多保留 100 条记录（`runs[:100]`），RAG 只检索其中有 `code` 字段的成功条目 |
| "这算不算真正的 RAG？" | 是的。核心三要素：Retrieval（embedding 相似度检索）、Augmented（注入 prompt 增强 context）、Generation（LLM 生成代码）。区别于 fine-tune：零部署成本，实时更新，可解释 |
| "向量数据库为什么不用 Chroma / Pinecone？" | 数据量小（≤100条），实时 embedding 计算延迟可接受（< 1s）。引入向量数据库是过度工程，增加运维复杂度但收益有限。规模扩大后再考虑 |

---

*文档版本：v1.0 · 2026-02 · 基于 Visocode RAG 实现整理*
