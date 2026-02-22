# Visocode：现状架构与目标路线图

本文档基于**当前代码实现**梳理「已有什么」「还缺什么」，并给出可落地的目标结构图与实现路线图，便于面试时对齐话术与真实实现。

---

## 一、当前架构（已实现）

### 1.1 流水线结构图（现状）

```
                    ┌─────────────────────────────────────────────────────────┐
                    │  LangGraph StateGraph                                    │
                    │  State: user_prompt, current_code, error_message,       │
                    │         retry_count, output_path, status, drive_link     │
                    └─────────────────────────────────────────────────────────┘
                                              │
     ┌────────────────────────────────────────┼────────────────────────────────────────┐
     │                                        ▼                                        │
     │   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐   │
     │   │  generate_   │───►│  audit_      │───►│  execute_    │───►│  upload_     │   │
     │   │  node        │    │  node        │    │  node        │    │  node        │   │
     │   └──────┬───────┘    └──────┬───────┘    └──────┬───────┘    └──────────────┘   │
     │          │                   │                   │                                │
     │          │  Gemini           │  SecurityAuditor  │  SandboxExecutor               │
     │          │  (单一模型)        │  (仅 AST 规则)     │  或 LocalExecutor             │
     │          │                   │  无 LLM            │  timeout=120s, mem_limit=1g    │
     │          │                   │                   │                                │
     │          │  ◄────────────────┼── audit 失败      │                                │
     │          │  ◄───────────────────────────────────┼── execute 失败且 retry<max     │
     │          │                   │                   │  retry≥max → END（无兜底视频）   │
     └──────────┼───────────────────┼───────────────────┼────────────────────────────────┘
                │                   │                   │
                │ 重试时：整段        │                   │
                │ error_message     │                   │
                │ 仅截断 2000 字     │                   │
                │ （非「最后 5 行」）  │                   │
                └───────────────────┴───────────────────┘
```

### 1.2 当前实现清单

| 模块 | 已实现 | 说明 |
|------|--------|------|
| **编排** | ✅ | LangGraph StateGraph，单图：generate → audit → execute → upload；路由：audit 失败回 generate，execute 失败且 retry_count < max_retries 回 generate，否则 END。 |
| **Generate** | ✅ | 单节点、单模型（Gemini）。无独立 Planner/Coder；直接「用户描述 + 系统 Prompt」生成 Manim 代码。`ManimCodeGenerator` 类存在但**未参与生成**，由 orchestrator 内直接调 `_llm.invoke`。 |
| **Audit** | ✅ 仅规则 | 仅 **SecurityAuditor**：AST 扫描，禁止 `os`/`sys`/`exec`/`eval`/`subprocess` 等。**无 LLM-as-Judge**，无废弃 API 检查。 |
| **Execute** | ✅ | **SandboxExecutor**（Docker，无网络、mem_limit=1g、timeout=120s）+ **LocalExecutor**（本机 manim）。 |
| **重试与熔断** | ✅ 部分 | **retry_count** + **max_retries**（默认 3），达上限后 `status=max_retries_exceeded` 并 END。**无**兜底视频、**无**降级页面。 |
| **错误反馈** | ✅ 部分 | `_build_feedback()`：对 `[EXECUTE]` 的 traceback **按长度截断 2000 字**，**未**做「最后 5 行 + 行号」的智能压缩。 |
| **Upload** | ✅ | Drive：服务账号 或 OAuth（个人 Gmail），固定文件夹 ID。 |
| **前端 / CLI** | ✅ | Streamlit app + `run.py`，dotenv、runs.json 持久、last_run_error 展示。 |

---

## 二、与「面试叙事」的差距（未实现）

| 面试叙事中的点 | 当前实现状态 | 差距简述 |
|----------------|--------------|----------|
| **编导 Agent (Planner)** | ❌ | 无独立分镜/步骤拆解；Generate 一步到位。 |
| **开发 Agent (Coder)** | ⚠️ 名义存在 | `ManimCodeGenerator` 未参与调用；由 orchestrator 直接调 Gemini。 |
| **审计 Agent 双重审查** | ✅ | 第一道 SecurityAuditor（AST）；第二道 LLMJudgeAuditor（PASS/FAIL + REASON）。 |
| **修复 Agent (Debugger)** | ✅ | 独立 **debugger_node**：执行失败后先走 Debugger（LLM 输出 DIAGNOSIS + FIX），再回 generate_node 修代码。 |
| **上下文压缩（最后 5 行）** | ✅ | Traceback 提取器：最后 5 行 + `File "…", line N`；重试时只传压缩 feedback。 |
| **熔断 + 降级视频** | ✅ | max_retries 后走 **fallback_node** 渲染安全脚本；`is_fallback` 与前端「降级视频」提示。 |
| **可量化的幻觉减少** | ✅ | runs.json 记录每笔 `first_try`（首轮即成功）；前端展示「一次通过率 X/Y (Z%)」。 |

---

## 三、目标架构（路线图终点）

### 3.1 目标结构图（To-Be）

```
                    ┌─────────────────────────────────────────────────────────────────┐
                    │  RAG（可选）                                                     │
                    │  runs.json 成功案例 / 规则与示例 chunk → 注入 Generate 或 Judge   │
                    └────────────────────────────┬────────────────────────────────────┘
                                                 │
┌─────────────┐     ┌────────────────────────────┼────────────────────────────┐
│   Prompt    │     │                            ▼                            │
│ (前端/CLI)   │────►│  generate_node (可拆为 Planner→Coder 或保持单节点)        │
└─────────────┘     │  - 可选 RAG 增强                                            │
                    │  - 重试时只接收「压缩反馈」：Traceback 最后 5 行 + 行号          │
                    └────────────────────────────┬────────────────────────────┘
                                                 │ current_code
                                                 ▼
                    ┌────────────────────────────┴────────────────────────────┐
                    │  audit_node                                              │
                    │  第一道：SecurityAuditor（AST，不变）                      │
                    │  第二道：LLM Judge（低成本模型，PASS/FAIL + 废弃 API/幻觉）  │
                    └────────────────────────────┬────────────────────────────┘
                                                 │ passed
                                                 ▼
                    ┌────────────────────────────┴────────────────────────────┐
                    │  execute_node（不变）                                    │
                    │  Docker/Local，timeout + mem_limit                        │
                    └────────────────────────────┬────────────────────────────┘
                                                 │
                         ┌──────────────────────┼──────────────────────┐
                         │ 成功                  │ 失败                  │
                         ▼                      ▼                      │
                    upload_node             retry_count < max?         │
                         │                      │ 是 → 回 generate     │
                         │                      │ 否 → 熔断             │
                         │                      ▼                      │
                         │              ┌───────────────┐              │
                         │              │ Fallback 策略  │              │
                         │              │ 预设安全短视频  │              │
                         │              │ + 错误提示     │              │
                         │              └───────────────┘              │
                         ▼
                    END（output_path / drive_link）
```

### 3.2 目标功能清单（与路线图对应）

| 目标项 | 说明 | 优先级 |
|--------|------|--------|
| **上下文压缩** | 提取 Traceback 最后 5 行 + `File "…", line N`，重试时只传该 payload 给 generate，不传整段日志。 | P0 |
| **熔断 + 兜底视频** | 当 `status == max_retries_exceeded` 时，渲染一份预设安全 Manim 脚本，得到兜底视频并返回，前端展示「降级结果 + 提示」。 | P0 |
| **LLM-as-Judge** | 新增 Judge 审计器（低成本模型 + 严格 Prompt），输出 PASS/FAIL + 原因；可检查废弃 API/明显幻觉；与 SecurityAuditor 串联。 | P1 |
| **Planner / Coder 拆分** | 可选：先 Planner 将需求拆成步骤/分镜，再 Coder 按步骤生成代码；或保持单节点，仅优化 Prompt。 | P2 |
| **RAG** | 用 runs.json 或规则 chunk 检索，注入 Generate/Judge 的上下文。 | P2 |
| **通过率统计** | 记录「引入 Judge 前后」一次性通过率，用于量化「幻觉减少」。 | P2 |

---

## 四、实现路线图（建议顺序）

```
Phase 1（约 1h）  上下文压缩 + 熔断兜底
    ├── 实现 traceback 提取器（最后 5 行 + 行号）
    ├── generate_node 重试时只传压缩后的 feedback
    └── max_retries 时写死一个安全 Manim 脚本并渲染，结果写入 output_path / 单独字段

Phase 2（约 2h）  LLM-as-Judge
    ├── 新增 LLMJudgeAuditor（或类似），调用低成本模型
    ├── 系统 Prompt：仅输出 PASS/FAIL + 一行 REASON；可含「废弃 API / 幻觉」检查
    ├── 在 audit_node 中 SecurityAuditor 通过后再跑 Judge
    └── 解析 FAIL 时 error_message 写入原因，回 generate

Phase 3（可选）   分工与 RAG
    ├── 可选：Planner 节点（或仅在 Prompt 中显式分镜）
    ├── 可选：用 ManimCodeGenerator 封装生成逻辑，orchestrator 只调 generator
    ├── RAG：runs.json 成功样本检索 → 注入 generate 的 user prompt
    └── 简单通过率统计（成功次数/总次数，按配置开关记录）
```

---

## 五、面试话术与实现对应表

| 面试说法 | 建议对应实现 | 当前是否可讲 |
|----------|--------------|----------------|
| 「多 Agent 协作，编导 / 开发 / 审计 / 修复」 | 当前：Generate + Audit + Execute 三节点；修复由同一 Generate 重试。目标：可加 Judge、可拆 Planner/Coder。 | 可讲「编排与角色分工」，不提「四个独立 Agent」除非做完拆分。 |
| 「上下文压缩，只传 Traceback 最后 5 行」 | Phase 1：提取器 + 重试时只传压缩 payload。 | 做完 Phase 1 后可如实讲。 |
| 「AST 第一道 + LLM Judge 第二道」 | 当前：仅 AST。Phase 2：加 Judge。 | 先讲 AST；Judge 做完再讲第二道。 |
| 「沙盒隔离、timeout、mem_limit」 | 已实现（Docker 无网、1g、120s）。 | ✅ 可直接讲。 |
| 「熔断与降级备用视频」 | Phase 1：max_retries 时兜底视频 + 提示。 | 做完 Phase 1 后可讲。 |
| 「RAG 增强生成」 | Phase 3：runs.json 检索注入。 | 做完 Phase 3 再讲。 |

---

## 六、执行失败原因与改进（为何「不能直接渲染」）

**现象**：部分提示词（如「讲解回溯算法 + 状态树 + 代码 + 复杂度」）第一次生成后 Execute 报错，日志里只有 "Partial movie file" 或 "No .mp4"，重试多次仍失败。

**原因归纳**：

1. **场景过重**：模型倾向于生成「讲课式」长动画（多段文字、多步动画），渲染时间超过 LocalExecutor 的 120s 或中途异常，Manim 只写出 partial 未合并成最终 .mp4。
2. **错误信息被压缩丢关键信息**：只传「最后 5 行」给 Generate，若真正原因是 "Timeout" 或 "No .mp4 under ..."，可能被压到后面，模型看不到「超时/无输出」的明确信号。
3. **未约束时长**：系统 Prompt 未要求「场景尽量短」，复杂需求容易生成超长 construct。

**已做改进**：

- **反馈里保留关键信号**：在 `_compress_traceback` 中识别 "Timeout"、"No .mp4"、"NameError"/"AttributeError"，在压缩内容前**预填一行结论**（如 "TIMEOUT: 简化场景"、"NO OUTPUT: 简化或修 bug"），让 Generate 明确知道是超时/无输出/运行时错误。
- **系统 Prompt 第 10 条**：要求场景保持 SHORT（总动画约 20–30 秒内），减少超时与只出 partial 的情况。

**可选后续**：若仍常超时，可将 LocalExecutor 的 `timeout` 调大（如 180s）或在 run.py 中按需传入；或对「讲解/教学类」提示在 Prompt 中显式写「用 3–5 个短动画概括即可」。

---

## 七、小结

- **当前**：单 Generate 节点（Gemini 3 Pro / 2.5 Flash）+ AST + LLM Judge（2.5 Flash）+ Debugger + 执行（Local/Docker）+ 熔断兜底 + 压缩反馈（含 Timeout/No .mp4 等关键信号）+ 通过率统计。
- **目标**：在不动主流程的前提下，先做**上下文压缩**和**熔断兜底**（Phase 1），再做 **LLM-as-Judge**（Phase 2），最后按需做分工细化与 RAG（Phase 3）。本文档中的「当前结构图」与「目标结构图」可作为实现与面试表述的统一参照。
