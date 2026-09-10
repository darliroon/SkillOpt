# SkillOpt 训练与评估命令速查

> 本文档供重启对话后快速恢复上下文使用。包含 Chat Backend / Exec Backend 的训练、评估命令，以及常用参数。

---

## 一、环境准备

```bash
# 进入项目目录
cd /home/huawei/桌面/SkillOpt

# 激活虚拟环境
export PATH="$HOME/.local/bin:$(pwd)/.venv/bin:$PATH"

# ALFWorld 专用环境变量
export ALFWORLD_DATA="$HOME/.cache/alfworld"
```

---

## 二、Chat Backend 训练

Chat Backend 通过 API 调用 LLM（不启动本地 CLI agent）。
支持的 chat backend: `openai_chat`, `claude_chat`, `qwen_chat`, `minimax_chat`, `openai_compatible`, `copilot_chat`

### 2.1 ALFWorld（openai_compatible，当前默认配置）

```bash
# 最简启动（使用 configs/alfworld/default.yaml 中的默认配置）
.venv/bin/python scripts/train.py --config configs/alfworld/default.yaml

# 指定 optimizer/target 模型
.venv/bin/python scripts/train.py \
    --config configs/alfworld/default.yaml \
    --optimizer_model gpt-5.6-sol \
    --target_model gpt-5.5

# 用 --cfg-options 覆盖配置
.venv/bin/python scripts/train.py \
    --config configs/alfworld/default.yaml \
    --cfg-options \
        model.optimizer=gpt-5.6-sol \
        model.target=gpt-5.5 \
        env.workers=36 \
        env.max_api_workers=36

# 后台运行（日志重定向）
.venv/bin/python scripts/train.py --config configs/alfworld/default.yaml 2>&1 | tee logs/alfworld_run.log

# 使用 .sh 脚本
bash scripts/run_alfworld.sh
```

### 2.2 SearchQA（openai_compatible）

```bash
.venv/bin/python scripts/train.py --config configs/searchqa/default.yaml

# 覆盖学习率等
.venv/bin/python scripts/train.py \
    --config configs/searchqa/default.yaml \
    --cfg-options optimizer.learning_rate=16 optimizer.lr_scheduler=linear
```

### 2.3 其他数据集（同理）

```bash
# SpreadsheetBench
.venv/bin/python scripts/train.py --config configs/spreadsheetbench/default.yaml

# OfficeQA
.venv/bin/python scripts/train.py --config configs/officeqa/default.yaml

# DocVQA
.venv/bin/python scripts/train.py --config configs/docvqa/default.yaml

# LiveMathematicianBench
.venv/bin/python scripts/train.py --config configs/livemathematicianbench/default.yaml
```

---

## 三、Exec Backend 训练

Exec Backend 启动本地 CLI agent（Codex / Claude Code / Cursor / Copilot / Jiuwen）执行代码。
Exec backend 只能作为 **target_backend**，optimizer 固定为 `openai_chat`（codex_exec 例外，可同时做 optimizer）。

### 3.1 Jiuwen Exec（SearchQA）

```bash
# 通过 --target_backend 指定 jiuwen_exec
.venv/bin/python scripts/train.py \
    --config configs/searchqa/default.yaml \
    --target_backend jiuwen_exec \
    --target_model gpt-5.2 \
    --optimizer_model gpt-5.5

# 通过 --cfg-options 指定
.venv/bin/python scripts/train.py \
    --config configs/searchqa/default.yaml \
    --cfg-options \
        model.target_backend=jiuwen_exec \
        model.target=gpt-5.2 \
        model.optimizer=gpt-5.5
```

### 3.2 Codex Exec

```bash
.venv/bin/python scripts/train.py \
    --config configs/searchqa/default.yaml \
    --target_backend codex_exec \
    --target_model gpt-4o \
    --codex_exec_path codex \
    --codex_exec_sandbox workspace-write \
    --codex_exec_approval_policy never
```

### 3.3 Claude Code Exec

```bash
.venv/bin/python scripts/train.py \
    --config configs/searchqa/default.yaml \
    --target_backend claude_code_exec \
    --target_model claude-sonnet-4-6 \
    --claude_code_exec_path claude \
    --claude_code_exec_effort medium \
    --claude_code_exec_max_thinking_tokens 16384
```

### 3.4 Cursor Exec

```bash
.venv/bin/python scripts/train.py \
    --config configs/searchqa/default.yaml \
    --target_backend cursor_exec \
    --target_model composer-2.5 \
    --cursor_exec_path cursor-agent
```

### 3.5 Copilot Exec

```bash
.venv/bin/python scripts/train.py \
    --config configs/searchqa/default.yaml \
    --target_backend copilot_exec \
    --copilot_exec_path copilot
```

---

## 四、纯评估命令（不训练）

使用 `scripts/eval_only.py`，只跑 rollout 评估指定 skill，不执行训练流程。

### 4.1 Chat Backend 评估

```bash
# 评估指定 skill 在 valid_unseen 上的表现
.venv/bin/python scripts/eval_only.py \
    --config configs/alfworld/default.yaml \
    --skill outputs/skillopt_alfworld_gpt-5.6-sol_20260826_120240/skills/best_skill.md \
    --split valid_unseen

# 评估初始 skill（baseline）
.venv/bin/python scripts/eval_only.py \
    --config configs/alfworld/default.yaml \
    --skill skillopt/envs/alfworld/skills/initial.md \
    --split all

# 评估所有 split
.venv/bin/python scripts/eval_only.py \
    --config configs/searchqa/default.yaml \
    --skill outputs/searchqa_run/best_skill.md \
    --split all
```

### 4.2 Exec Backend 评估

```bash
# Jiuwen Exec 评估
.venv/bin/python scripts/eval_only.py \
    --config configs/searchqa/default.yaml \
    --skill skills/my_skill.md \
    --cfg-options model.target_backend=jiuwen_exec model.target=gpt-5.2

# Codex Exec 评估
.venv/bin/python scripts/eval_only.py \
    --config configs/searchqa/default.yaml \
    --skill skills/my_skill.md \
    --cfg-options model.target_backend=codex_exec model.target=gpt-4o

# Claude Code Exec 评估
.venv/bin/python scripts/eval_only.py \
    --config configs/searchqa/default.yaml \
    --skill skills/my_skill.md \
    --cfg-options model.target_backend=claude_code_exec model.target=claude-sonnet-4-6
```

### 4.3 Prox Shrink 独立运行

```bash
.venv/bin/python scripts/run_prox_standalone.py \
    --config configs/searchqa/default.yaml \
    --skill outputs/searchqa_run/best_skill.md \
    --out_root outputs/searchqa_prox_standalone
```

---

## 五、常用参数速查

### 5.1 核心参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--config` | (必需) | YAML 配置文件路径 |
| `--optimizer_model` | 配置文件值 | optimizer 模型名 |
| `--target_model` | 配置文件值 | target 模型名 |
| `--optimizer_backend` | 配置文件值 | optimizer 后端 |
| `--target_backend` | 配置文件值 | target 后端 |
| `--reasoning_effort` | 配置文件值 | 推理强度: low/medium/high/xhigh/max |
| `--out_root` | 自动生成 | 输出目录 |

### 5.2 训练参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--num_epochs` | 4 | 训练轮数 |
| `--batch_size` | 40 | 批大小 |
| `--edit_budget` | 4 | 每步最大编辑数（学习率） |
| `--seed` | 42 | 随机种子 |
| `--lr_scheduler` | cosine | 学习率调度: constant/linear/cosine/autonomous |
| `--skill_update_mode` | patch | 更新模式: patch/rewrite/full_rewrite 等 |

### 5.3 评估参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--eval_test` | true | 训练后在 valid_unseen 上做最终测试 |
| `--use_gate` | true | 使用门控机制 |
| `--sel_env_num` | 0 | 选择集大小（0=全部） |
| `--test_env_num` | 0 | 测试集大小（0=全部） |

### 5.4 ALFWorld 专用参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--max_steps` | 50 | 每个 episode 最多步数 |
| `--workers` | 36 | 并行 ALFWorld 环境数 |
| `--max_api_workers` | 36 | 并发 LLM API 调用数 |
| `--split_dir` | data/alfworld_path_split | 数据分割目录 |

### 5.5 Jiuwen Exec 专用参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--jiuwen_exec_max_iterations` | 8 | ReAct agent 最大迭代次数 |
| `--jiuwen_exec_api_key` | (空=复用 openai_compatible key) | API key |
| `--jiuwen_exec_api_base` | (空=复用 openai_compatible base_url) | API base URL |

---

## 六、配置文件一览

| 配置路径 | 数据集 | env.name |
|----------|--------|----------|
| `configs/_base_/default.yaml` | 基础配置（被所有环境继承） | - |
| `configs/alfworld/default.yaml` | ALFWorld | alfworld |
| `configs/searchqa/default.yaml` | SearchQA | searchqa |
| `configs/spreadsheetbench/default.yaml` | SpreadsheetBench | spreadsheetbench |
| `configs/officeqa/default.yaml` | OfficeQA | officeqa |
| `configs/docvqa/default.yaml` | DocVQA | docvqa |
| `configs/livemathematicianbench/default.yaml` | LiveMathematicianBench | livemathmaticianbench |

---

## 七、Backend 分类速查

### Chat Backends（API 调用，optimizer 和 target 都可用）

| Backend | 默认模型 | 配置函数 |
|---------|---------|---------|
| `openai_compatible` | gpt-4o-mini | `configure_openai_compatible()` |
| `openai_chat` | gpt-4o | `configure_azure_openai()` |
| `claude_chat` | claude-sonnet-4-6 | 通过 `set_reasoning_effort()` |
| `qwen_chat` | Qwen/Qwen3.5-4B | `configure_qwen_chat()` |
| `minimax_chat` | MiniMax-M2.7 | `configure_minimax_chat()` |
| `copilot_chat` | (Azure 默认) | `configure_copilot_chat()` |

### Exec Backends（CLI agent 执行，只能做 target，codex_exec 例外）

| Backend | 默认模型 | optimizer |
|---------|---------|-----------|
| `jiuwen_exec` | gpt-4o-mini | openai_chat |
| `codex_exec` | gpt-4o | codex_exec |
| `claude_code_exec` | claude-sonnet-4-6 | openai_chat |
| `cursor_exec` | composer-2.5 | openai_chat |
| `copilot_exec` | (Azure 默认) | openai_chat |

---

## 八、输出目录结构

训练输出目录名格式: `outputs/skillopt_{env_name}_{target_model}_{timestamp}/`

```
outputs/skillopt_alfworld_gpt-5.6-sol_20260826_120240/
├── config.json                 # 完整配置快照
├── history.json                # 每个 epoch 的训练历史
├── runtime_state.json          # 运行时状态（last_completed_step 等）
├── skills/
│   ├── skill_v0000.md          # 初始 skill
│   ├── skill_v0001.md          # epoch 1 后的 skill
│   ├── best_skill.md           # 最佳 skill（selection 最高）
│   └── prox_skill.md           # prox shrink 后的压缩 skill
├── steps/
│   └── step_0001/
│       ├── step_record.json    # 该 step 的完整记录
│       ├── rollout/
│       │   ├── results.jsonl    # 每个 episode 的结果
│       │   └── predictions/     # 每个 episode 的对话记录
│       └── patches/             # analyst 生成的 patches
├── test_eval/                  # 最终测试评估
│   ├── predictions/            # 测试 episode 对话记录
│   └── summary.json            # 测试结果汇总
└── logs/
    └── *.log                   # 训练日志
```

---

## 九、监控训练进度

```bash
# 查看训练日志关键行
grep -n "EPOCH\|STEP.*done\|REFLECT\|analyst\|SLOW\|META\|accept\|reject\|baseline result\|test eval" logs/skillopt_*.log | grep -vi skill_update_mode

# 查看 history.json
python3 -c "
import json
d=json.load(open('outputs/skillopt_alfworld_*/history.json'))
for s in d: print(f\"step{s['step']}: rollout={s['rollout_hard']:.4f} cur={s['current_score']:.4f} best={s['best_score']:.4f} action={s['action']} patches={s['n_patches']}\")
"

# 查看 test_eval 部分结果
python3 -c "
import json, os
pred_dir = 'outputs/skillopt_alfworld_*/test_eval/predictions'
dirs = sorted(os.listdir(pred_dir))
success = sum(1 for d in dirs if json.load(open(os.path.join(pred_dir, d, 'conversation.json')))[-1].get('reward',0) > 0)
print(f'{success}/{len(dirs)} = {success/len(dirs):.4f}')
"

# 检查进程状态
ps aux | grep "train.py" | grep -v grep
```

---

## 十、关键修复记录

### reflect.py 冒号 ID 路径修复（2026-08-26）

**问题**: ALFWorld 的 item id 含冒号（如 `train:0036`），rollout 写盘用原始 id 做目录名，reflect 读取时无条件 `replace(":", "-")` 导致找不到目录，analyst LLM 从未被调用（每个 epoch 0 patches）。

**修复文件**: `skillopt/gradient/reflect.py` 第 138-152 行

**修复逻辑**: 先用原始 id 查找目录，不存在才 fallback 到冒号替换后的 id。对不含冒号的 id（如 searchqa 的 hex hash）无影响。

**验证**: 修复后 Epoch 1 成功生成 5 个 patches（1 failure + 4 success），analyst 真正分析了失败轨迹。Epoch 3 首次 `accept_new_best`，selection 从 0.8333 提升到 0.9444。

---

## 十一、API Key 配置

在 `configs/_base_/default.yaml` 中配置:

```yaml
model:
  backend: openai_compatible
  openai_compatible_base_url: "https://yibuapi.com/v1/"
  openai_compatible_api_key: "key1,key2,key3"  # 逗号分隔，自动轮询
  optimizer_openai_compatible_api_key: ""     # 空=复用上面的 key
  target_openai_compatible_api_key: ""       # 空=复用上面的 key
```

- `openai_compatible` backend 用 `itertools.cycle` 轮询多个 key，每次请求切换
- `jiuwen_exec` backend 只取第一个 key（`api_keys[0]`），不轮询
- key 失效（401）后重试 5 次仍失败则 RuntimeError，**不会自动切换到其他 key**
