# Agent Trace 制作数据集的最小字段需求

> 问题：如果我们要使用 Agent 实际执行的轨迹（Trace）来制作数据集，然后通过 ReflACT 算法让 Skill 变得更好，从而让 Agent 更好，那么 Agent Trace 至少需要哪些东西才能保证制作数据集？

本文基于项目代码的实际消费点（`skillopt/types.py`、`skillopt/gradient/reflect.py`、`skillopt/envs/base.py`、`skillopt/optimizer/slow_update.py`、`skillopt/datasets/base.py`）梳理得出。

**结论先行：一条 Agent Trace 必须 = 任务输入 + 执行过程 + 结果评估 + 溯源信息，且能通过稳定 `id` 与数据集 item 和 skill 版本对齐。**

---

## 一、最小必需字段（缺一不可）

### 1. 身份与关联键（join key）

| 字段 | 说明 | 消费点 |
|---|---|---|
| `id` | 稳定唯一任务 ID | 贯穿全流程：`predictions/<id>/conversation.json` 的定位、失败/成功分组、纵向对比对齐都靠它 |

没有 `id`，轨迹无法与 item、评估结果、前后两次 rollout 关联，整个数据集无从建起。

### 2. 任务输入（任务是什么）

| 字段 | 说明 | 消费点 |
|---|---|---|
| `question` / `task_description` | 任务指令原文 | Reflect 阶段轨迹头部、纵向对比的 `task` 字段（`optimizer/slow_update.py` 的 `build_comparison_pairs`） |
| `task_type` | 任务类型标签 | 按类型统计成功率分桶、代表性样本多样性挑选 `select_representative_items`（`envs/base.py`） |
| `target_system_prompt` / `target_user_prompt` | Agent 当时看到的完整提示（含当时的 skill） | Analyst 需要知道"Agent 看到了什么"才能归因（`gradient/reflect.py` 的 `fmt_minibatch_trajectories` 会读这两个文件） |

### 3. 执行过程（Agent 做了什么）—— `conversation.json`

这是 Trace 的核心，`fmt_trajectory`（`gradient/reflect.py`）接受两种格式（至少满足其一）：

```jsonc
// 格式A：工具调用记录
{"type": "tool_call", "cmd": "<执行的动作/命令>", "obs": "<环境返回的观察>"}

// 格式B：步骤记录（推荐，多一个 reasoning）
{"step": 1, "reasoning": "<思考>", "action": "<动作>", "env_feedback": "<观察>"}

// 可选：事后验证信息（docvqa 实际写入的格式，rollout.py 会把
// Question / Predicted / Gold / ANLS 明细 append 到 conversation 末尾）
{"role": "system", "content": "Question... Predicted: ... Gold: ... ANLS: 0.85"}
```

关键点：

- **每步必须有 action + observation**；
- `reasoning` 可选但强烈建议保留——它是 Analyst 区分"策略错误" vs "执行失误（EXECUTION_LAPSE）"的唯一依据（skill-aware reflection 的 appendix 机制依赖它）；
- 另外需要 `n_turns`（步数，写入轨迹头部）。

### 4. 结果与评估（做对了吗）

| 字段 | 说明 | 消费点 |
|---|---|---|
| `hard` (0/1) | 可验证的硬指标 | **整个算法的梯度信号**：失败/成功轨迹分流、Gate 接受/拒绝、纵向对比四分类（improved / regressed / persistent_fail / stable_success） |
| `soft` (0-1) | 部分得分（如 ANLS） | Gate 选择分数 `select_gate_score`、软评分机制 |
| `predicted_answer` | Agent 最终答案 | 纵向对比、失败原因分析 |
| `fail_reason` | 结构化失败原因 | 失败模式聚类 `_extract_failure_patterns`（按前缀分组）、轨迹头部 |
| **gold answer / reference**（`answers` / `ground_truth` / `reference_text`） | 标准答案/参考材料 | 若 trace 不带 `hard/soft`，必须带 gold 才能离线重算；`reference_text` 还会作为 Hidden Reference 喂给 Analyst（`envs/base.py` 的 `attach_reference_context`） |

### 5. 溯源信息（Provenance）

| 字段 | 说明 | 为什么必需 |
|---|---|---|
| `skill_version` / `skill_hash` | 本次执行所用的 skill 版本 | **Skill 优化的归因基础**。没有它无法构建"同一任务、新旧 skill 两次执行"的对比对，`build_comparison_pairs` 的 improved/regressed 分类就不可能 |
| 模型/后端标识、seed、时间戳 | 运行环境 | 数据集去重、可复现、按后端分层分析 |

---

## 二、最小 Trace 示例（单条）

```json
{
  "id": "32438",
  "task_type": "Cell-Level Manipulation",
  "question": "<任务指令原文>",
  "target_system_prompt": "<当时的 system prompt + skill>",
  "target_user_prompt": "<当时的 user prompt>",
  "n_turns": 6,
  "conversation": [
    {"step": 1, "reasoning": "...", "action": "openpyxl load workbook", "env_feedback": "..."},
    {"step": 2, "reasoning": "...", "action": "...", "env_feedback": "..."}
  ],
  "predicted_answer": "<最终产物/答案>",
  "hard": 0, "soft": 0.0,
  "fail_reason": "format_error: ...",
  "reference_text": "<gold / 期望结果>",
  "provenance": {
    "skill_hash": "a1b2c3...", "backend": "gpt-5.5", "seed": 42, "timestamp": "..."
  }
}
```

---

## 三、按算法能力的增量需求（可选但决定上限）

1. **纵向对比（slow update / 对比对）**：同一 `id` 需要在 ≥2 个 skill 版本下各有一条 trace，成对出现。
2. **Skill-aware 反思**：轨迹中的 `reasoning` + 末尾验证消息（predicted vs gold 明细），用于提取 EXECUTION_LAPSE 笔记进 appendix。
3. **软门控**：必须每个任务都能计算 `soft`（如 ANLS、部分匹配），即 gold 要保留完整可重算的形式而非只有 0/1。
4. **多样性挑选**：`task_type` 覆盖面要广，否则 `select_representative_items` 挑不出有代表性的失败/成功样本。

---

## 四、缺失后果速查

| 缺失 | 后果 |
|---|---|
| `id` | 无法与数据集/评估对齐，trace 不可用 |
| `hard` 且缺 gold | 无梯度信号，无法训练 |
| observation / action | Analyst 看不到决策依据，反思退化成瞎猜 |
| `skill_version` | 只能做"批量失败统计"，无法做 skill 前后对比的归因优化 |
| `task_type` | 无法按类型分桶分析、无法多样性采样 |

---

## 参考代码

- `skillopt/types.py` 的 `RolloutResult`：字段的权威定义
- `skillopt/gradient/reflect.py` 的 `fmt_trajectory` / `fmt_minibatch_trajectories`：轨迹格式消费
- `skillopt/envs/base.py` 的 `attach_reference_context` / `select_representative_items`：参考材料与多样性采样
- `skillopt/optimizer/slow_update.py` 的 `build_comparison_pairs`：纵向对比对构建
- `data/README.md`：数据侧 item 物化要求（各 benchmark 的必填字段）

**简言之：照着 `RolloutResult` + `conversation.json` 格式采集 trace，把 gold 和 skill_hash 一并带上，就能直接喂进现有训练循环。**
