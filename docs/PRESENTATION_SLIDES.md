# Visocode — 技术面试 Presentation 脚本

> **受众：** 技术面试官（工程 team）
> **时长：** 20 分钟（含 Q&A 缓冲）
> **结构：** 4 张 slides，叙事弧线：`痛点 → 方案 → 踩坑 → 结果`

---

## 整体时间规划

```
Slide 1  Hook & Problem          2–3 min   ████
Slide 2  Architecture            7–8 min   ████████████
Slide 3  3 Engineering Choices   7–8 min   ████████████
Slide 4  Results & Next Steps    2–3 min   ████
─────────────────────────────────────────────────────
总计                            ~20 min
```

---

## Slide 1 — Hook & Problem

### 标题（写在 slide 上）
> **"From Text to Animation in 30 Seconds — with a Reliability-First AI Pipeline"**

---

### Slide 内容布局

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│   左半：                         右半：                  │
│                                                         │
│   手动写 Manim：                  [Demo GIF / 截图]      │
│   ✗ 学习曲线陡峭                   输入 prompt →         │
│   ✗ 调试动画代码耗时数小时           30 秒后输出视频       │
│   ✗ LaTeX 环境配置复杂              [视频缩略图]          │
│                                                         │
│   ─────────────────────────────────────────────────     │
│   三个关键数字（底部横排）                                │
│   [ 首轮通过率 X% ]  [ 平均生成时间 Xs ]  [ N 层安全审计 ] │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

### 演讲稿（逐字稿）

> *开场：先播 Demo，再说话。*

"先让大家看 15 秒——"

*[播放 Demo：输入 prompt → Streamlit 显示 Pipeline 运行 → 视频出现]*

"这是 Visocode。用户输入一段自然语言描述，比如'可视化冒泡排序算法'，30 秒左右得到一个可以直接用的 Manim 动画视频，然后自动上传到 Google Drive。"

"这个问题本身不复杂——调 LLM 生成代码，跑代码，搞定。**难的是让它稳定工作。**"

"Manim 是一个高度特定领域的库，LLM 生成的代码里有大量幻觉：用了不存在的 API、忘记 import、场景太长跑超时。我在测试里见过各种失败——代码能过静态检查，一跑就崩；代码能跑完，但生成的是空白视频。"

"今天我想讲的，不是'我用 LLM 生成了代码'，而是**这个 pipeline 是怎么设计的，以及我在让它可靠这件事上做了哪些工程决策**。"

---

### 备注
- Demo 视频控制在 15 秒以内，提前录好，不要现场跑（网络、Docker 时间不可控）
- 三个关键数字提前统计好，来自 `runs.json` 的真实数据
- 最后一句话是 transition，自然引出 Slide 2

---
---

## Slide 2 — System Architecture

### 标题（写在 slide 上）
> **"A LangGraph Pipeline with Deterministic Safety Layers"**

---

### Slide 内容布局

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│  [流程图，横向展开]                                        │
│                                                         │
│  User                                                   │
│  Input ──► GENERATE ──► AUDIT ──► EXECUTE ──► UPLOAD   │
│               ▲            │         │                  │
│               │     ┌──────┘         │                  │
│               │     │ audit fail     │ exec fail        │
│               │     ▼                ▼                  │
│               └── (LLM)       DEBUGGER ──► GENERATE     │
│                                     │                   │
│                             max retries                 │
│                                     ▼                   │
│                                 FALLBACK                │
│                                                         │
│  ─────────────────────────────────────────────────────  │
│  每个节点下方标注 1 行关键技术选型（见下）                   │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

**各节点标注（写在流程图节点下方）：**
- `GENERATE`：Gemini 2.5 Pro · structured prompt · retry with compressed feedback
- `AUDIT`：Layer 1 AST scan · Layer 2 LLM Judge (Flash)
- `EXECUTE`：Docker · network_disabled · mem 1GB · timeout 120s
- `DEBUGGER`：DIAGNOSIS + FIX in 2 lines · noise filtering
- `FALLBACK`：safe script · always returns a video

---

### 演讲稿（逐字稿）

"整个 pipeline 用 LangGraph 编排，核心是这五类节点。我来逐一讲，但重点会放在三个设计决策上。"

---

**第一个决策：为什么用 LangGraph 而不是 while 循环**

"最直觉的实现是一个 while loop：生成、检查、执行，失败就重试。但这个 pipeline 的控制流不是线性的——audit 失败要回 generate，execute 失败要先经过 debugger 再回 generate，达到最大重试要走 fallback，而不是 execute。"

"用 while loop 写这个逻辑，代码会变成一堆嵌套 if/else，状态靠局部变量传递。LangGraph 让我把**拓扑结构**和**业务逻辑**分开：`_build_graph()` 里声明边和路由，节点函数只负责自己的输入输出。加一个新节点不需要改其他节点，维护成本低很多。"

---

**第二个决策：两层 Audit**

"Audit 节点有两个独立的检查器，处理两类不同性质的问题。"

"第一层是 `SecurityAuditor`，用 AST 静态分析，拦截危险 import 和 built-in。这是**确定性**的，`import os` 就是 `import os`，不依赖概率。"

"第二层是 `LLMJudgeAuditor`，用 Gemini Flash 判断代码是否真的回答了用户的问题——有没有幻觉 API、主题有没有偏。这里我刻意选了轻量模型：Judge 只需要输出 PASS 或 FAIL，不需要生成代码，用 Flash 响应更快、成本低 3-5 倍。"

"两层的关系是互补：静态分析弥补 LLM 判断的不确定性，LLM Judge 弥补静态分析无法理解语义的局限。"

---

**第三个决策：Debugger Node 是独立节点，不是 Generate 的一部分**

"执行失败后，代码里有个 `debugger_node`，它的唯一工作是：读取 traceback，提炼成两行——`DIAGNOSIS: 一句话根因` 和 `FIX: 一句话修法`。"

"为什么不直接把 traceback 丢给 Generator？因为 Manim 的完整 traceback 里有大量框架内部调用栈，跟用户代码无关。让 Generator 看 2000 行日志，信噪比极低，修复质量反而差。Debugger 先把信号提炼出来，Generator 收到的是精炼过的两行，上下文 token 用更少，修复成功率更高。"

"这是'用廉价的小任务为昂贵的大任务降噪'的思路，在 LLM pipeline 里很通用。"

---

### 备注
- 流程图建议自己用 Figma / Excalidraw 画，不要用 mermaid 代码截图
- 重点讲三个决策，每个 2 分钟左右，共 6 分钟；其余节点一带而过
- 如果面试官打断提问，这张 slide 是最容易展开讨论的，不用慌

---
---

## Slide 3 — 3 Engineering Challenges

### 标题（写在 slide 上）
> **"Three Problems I Didn't Expect — and How I Solved Them"**

---

### Slide 内容布局

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│  Problem 1       Problem 2           Problem 3          │
│  ──────────      ──────────          ──────────         │
│                                                         │
│  LLM Judge       Traceback noise     NameError          │
│  loops forever   → wrong fix         → wrong fix        │
│                                                         │
│  → audit_retry   → compress:         → ApiLookup:       │
│    _count cap      last 5 lines        error-driven     │
│                    + key signals       doc injection     │
│                                                         │
│  消除             修复成功率↑          NameError 修复     │
│  RecursionError                       更精准             │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

### 演讲稿（逐字稿）

"架构设计容易讲得漂亮，但真正有意思的是它跑起来之后遇到的问题。我选三个最有代表性的。"

---

**Problem 1：LLM Judge 循环失败，触发 GraphRecursionError**

"上线初期我发现，某些 prompt 触发后，pipeline 会跑很久，然后报一个 `GraphRecursionError`，用户看到的是空白。"

"查日志发现：LLM Judge 一直输出 FAIL，代码不断回 generate，再 audit，再 FAIL……audit 失败不计入 `retry_count`，所以熔断逻辑根本没触发，LangGraph 的节点调用次数撞上了 `recursion_limit: 50`。"

"根因是：**审计失败没有上限**，和执行失败是两套独立的计数逻辑。"

"解法：在 `GraphState` 里加了 `audit_retry_count` 字段，`audit_node` 每次失败时递增，`_route_after_audit` 在这个计数达到 `max_retries` 时直接路由到 `fallback_node`，不再继续循环。同时 `generate_node` 生成新代码时重置这个计数器——因为新代码是全新的起点，不应该带着上一轮的失败记录。"

"这个 fix 的本质是：**不同性质的失败需要独立的计数器和独立的熔断逻辑**。"

---

**Problem 2：Traceback 太长，Generator 看了也修不好**

"执行失败后，traceback 有时上千行。我最开始直接把前 2000 个字符截断丢给 Generator，效果很差——LLM 经常'修'了一个无关的地方，因为真正的错误被埋在中间。"

"分析了几十条失败日志后，发现了规律：最有价值的信息集中在两个地方——traceback 的**最后 5 行**（真正抛错的地方），以及**第一行**（Executor 写的高层错误信息，比如 'No .mp4 under ...' 或 'Timeout 120s'）。"

"解法：写了 `_compress_traceback()`，提取最后 5 行 + 最后一个 `File \"...\", line N` 定位，然后在最前面预写一行结构化信号：`TIMEOUT: 简化场景` 或 `NO OUTPUT: 代码崩溃或只产出 partial` 或 `RUNTIME ERROR: 检查 import`。"

"Generator 收到的 feedback 从 2000 个随机字符变成了 200 个有结构的字符。这不只是省 token，是在帮 LLM 做了'根因分类'，它知道该修什么方向了。"

---

**Problem 3：NameError 修不准 — 错误驱动的 API 文档注入**

"执行失败里有一大类特别顽固：`NameError: name 'Write' is not defined`。Generator 看到这个错误，大概率会随机猜测正确的写法，或者干脆换掉整段逻辑，而不是精准修复 import。"

"根因是：**LLM 收到的 feedback 只有错误信息，没有正确答案**。它要靠自己的参数记忆去猜 `Write` 的正确用法，而 Manim 的 API 版本差异很大，记忆不可靠。"

"解法：在项目里维护了一份手工精选的 `manim_api_index.json`，覆盖约 50 个最常用的 Manim 类和方法，每条包含正确的签名和一个 runnable 的示例。`debugger_node` 里加了 `ApiLookup`，它从 traceback 里正则提取错误的符号名，然后直接查 index，把匹配到的文档片段追加进 `debugger_hint`。"

"Generator 在下一次 retry 里收到的不只是'Write 没有定义'，而是："

```
DIAGNOSIS: Missing import for Write animation class.
FIX: Add Write to the manim import statement.

[Manim API — Write] Animates writing a Text or VMobject stroke by stroke.
  Signature: Write(mobject, run_time=1, **kwargs)
  Example:   self.play(Write(Text('Hello')))
```

"这是从'告诉 LLM 哪里错了'升级到'告诉 LLM 正确答案是什么'。精准度提升明显，NameError 类错误的首次修复成功率大幅提高。"

"这个设计背后的原则是：**错误驱动的精粒度检索比生成时的泛检索更有价值**——我知道具体哪个 API 出问题了，就直接给它正确文档，而不是盲目注入一堆可能无关的 API 说明。"

---

### 备注
- 三个问题各控制在 2-2.5 分钟，合计约 7 分钟
- 每个 Problem 讲完后停顿 1-2 秒，给面试官打断提问的空间
- Slide 上只放关键词，细节靠口头讲，不要把演讲稿写上去
- 如果时间紧，Problem 1 最重要；Problem 2 和 3 可以合并成"反馈质量的两个维度：压缩 + 精准文档"

---
---

## Slide 4 — Results & What's Next

### 标题（写在 slide 上）
> **"What It Can Do Now — and What I'd Build Next"**

---

### Slide 内容布局

```
┌─────────────────────────────────────────────────────────┐
│                                                         │
│  左半：Results                  右半：If I Had More Time  │
│  ──────────────────             ──────────────────────  │
│                                                         │
│  📊 首轮通过率：X%              1. 任务队列 + 异步         │
│  ⏱ 平均耗时：~Xs               (Celery / Redis)         │
│  🎬 已生成视频：N 个             让 UI 不阻塞              │
│  🔒 安全拦截：2 层               2. 每任务独立目录          │
│                                 消除文件竞态              │
│  [2–3 个视频截图缩略图]          3. 流式进度反馈            │
│   Bubble Sort / FFT / etc.      实时展示渲染日志           │
│                                 4. Full Manim Docs RAG  │
│                                 按语义分块 + 向量数据库    │
│                                                         │
│  ─────────────────────────────────────────────────────  │
│  Key Takeaway（底部居中，大字）                           │
│  "Reliability in LLM pipelines comes from              │
│   deterministic layers, not better prompts."           │
│                                                         │
└─────────────────────────────────────────────────────────┘
```

---

### 演讲稿（逐字稿）

"最后来看结果和反思。"

**Results（1 分钟）**

"从 `runs.json` 的数据来看，首轮通过率在 X% 左右——也就是说，超过半数的请求第一次就能生成可用视频，不需要 retry。平均生成时间大约 Xs，大部分时间花在 Docker 渲染上。"

"这几个是实际生成的视频——冒泡排序、傅里叶变换、梯度下降。"

*[指着截图，简单说一句每个是什么]*

---

**What's Next（1 分钟）**

"如果继续做，我会优先改三件事。"

"第一：任务队列。现在所有的 LLM 调用和 Docker 等待都是同步阻塞的，Streamlit 在等待期间卡住。改成 Celery + Redis 任务队列，把渲染任务放到后台 Worker，前端用 WebSocket 接收进度，这是从 demo 到产品最关键的一步。"

"第二：每个任务用独立的 UUID 子目录。现在所有请求共享 `manim_output/`，并发场景下 `_collect_output_files` 取'最新的 .mp4'，可能拿到别人的文件。这个 bug 在单用户场景无感，并发一高就会出现竞态。"

"第三：流式进度反馈。生成视频要 30 秒到几分钟，用户盯着转圈体验很差。LLM 生成阶段可以用 `stream=True` 实时展示代码，执行阶段可以 tail Docker 容器日志，展示渲染进度百分比。"

"第四，也是我最想做的：**完整的 Manim 文档 RAG**。现在我维护的 API index 是手工精选的 50 条，覆盖最常见的场景。下一步是把完整的 Manim v0.18 官方文档按语义分块——不是按 token 切，而是每个 class 或 method 作为一个独立 chunk——存入向量数据库，生成时基于用户意图粗粒度检索，retry 时基于错误精粒度检索。手工精选的信噪比高，完整文档的覆盖率高，两种策略可以并存：先查静态 index，没命中再查向量数据库，形成两级检索。"

---

**Closing（30 秒）**

"最后想说一个更大的感受——"

"这个项目让我意识到：在 LLM pipeline 里，**可靠性不是靠写更好的 prompt 得到的，而是靠在 prompt 之外加确定性的保护层**。静态分析、计数器、超时、熔断——这些传统软件工程的手段，在 AI 系统里同样关键，甚至更关键。"

*[停顿]*

"就这些，有什么问题欢迎展开聊。"

---

### 备注
- Results 数字一定要是真实数据，面试官可能追问"这个数字怎么来的"
- 视频截图选视觉上最好看的 2-3 个，不要放太多
- Key Takeaway 那句话要背下来，作为全场最后一句，干净有力
- "就这些，有什么问题欢迎展开聊"——比"谢谢大家"更专业，更自信

---
---

## 附：各 Slide 视觉设计建议

| Slide | 主色调 | 关键视觉元素 | 避免 |
|-------|--------|------------|------|
| Slide 1 | 深色背景（#0d1117）+ 渐变文字 | Demo GIF / 视频截图为主 | 大段文字 |
| Slide 2 | 深色 + 蓝色节点边框 | 自绘流程图（Figma/Excalidraw） | 截代码、用 mermaid 截图 |
| Slide 3 | 每个 Problem 用不同强调色 | 简洁图示（❌ → ✅）| 大段对话框 |
| Slide 4 | 深色 + 视频缩略图 | 数字大字体，截图作点缀 | 过多 bullet points |

---

## 附：常见追问准备

| 追问 | 简短回答方向 |
|------|------------|
| "为什么选 Gemini 不选 GPT-4？" | API 免费额度、langchain-google-genai 接口简单；核心架构模型无关，换成 GPT 改一行代码 |
| "LLM Judge 会误判吗？" | 会。Judge 是软约束，误判会多消耗一次 retry，但不会导致错误视频被送达用户，因为还有执行层兜底 |
| "Docker 镜像冷启动很慢吧？" | 第一次 pull 慢，之后有本地缓存。生产环境可以预热一个常驻容器池，减少每次 cold start |
| "runs.json 并发写入怎么处理？" | 当前没处理，MVP 单用户场景问题不大。下一步换 SQLite + WAL 模式，天然支持并发写入 |
| "为什么不用 CrewAI 或者 AutoGen？" | 这个 pipeline 的节点交互是确定性的，不需要 Agent 之间自由通信。LangGraph 的显式图结构比 CrewAI 的隐式编排更容易 debug 和测试 |
| "通过率 X% 你觉得高吗？" | 诚实说有进步空间。Prompt 优化、更严格的 Judge、RAG 注入历史成功案例，都是可以做的方向 |

---

*文档版本：v1.0 · 2026-02 · 基于技术面试场景撰写*
