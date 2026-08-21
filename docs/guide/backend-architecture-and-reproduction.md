# Backend 架构与 SpreadsheetBench 复现笔记

> 本文总结了关于 SkillOpt 的 backend 架构、chat/exec 后端区别、以及使用 GLM-5.2 复现 SpreadsheetBench 实验的完整过程。

---

## 1. Optimizer Backend vs Target Backend

SkillOpt 采用**双后端分离架构**:用一个模型优化 skill,用另一个模型执行任务。

### 角色定位

| 维度 | Optimizer Backend (优化器后端) | Target Backend (目标后端) |
|---|---|---|
| **角色** | "教师" — 分析轨迹、生成编辑补丁、评判打分 | "学生" — 使用当前 skill 执行任务 (rollout),是最终部署模型 |
| **负责阶段** | Reflect / Aggregate / Select / Update / Judge / LLM mining | Rollout (attempt) |
| **类比** | 产生"梯度"的模型 | 被训练/被部署的模型 |

核心定义见 `skillopt/backend.py` 中 `DualBackend` 的文档字符串:

- `attempt` → **TARGET** backend (skill 部署的模型)
- `reflect` → **OPTIMIZER** backend (写编辑的更强/更便宜的模型)
- `judge` → **OPTIMIZER** backend (无本地规则时由 optimizer 评分)

### 支持的后端白名单不同

这是两者最关键的不对称性,定义在 `skillopt/model/backend_config.py`:

- **Optimizer 白名单较小**: 仅支持 chat 类后端 + `codex_exec`。因为 optimizer 必须能产出文本编辑。
- **Target 白名单更大**: 除 chat 类后端外,还包含 exec 执行框架 (`claude_code_exec`、`cursor_exec`、`copilot_exec`),它们会启动一个编码 agent 对 benchmark 工作区进行实际执行。

能力矩阵:

| Backend | Optimizer | Target |
|---|:---:|:---:|
| `openai_chat` / `openai_compatible` / `claude_chat` / `qwen_chat` / `minimax_chat` / `copilot_chat` | ✓ | ✓ |
| `codex_exec` | ✓ | ✓ |
| `claude_code_exec` / `cursor_exec` / `copilot_exec` | — | ✓ |

### 配置与派发

- **配置键**: `model.optimizer_backend` + `model.optimizer` + `OPTIMIZER_*` 环境变量 vs `model.target_backend` + `model.target` + `TARGET_*` 环境变量
- **派发入口**: `skillopt/model/__init__.py` 中 `chat_optimizer()` / `chat_optimizer_messages()` 检查 `get_optimizer_backend()`;`chat_target()` / `chat_target_messages()` 检查 `get_target_backend()`。Exec 类 target 不走 chat 合约,而是通过 `codex_harness.py` 及环境特定的 rollout 代码集成。

### 角色解析

`skillopt/engine/trainer.py` 的 `_resolve_role_backends()` 负责将高层级 `--backend` 标签映射为 `(optimizer, target)` 角色对。例如 `cursor_exec` 会被解析为 optimizer=`openai_chat`、target=`cursor_exec`。

### 设计目的

这种分离是**跨模型优化实验**的基础:你可以用便宜/强的模型优化 skill,再部署到另一个 (target) 模型上运行——这正是 `DualBackend` 和 sleep 子系统的 transfer/sweep 实验所实现的 "optimize cheap, deploy expensive (or vice versa)" 场景。

---

## 2. Chat Backend vs Exec Backend 在评估上的区别

### 核心区别:代码生成方式不同,评分方式相同

无论用哪种后端,最终评分用的是同一个 `skillopt/envs/spreadsheetbench/evaluator.py` (官方 SpreadsheetBench 评估的忠实移植)。区别完全在于**解决方案代码是怎么产生的**。

### 对比表

| 维度 | Chat Backend | Exec Backend |
|---|---|---|
| **模型能力** | 无状态文本生成器,无工具、无文件系统 | 完整编码 agent (Codex/Claude Code),有 Read/Bash 工具 |
| **输入** | 仅看到截断的工作簿文本预览 (`_preview_workbook`) | 拿到真实的 `input.xlsx` 文件,可直接读取检查 |
| **代码来源** | 从 LLM 返回文本中用正则提取 ` ```python ` 代码块 (`extract_code`) | 从 agent 写到磁盘的 `solution.py` 文件读取 |
| **工作区** | 无工作区,纯文本交互 | 创建完整工作区: `SKILL.md` + `task.md` + `run_solution.py` + `input.xlsx` (`_prepare_codex_workspace`) |
| **自验证** | 无法自己运行代码;由 harness 执行后把错误作为文本反馈 | agent 可以自己运行 `python run_solution.py` 验证后再提交 |
| **mode=multi** | 支持多轮:LLM 生成→harness 执行→反馈错误→LLM 重试 (最多 `max_turns` 轮) | **不支持**,被 `adapter.py:setup()` 硬限制为 `mode=single` |
| **mode=single** | 一次 LLM 调用生成代码就结束 | 一次 agent 会话,agent 自主探索后写出 `solution.py` |
| **沙箱隔离** | 无 | 有: `_validated_add_dirs` 拒绝暴露敏感数据目录, `run_solution.py` 清理环境变量 |
| **结构化输出** | 自由文本 | 强制 `ANSWER_SCHEMA` JSON 结构 |

### 实际影响

1. **Exec backend 更强**: agent 能实际读取 Excel 文件、检查数据、运行测试代码自验证,然后才提交最终方案。Chat backend 只能凭文本预览"盲猜"代码。
2. **但 Exec 限制更多**: 只支持 `mode=single` (不能多轮修复),且需要安装对应 CLI (Codex/Claude Code)。Chat backend 支持 `mode=multi` 多轮迭代修复。
3. **论文默认配置**: 当前 `configs/spreadsheetbench/default.yaml` 使用 `mode: multi` + chat backend (`openai_compatible`),这是论文的 paper-style 设置。

---

## 3. 后端判断与分发机制

### 判断函数

```python
# skillopt/model/backend_config.py:164-165
def is_target_exec_backend() -> bool:
    return TARGET_BACKEND in {"codex_exec", "claude_code_exec", "cursor_exec", "copilot_exec"}
```

这个函数只检查全局变量 `TARGET_BACKEND` 是否属于 exec 集合。它在启动时读一次配置就固定了,运行期间不会变。

### 三个判断点

**1. 启动时检查 — `adapter.py:72`**

```python
if is_target_exec_backend() and self.mode != "single":
    raise NotImplementedError(
        "Exec target backends are currently supported only for SpreadsheetBench mode=single."
    )
```

exec backend 只允许 `mode=single`,否则直接报错退出。

**2. `run_single` 入口 — `codegen_agent.py:423`**

```python
if is_target_exec_backend():
    # exec 路径:准备 workspace → 启动 agent CLI → 读取 solution.py
else:
    # chat 路径:构建 system+user prompt → 一次 LLM API 调用 → 正则提取代码
```

**3. `run_multi` 入口 — `codegen_agent.py:533`**

```python
if is_target_exec_backend():
    # exec 路径:workspace + 多轮 agent 修复(但被 adapter.py 挡住,实际走不到)
else:
    # chat 路径:LLM 生成→执行→反馈错误→LLM 重试,最多 max_turns 轮
```

### 完整流程图

```
启动 → 读配置 TARGET_BACKEND
  │
  ├─ adapter.setup() → is_target_exec_backend()?
  │     └─ exec + mode≠single → 报错退出
  │
  └─ rollout 每个任务 → run_single / run_multi
        │
        ├─ is_target_exec_backend() == True
        │     → _prepare_codex_workspace() 创建工作区
        │     → _run_exec_backend() 启动 Codex/Claude CLI 子进程
        │     → 读取 solution.py
        │
        └─ is_target_exec_backend() == False (当前情况)
              → _build_system() / _build_user() 构建文本 prompt
              → _chat_call() → chat_target_messages() 调 GLM-5.2 API
              → extract_code() 正则提取代码
              → (multi 模式) run_generated_code() 执行 → 反馈错误 → 重试
```

---

## 4. Rollout 与 Holdout 的执行方式

### 所有阶段共用同一个调用链

```
trainer.py
  ├─ 训练 rollout   → adapter.rollout(env, skill, dir, use_eval_feedback=True)
  ├─ selection eval → adapter.rollout(env, skill, dir)               ← use_eval_feedback=False
  ├─ baseline test   → adapter.rollout(env, skill, dir)               ← use_eval_feedback=False
  └─ final test      → adapter.rollout(env, skill, dir)               ← use_eval_feedback=False
         │
         ▼
  adapter.rollout() → run_spreadsheet_batch_codegen()
         │
         ▼
  process_one_codegen() → run_single() / run_multi()
         │
         ├─ is_target_exec_backend() == True  → exec 路径(启动 agent CLI)
         └─ is_target_exec_backend() == False  → chat 路径(调 LLM API)
         │
         ▼
  evaluate()  ← 评分,两种后端完全相同
```

### train 和 holdout 的唯一区别

不是后端类型,而是 `use_eval_feedback` 参数:

| 阶段 | 调用代码 | `use_eval_feedback` | 含义 |
|---|---|---|---|
| **训练 rollout** | `trainer.py:1196-1199` | `True` | multi 模式下,每轮执行后把 cell 级反馈 (不暴露答案值) 喂回 LLM 做下一轮 |
| **selection eval** | `trainer.py:1073` | `False` (默认) | 无反馈,直接评分 |
| **holdout/test** | `trainer.py:2226` | `False` (默认) | 无反馈,直接评分 |

`use_eval_feedback` 在 `rollout.py:709` 决定 multi 模式下是否传 `gold_path` 给 `run_multi`:

```python
gold_path=first_gold if use_eval_feedback else "",
```

- `use_eval_feedback=True` (训练): `gold_path` 有值 → 每轮执行后运行 `evaluate()` + `_auto_verify_output()` 生成 cell 级反馈 → LLM 可以多轮修正
- `use_eval_feedback=False` (holdout/test): `gold_path=""` → 不做中间评估,LLM 生成后直接最终评分

### `is_target_exec_backend()` 在 engine 层零调用

在整个 `skillopt/engine/` 目录中**零调用**。它只在 `codegen_agent.py:424` 和 `533` 这两个位置判断,决定代码生成方式。两条路径生成的代码最终都进入同一个 `evaluate()` 评分,评分逻辑与后端类型无关。

---

## 5. 使用 GLM-5.2 复现 SpreadsheetBench 实验

### 目标

复现论文 Table 2 中 SkillOpt 在 SpreadsheetBench (IID) 上的数据:

| 模型 | Spreadsheet IID |
|---|---|
| Qwen3.5-4B | 15.3 ± 2.5 |
| Qwen3.5-27B | 51.3 ± 4.7 |
| Qwen3.6-27B | 53.3 ± 7.6 |

使用已配置的 GLM-5.2 作为 optimizer 和 target 模型。

### 当前后端配置

配置文件 `configs/_base_/default.yaml`:

```yaml
model:
  backend: openai_compatible
  optimizer_backend: openai_compatible
  target_backend: openai_compatible
  optimizer: GLM-5.2
  target: GLM-5.2
```

端点配置 (硬编码在 `skillopt/model/openai_compatible_backend.py` 的 `_initial_config()` 中,可通过 `.env` 覆盖):

```
OPENAI_COMPATIBLE_BASE_URL=http://113.46.219.251:8080/v1
OPENAI_COMPATIBLE_API_KEY=sk-6Vi_7BS_IuofzkYt8t2B9w
OPENAI_COMPATIBLE_MODEL=GLM-5.2
```

当前使用 chat backend + `mode=multi`,这是论文的 paper-style 设置,是复现实验的正确路径。

### SpreadsheetBench 配置

配置文件 `configs/spreadsheetbench/default.yaml`:

```yaml
mode: multi
max_turns: 10
exec_timeout: 300
workers: 4
max_completion_tokens: 16384
```

### 复现过程修复的 3 个 Bug

1. **`skillopt/config.py`**: `_resolve_layer_format_duplicates` 和 `_drop_base_keys_overridden_by_layer` 中 `"env.name" → "env"` 的映射导致整个 `env` section 被误删。修复为只在值不是 dict 时才 pop。

2. **`skillopt/engine/trainer.py:833`**: skill_init 文件读取未指定 `encoding="utf-8"`,在 Windows 上默认使用 GBK 导致解码失败。

3. **`skillopt/envs/spreadsheetbench/codegen_agent.py:31-37`**: 直接硬编码导入 `azure_openai.get_target_client()`,绕过了后端分发器。修改为使用 `skillopt.model.chat_target_messages`,自动路由到配置的 `openai_compatible` 后端。

### 冒烟测试结果

```
Baseline: 5 items, hard=0.0000 (初始 skill)
STEP 1/20 Rollout: 2 PASS + 2 FAIL (hard=0.5000)
STEP 1/20 Reflection: 分析 2 失败组 + 2 成功组 → 正在生成 skill 补丁
```

### 完整训练 Baseline 结果

```
Baseline (40 val items): hard=0.2250 (22.5%)
```

### 运行完整训练命令

```powershell
$env:PYTHONPATH = "$PWD\.pylibs"; $env:PYTHONUTF8 = "1"
python -u scripts/train.py --config configs/spreadsheetbench/default.yaml
```

### 参数调优经验

- **`workers=24`**: 导致 GLM-5.2 API 过载,大量 TIMEOUT (24 个并发请求太多)
- **`exec_timeout=60`**: 太短,GLM-5.2 单次 API 调用需要 30-100+ 秒,60 秒超时导致所有任务来不及完成一轮
- **`workers=4` + `exec_timeout=300`**: 较为合理的配置,API 不会过载,每任务有 5 分钟完成时间
