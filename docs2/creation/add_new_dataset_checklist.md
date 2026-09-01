# 新增自定义数据集完整清单

> 基于 `_template` 模板和 `docs/guide/new-benchmark.md` 文档整理。

## 总览

添加一个新数据集需要搭建 **4 个部分**：

| # | 部分 | 路径 | 必须 |
|---|---|---|---|
| 1 | 数据集 | `data/<name>_split/` | ✅ |
| 2 | Config 文件 | `configs/<name>/default.yaml` | ✅ |
| 3 | envs 文件夹 | `skillopt/envs/<name>/` | ✅ |
| 4 | 注册代码 | `scripts/train.py` + `scripts/eval_only.py` | ✅ |

---

## 1. 数据集

```
data/<your_bench>_split/
├── train/
│   └── items.json
├── val/
│   └── items.json
├── test/
│   └── items.json
└── split_manifest.json
```

每个 `items.json` 是一个 list of dict，每个 item 至少包含 `id` 字段，其余字段按数据集特色自定义（如 `question`、`ground_truth`、`reference_text`、`task_type` 等）。

---

## 2. Config 文件

路径：`configs/<your_bench>/default.yaml`

```yaml
_base_: ../_base_/default.yaml      # 注意：是字符串，不是列表

model:
  reasoning_effort: medium

train:
  batch_size: 16
  accumulation: 1
  num_epochs: 4

gradient:
  minibatch_size: 8
  merge_batch_size: 8

optimizer:
  learning_rate: 4

env:
  name: your_bench                  # 必须与注册 key 一致
  skill_init: skillopt/envs/your_bench/skills/initial.md
  split_mode: split_dir             # 或 ratio
  split_dir: data/your_bench_split
  workers: 4
  max_completion_tokens: 4096
  limit: 0                          # 调试时设小值，如 10
```

`_base_` 继承 `configs/_base_/default.yaml` 的全部默认配置，可覆盖。

---

## 3. envs 文件夹

路径：`skillopt/envs/<your_bench>/`

```
skillopt/envs/your_bench/
├── __init__.py              # ✅ Python 包标识（空文件即可）
├── adapter.py               # ✅ 必须：EnvAdapter 子类
├── dataloader.py            # ✅ 必须：SplitDataLoader 子类
├── rollout.py               # ✅ 必须：跑模型 + 打分 + 持久化 conversation
├── evaluator.py             # 🔵 可选：评分逻辑也可写在 rollout.py 里
├── reflect.py               # 🔵 可选：基类已有默认 reflect() 实现
│
├── prompts/                  # ✅ 必须：prompt 目录
│   ├── analyst_error.md      #    失败反思 prompt
│   ├── analyst_success.md    #    成功反思 prompt
│   └── rollout_system.md     #    rollout 系统提示词
│
└── skills/                   # ✅ 必须：初始 skill
    └── initial.md            #    训练前的初始 skill 文件
```

### 3.1 `__init__.py`

空文件即可，确保目录被识别为 Python 包。

### 3.2 `adapter.py` — EnvAdapter 子类

继承 `skillopt.envs.base.EnvAdapter`，必须实现 4 个抽象方法：

```python
class YourBenchAdapter(EnvAdapter):
    def build_train_env(self, batch_size, seed, **kw): ...
    def build_eval_env(self, env_num, split, seed, **kw): ...
    def rollout(self, env_manager, skill_content, out_dir, **kw): ...
    def get_task_types(self) -> list[str]: ...
```

- `reflect()` 基类已提供默认实现，调用共享的 `run_minibatch_reflect`
- `setup()` / `get_dataloader()` 通常简单代理给 dataloader
- 评分逻辑写在 `rollout.py` 中，不是 adapter 的方法

### 3.3 `dataloader.py` — SplitDataLoader 子类

继承 `skillopt.datasets.base.SplitDataLoader`，必须实现：

```python
class YourBenchLoader(SplitDataLoader):
    def load_split_items(self, split_path: str) -> list[dict]: ...
```

- `load_split_items` 从磁盘加载 train/val/test 的 item 列表
- 如需支持 `split_mode="ratio"`（自动切分单个原始文件），还需 override `load_raw_items(data_path)`

### 3.4 `rollout.py` — 执行与打分

核心函数 `run_batch()` 完成：
1. 用 `skill_content` 作为 system prompt，调用 `skillopt.model.chat_target` 跑模型
2. 打分：返回 `hard`（0/1 或 [0,1] float）和 `soft`（[0,1] float）
3. 持久化：每个非空 trajectory 写到 `<out_dir>/predictions/<id>/conversation.json`
   - 基类 `reflect()` 读取这个路径，没有这个文件则该结果不参与反思

```python
def run_batch(*, items, skill_content, out_root, workers=4, max_completion_tokens=4096) -> list[dict]:
    # 返回 [{"id": ..., "hard": 0/1, "soft": 0.0-1.0, ...}, ...]
```

> **关键**：使用 `skillopt.model.chat_target` 而非直接调 OpenAI/Claude，这样能路由到用户配置的任意 chat backend。

### 3.5 `evaluator.py` — 可选

- `EnvAdapter` 基类**没有** `evaluate()` 抽象方法
- 评分逻辑可以直接写在 `rollout.py` 里
- 只有当评分逻辑复杂且需要复用时，才单独拆出 `evaluator.py`（如 spreadsheetbench）

### 3.6 `reflect.py` — 可选

- 基类 `EnvAdapter.reflect()` **已内置默认实现**，调用 `run_minibatch_reflect`
- 默认实现读取 `predictions/<id>/conversation.json` + `analyst_error.md` / `analyst_success.md` prompt
- 只有需要自定义反思逻辑时才 override

### 3.7 `prompts/` 目录

| 文件 | 用途 | 必须 |
|---|---|---|
| `analyst_error.md` | 失败案例反思 prompt，告诉 analyst 如何分析失败 trajectory | ✅ |
| `analyst_success.md` | 成功案例反思 prompt，告诉 analyst 如何提炼成功经验 | ✅ |
| `rollout_system.md` | rollout 时的系统提示词（如 ReAct 格式、代码生成格式等） | 视 rollout 实现而定 |

prompt 加载优先级（`load_prompt(name, env)`）：
1. `skillopt/envs/<env>/prompts/<name>.md`（数据集专属）
2. `skillopt/prompts/<name>.md`（通用 fallback）

### 3.8 `skills/initial.md`

训练开始前使用的初始 skill 文件。可以是空文件（从零开始），也可以写入基础方法论作为起点。

---

## 4. 注册代码

在两个脚本的 `_register_builtins()` 函数中添加懒注册：

### `scripts/train.py`

```python
try:
    from skillopt.envs.your_bench.adapter import YourBenchAdapter
    _ENV_REGISTRY["your_bench"] = YourBenchAdapter
except ImportError:
    pass
```

### `scripts/eval_only.py`

同样的代码块，确保单独评估时也能找到环境。

> **没有 `BENCHMARK_REGISTRY` 字典**：每个 CLI 脚本维护自己的 `_ENV_REGISTRY`，懒加载，避免可选依赖影响 `--help`。

---

## 快速开始

```bash
# 1. 复制模板
cp -r skillopt/envs/_template skillopt/envs/your_bench

# 2. 重命名文件
cd skillopt/envs/your_bench
mv env_template.py    adapter.py
mv loader_template.py dataloader.py

# 3. 重命名类名，修复交叉引用
# 4. 实现 adapter.py 中的 rollout 和 dataloader.py 中的 _normalize_item
# 5. 添加 prompts/ 和 skills/initial.md
# 6. 在 scripts/train.py 和 scripts/eval_only.py 注册
# 7. 创建 configs/your_bench/default.yaml
# 8. 准备 data/your_bench_split/

# 运行
python scripts/train.py --config configs/your_bench/default.yaml
```

---

## 常见问题

| 报错 | 原因 |
|---|---|
| `ValueError: Unknown environment 'your_bench'` | 忘了在 scripts 里注册 |
| `TypeError: Can't instantiate abstract class` | 没实现全部 4 个抽象方法 |
| 训练时 `skip_no_patches` | rollout 没有持久化 `predictions/<id>/conversation.json`，或 id 不一致 |
| 评分噪声大导致优化器不收敛 | `rollout.py` 的评分函数质量不够，先打磨评分再打磨 prompt |

## 调试技巧

- `train.batch_size: 4` + `limit: 10` 先跑通
- 评分逻辑是影响优化器效果的关键，优先打磨 `_score()` 函数
- 如果数据集有重依赖（selenium、vllm 等），注册时用 `try/except ImportError` 包裹
