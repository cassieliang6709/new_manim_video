# Visocode 系统架构：现状与 LLM-as-Judge / RAG 演进

## 一、当前架构总览

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Prompt    │────►│  Generate   │────►│   Audit     │────►│  Execute    │────►│   Upload    │
│ (前端/CLI)   │     │ (Agent G)   │     │ (Agent C)   │     │ (Manim)     │     │ (Drive)     │
└─────────────┘     └──────┬──────┘     └──────┬──────┘     └──────┬──────┘     └─────────────┘
                          │                    │                    │
                          │  Gemini 2.5        │  规则引擎           │  Docker / Local
                          │  (单一模型)         │  SecurityAuditor   │  manim CLI
                          │                    │  AST 白名单/黑名单   │
                          ▼                    ▼                    ▼
                    current_code         passed?              .mp4 → output_path
                          │                    │ 否 → 回 generate
                          │                    │ 是 → execute
                          └────────────────────┘
```

### 1.1 组件角色（现状）

| 角色 | 实现 | 职责 |
|------|------|------|
| **Agent G（生成）** | `orchestrator.generate_node` + Gemini | 根据用户描述 + 系统 Prompt 生成 Manim 代码；失败时根据 `error_message` 重试生成。 |
| **Agent C（审计）** | `SecurityAuditor`（规则） | 基于 AST 做**规则判断**：禁止 `os`/`sys`/`exec`/`eval` 等；无 LLM 调用。 |
| **Execute** | `SandboxExecutor` / `LocalExecutor` | 在 Docker 或本机执行 `manim`，产出 `.mp4`。 |
| **Upload** | `DriveUploader` / `DriveUploaderOAuth` | 将成功渲染的视频上传到固定 Drive 文件夹。 |

### 1.2 数据流与状态

- **状态**：LangGraph `GraphState`（`user_prompt`, `current_code`, `error_message`, `retry_count`, `output_path`, `status`, `drive_link`）。
- **路由**：audit 不通过 → 回 generate；execute 失败且未达 max_retries → 回 generate；execute 成功 → upload → END。

---

## 二、LLM as a Judge（Agent C 升级为裁判模型）

### 2.1 现状局限

- **SecurityAuditor** 只做「规则判断题」：AST 扫描，硬编码禁止项。无法判断：
  - 代码是否**语义上**符合用户意图；
  - 是否可能**运行时**出错（如未导入 `Write`）；
  - 风格/可读性是否达标。

### 2.2 引入 Agent C（Judge）的思路

- **角色**：专门的「裁判」Agent，只做**判断题**（通过 / 不通过 + 简短理由），不生成代码。
- **模型选择**：用**成本低、延迟低**的模型即可，例如：
  - **GPT-4o-mini**（OpenAI）
  - **Llama 3**（本地或 API）
  - **Gemini Flash**（与生成模型区分开，或同厂商不同档位）
- **严格系统 Prompt**：约束输出格式（如 `PASS`/`FAIL` + 一行原因），便于解析和路由。

### 2.3 与现有架构的衔接

- **方案 A（并行）**：保留现有 `SecurityAuditor` 做安全门；新增 `LLMJudgeAuditor`，在规则通过后再调一次 Judge 模型，对 `(user_prompt, current_code)` 做语义/质量判断。
- **方案 B（替代部分规则）**：用 Judge 替代「难以用规则描述的检查」（如「是否可能缺 import」），规则只保留硬性安全项（exec/eval/网络等）。

```
当前:  generate → [SecurityAuditor 规则] → execute
演进:  generate → [SecurityAuditor 规则] → [LLM Judge] → execute
                        ↑                      ↑
                    快速 AST                 低成本模型
                    必过安全门                语义/质量判断题
```

### 2.4 Judge 的系统 Prompt 示例（思路）

- 输入：`user_prompt`（用户描述）、`current_code`（待审代码）、可选 `error_message`（上一轮执行/审计错误）。
- 输出约定：例如 `PASS` 或 `FAIL`，以及一行 `REASON: ...`。
- 系统 Prompt 要点：
  - 只判断：是否满足用户描述、是否可能缺 import/明显运行时错误、是否仅用允许的 manim API。
  - 不做代码生成；不输出代码；仅输出判定与一行原因。

---

## 三、RAG 在系统中的位置

### 3.1 可用的「检索」来源

| 来源 | 内容 | 用途 |
|------|------|------|
| **runs.json** | 历史成功/失败记录（prompt、code、status、video_path） | 检索「与当前 prompt 相似且成功」的 Manim 片段，作为 few-shot 或参考。 |
| **规则/最佳实践** | 现有系统 Prompt 中的规则（禁止 MathTex、必须 import、相对定位等） | 做成结构化文档或 chunk，RAG 时注入到 Generate 或 Judge 的上下文。 |
| **Manim 官方示例** | 官方文档或精选示例代码 | 按「场景类型」检索，增强 Generate 的上下文。 |

### 3.2 RAG 可增强的节点

- **Agent G（Generate）**：
  - 用户描述 → 检索「相似历史成功案例」的代码片段或 prompt–code 对，拼进 system/user prompt，做 **retrieval-augmented generation**。
  - 或检索「与当前场景相关的规则/示例」chunk，减少幻觉、统一风格。
- **Agent C（Judge）**：
  - 检索「常见失败模式」或「判定准则」文档，让 Judge 的决策更一致（例如「缺 Write 必须 FAIL」）。

### 3.3 实现顺序建议

1. **先做 Judge（LLM-as-Judge）**：不加 RAG，仅用「严格 Prompt + 低成本模型」做判断题，验证流程与效果。
2. **再为 Generate 做 RAG**：用 `runs.json` 中成功样本做检索（按 prompt 或 code 的简单 embedding 相似度），注入到 generate 的上下文。
3. **最后考虑规则/示例 RAG**：若规则或示例文档增多，再上 chunk + 检索，供 Generate 或 Judge 使用。

---

## 四、演进后的架构草图

```
                    ┌─────────────────────────────────────────┐
                    │  RAG（可选）                              │
                    │  - runs.json 成功案例                     │
                    │  - 规则/示例 chunk                         │
                    └──────────────┬──────────────────────────┘
                                   │ 检索增强
                                   ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Prompt    │────►│  Generate   │────►│   Audit     │────►│  Execute    │
│             │     │ (Agent G)   │     │ (Agent C)   │     │             │
└─────────────┘     │ + RAG 上下文│     │ 规则+Judge  │     └──────┬──────┘
                    └──────┬──────┘     └──────┬──────┘            │
                           │  Gemini         │ 规则 AST           │
                           │ (主模型)         │ + 低成本 Judge     │
                           │                 │ (GPT-4o-mini/     │
                           │                 │  Llama/Gemini Flash)│
                           ▼                 ▼                    ▼
                    current_code         PASS/FAIL            upload → END
                                         + REASON
```

---

## 五、小结

| 方向 | 目的 | 建议 |
|------|------|------|
| **LLM as Judge（Agent C）** | 在规则审计之外增加「语义/质量」判断题，且控制成本 | 用低成本快速模型 + 严格系统 Prompt，输出 PASS/FAIL+REASON；与现有 SecurityAuditor 并行或部分替代。 |
| **RAG** | 让生成更稳、Judge 更一致 | 先用 runs.json 成功案例增强 Generate；再视需要为规则/示例做检索，供 Generate 或 Judge 使用。 |

当前文档对应你「真实去做 LLM as a Judge 和 RAG」的架构思考；具体接口（如 `LLMJudgeAuditor` 的入参、与 orchestrator 的衔接）可在实现时再细化到代码层面。
