# 方案三/四/五 实施方案：CCE-Reflect · CL-Sampler · ParetoGate

> 目标：三个改进全部以**环境无关（env-agnostic）**方式落地——同一份代码在 SpreadsheetBench / ALFWorld / DocVQA / SearchQA / OfficeQA 等任何环境上可用，仅通过配置开关启用。
>
> 前置结论（来自代码核对）：
> - 通用 reflect 引擎 [skillopt/gradient/reflect.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/gradient/reflect.py) 的 `fmt_trajectory()`（L65-108）已统一支持三种轨迹格式：tool_call 记录、`{action, env_feedback, reasoning}` 步骤记录（ALFWorld）、`{role, content}` 消息列表（SpreadsheetBench）。
> - 所有未覆写 reflect 的环境经 [envs/base.py:234-253](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/envs/base.py#L234-L253) 统一路由到 `run_minibatch_reflect()`。
> - gate 是纯决策函数（[evaluation/gate.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/evaluation/gate.py)），副作用全在 trainer——ParetoGate 只需改纯函数。
> - 训练批生成统一走 dataloader 的 `plan_train_epoch()`（[datasets/base.py:431](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/datasets/base.py#L431)），trainer 在 [trainer.py:1173-1181](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/engine/trainer.py#L1173-L1181) 消费 `BatchSpec` 列表——CL-Sampler 在此处后处理即可覆盖所有环境。

***

## 一、CCE-Reflect（对比因果提取反思，方案三）

### 1.1 设计原则与注入层级

**注入层级选择：`run_minibatch_reflect()` 调度器内部**，而不是 trainer。理由：

- 调度器已拿到本批全部 rollout 结果（含成功与失败）和 `prediction_dir`、`patches_dir`，CCE 需要的一切都在参数里；
- 所有环境自动继承（走通用 reflect 引擎的 = 全部环境，spreadsheetbench/alfworld 的 env 级 reflect.py 只是 prompt 占位）；
- 复用现有的并行执行器、断点续跑（patches_dir 下的 JSON 落盘检查）、`failure_only` 开关逻辑。

配置关闭时行为与基线**逐字节一致**（与 `use_skill_aware_reflection` 相同的开关纪律）。

### 1.2 新文件：`skillopt/gradient/cce_reflect.py`

#### 1.2.1 跨环境配对键（核心：方案原版的第一处改造）

原版假设 `task_id` 可重复出现——训练 rollout 每任务每批只跑一次，同任务配对恒为空。改为**字段回退链**：

```python
_PAIRING_KEY_FIELDS = (
    "task_type",          # 通用字段（types.RolloutResult）
    "instruction_type",   # spreadsheetbench 专用
    "category",           # 预留
    "domain",             # 预留
)

def pairing_key(item: dict) -> str | None:
    """按回退链取第一个非空字段作为类别键；全空 → None（该 item 不参与配对）。"""
    for f in _PAIRING_KEY_FIELDS:
        v = str(item.get(f) or "").strip()
        if v:
            return v
    return None
```

- 同类别内失败×成功做**最多 M:N 对**（贪心，每个成功轨迹最多被引用 `cce_success_reuse`（默认 2）次，提高成功样本利用率）；
- `pairing_key()` 全空的 item 直接跳过（例如某些环境无类别字段）——**静默降级，不报错**；
- 允许配置 `cce_cross_type_pairing: true` 兜底：类别键缺失时把全部失败 vs 全部成功配对，prompt 中注明"跨类别对比，仅提取通用模式"（默认 false）。

#### 1.2.2 轨迹格式化（核心：方案原版的第二处改造）

废弃 `extract_behavioral_diffs()` 的字符级逐位 diff，改为**复用 `fmt_trajectory()` + LLM 语义 diff**：

```python
from skillopt.gradient.reflect import fmt_trajectory   # 已支持 3 种格式

def _load_conversation(prediction_dir: str, item: dict) -> list[dict]:
    # 与 fmt_minibatch_trajectories 完全相同的读取路径：
    # prediction_dir/<safe_tid>/conversation.json（':' → '-'，Windows 安全）
    ...

def build_contrastive_context(pair: Pair, prediction_dir: str) -> str:
    succ_text = fmt_trajectory(_load_conversation(prediction_dir, pair.success))
    fail_text = fmt_trajectory(_load_conversation(prediction_dir, pair.failure))
    ref = str(pair.failure.get("reference_text") or "").strip()
    return (
        f"### Pair — category: {pair.category}\n"
        f"#### SUCCESS (id={pair.success['id']}, n_turns={pair.success.get('n_turns','?')})\n{succ_text}\n"
        f"#### FAILURE (id={pair.failure['id']}, n_turns={pair.failure.get('n_turns','?')})\n{fail_text}\n"
        + (f"#### Hidden reference (do not copy verbatim into the skill)\n{ref}\n" if ref else "")
    )
```

要点：
- `fmt_trajectory` 对步骤格式输出 `[step N think/action/obs]`、对消息格式输出 `[assistant]/[user]/[verification]`——**LLM 在两种格式下都能做语义分叉分析**，代码零分支；
- `reference_text`（spreadsheetbench 的 item enrichment 已有）作为失败原因对照证据传给 LLM，但 prompt 明令禁止把参考值硬编码进 skill；
- 长轨迹截断策略沿用 `fmt_minibatch_trajectories` 现状（不截断，optimizer 看全量）。

#### 1.2.3 批量调用（核心：成本改造，方案原版每对一调用 → 每调用 K 对）

```python
def run_cce_reflect(
    results: list[dict],
    skill_content: str,
    prediction_dir: str,
    patches_dir: str,
    *,
    edit_budget: int,
    pairs_per_call: int = 3,        # K
    max_pairs: int = 6,             # 每步上限（成本护栏）
    update_mode: str = "patch",
    max_completion_tokens: int = 0,
) -> list[dict]:
    failures = [r for r in results if not r.get("hard")]
    successes = [r for r in results if r.get("hard")]
    if not failures or not successes:
        return []                    # 全失败/全成功 → 静默跳过，零成本
    pairs = _pair_by_category(failures, successes)[:max_pairs]
    if not pairs:
        return []
    calls = [_chunk(pairs, pairs_per_call)]           # 分组
    # 每组一次 optimizer 调用，产出 ≤ edit_budget 条 edits 的 patch
    # patch 结构: {"source_type": "failure", "patch": {"reasoning": ..., "edits": [...]}}
    # reasoning 中强制包含 "causal chain: skill instruction → divergent behavior → failure"
```

- patch 结构与现有 failure patch 完全同构，`_normalise_patches()` 无需改动即可吃进；
- 输出落盘 `patches_dir/cce_{i:03d}.json`，与 minibatch patch 一样支持断点续跑；
- 并行复用调度器现有 ThreadPoolExecutor 模式。

#### 1.2.4 新 prompt：`skillopt/prompts/cce_reflect.md`（通用，无 env 前缀）

要点：给出 skill + 若干对比对 → 要求 (a) 识别成功/失败的行为分叉点（步骤格式找分叉 step，消息格式找分叉 turn，代码产物找代码段差异）；(b) 每条 edit 必须给出显式因果链；(c) 禁止输出仅相关性支持的 edit；(d) 禁止泄漏 reference_text 具体值。

### 1.3 修改点清单

| 文件 | 修改 |
|---|---|
| `skillopt/gradient/cce_reflect.py` | **新增**（全部核心逻辑） |
| `skillopt/gradient/reflect.py` | `run_minibatch_reflect()`（L476）末尾：开关开启时调用 `run_cce_reflect`，返回值 append 进 `raw_patches`；开关读取复用 `is_skill_aware_enabled()` 同款的进程级配置模式 |
| `skillopt/prompts/cce_reflect.md` | **新增** |
| `configs/_base_/default.yaml` | `optimizer.use_cce_reflection: false`（默认关=基线一致）+ 子参数 |
| `docs/reference/config.md` | 配置表补 4 行 |

trainer **零改动**（配置经 `is_*_enabled()` 进程级开关传递，同 skill_aware 模式）。

### 1.4 配置

```yaml
optimizer:
  use_cce_reflection: false      # 总开关，false = 逐字节基线
  cce_pairs_per_call: 3          # 每次 optimizer 调用装的对比对数
  cce_max_pairs: 6               # 每步配对上限（成本护栏，0=不限）
  cce_success_reuse: 2           # 单条成功轨迹最多被配对次数
  cce_cross_type_pairing: false  # 无类别键时的跨类别兜底
```

### 1.5 与现有机制的交互

| 机制 | 交互 | 说明 |
|---|---|---|
| `failure_only: true` | 兼容 | CCE 只用成功**轨迹**不产成功 patch，不受该开关影响（调度器里 successes 列表在该开关下仍可构建） |
| `use_skill_aware_reflection` | 协同 | CCE patch 走 failure 流，自动经过 defect/lapse 分类增强；两者叠加即 run 3 的组合实验 |
| train_gate | 兼容 | CCE 只影响 patch 质量，gate 语义不变；若 gate 拒绝率因此下降，即是 CCE 生效的直接证据 |
| prox_shrink | 兼容 | 单谱系假设未动 |
| 断点续跑 | 已处理 | cce_*.json 落盘检查与 minibatch patch 同款 |

### 1.6 成本与预期

- API：每步 ≤ `ceil(6/3)=2` 次 optimizer 调用（对比现有 analyst ~6 次），**+33% optimizer 调用、0 额外 rollout**；wall time 增幅 < 5%（optimizer 并行、rollout 才是瓶颈）
- 预期：patch 因果质量提升 → gate 拒绝率下降 → 有效步数增加；这是三方案中唯一直接作用于已观察短板（gate 连拒、补丁退化）的
- 风险：40 题批次中成功数少（如 10）→ 配对上限天然受限，机制自动降级为低强度，不会空转烧钱

***

## 二、CL-Sampler（课程学习任务采样，方案四）

### 2.1 注入层级：trainer 后处理（而非改每个 dataloader）

原版把课程逻辑写进 `trainer.py` 的采样处，但项目里 `plan_train_epoch` 有多份实现（split 版 [datasets/base.py:431](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/datasets/base.py#L431)、ALFWorld 版、livemath 版）。逐个改会破坏环境无关性。**改为在 trainer 消费点做后处理**：

```python
# trainer.py L1173-1181 之后插入：
epoch_batches = dataloader.plan_train_epoch(...)
if use_curriculum:
    epoch_batches = curriculum.reorder_epoch(epoch_batches, epoch, num_epochs)  # 整批重排序 + 可选过滤
```

单点接入，任何 dataloader 生成的 `BatchSpec` 列表都能处理。

### 2.2 新文件：`skillopt/optimizer/curriculum.py`

#### 2.2.1 状态与持久化

```python
@dataclass
class TaskRecord:
    task_id: str
    difficulty: float      # 初始启发式 → 历史成功率修正
    n_attempts: int = 0
    n_successes: int = 0
    last_epoch: int = 0

class Curriculum:
    def __init__(self, out_root: str, *, easy_fade_rate=0.95, mode="e2h"):
        self.state_path = os.path.join(out_root, "curriculum_state.json")  # 断点续跑
        ...
```

- `update(results, epoch)`：每步 rollout 后由 trainer 调用，输入 `all_rollout_results`（含 `id`、`hard`），更新成功率；
- 难度 = `0.5 × 启发式 + 0.5 × (1 - shrunk_success_rate)`（shrunk: 向 0.5 收缩的小样本修正 `sr' = (s×n + 0.5×m)/(n+m)`, m=3），避免 1 次尝试定终身；
- 启发式难度：`min(len(str(instruction))/4000, 0.4) + min(n_turns/30, 0.3) + (0.3 if fail_reason else 0)`，字段缺失时取中性 0.5——**任何环境的 item dict 都能算出值**。

#### 2.2.2 重排序语义（与数据流约束对齐）

当前配置 train=80 / batch=40 / 2 步每 epoch：**每 epoch 全量覆盖，课程只能决定"易批先、难批后"的批间顺序**。要让课程产生"选哪些题"的压力，需 `steps_per_epoch × batch_size < train_size`（如 train 扩到 120 或 batch 降到 20）。文档明确两档：

```python
def reorder_epoch(self, batches: list[BatchSpec], epoch, num_epochs) -> list[BatchSpec]:
    # 阶段权重 (warmup/ramp/plateau/anneal) 按 epoch/num_epochs 切分
    if 全量覆盖 (sum(batch_size) >= n_train):
        return _sort_batches_easy_to_hard(batches)      # 仅排序：batch 整体按批内平均难度升序
    else:
        return _sample_with_pressure(batches, weights)  # 采样：未掌握(easy 且 sr<0.85)保留，已掌握按 easy_fade_rate 衰减
```

排序模式不丢任务、不改 batch 内容，只换执行顺序——**最保守、任何数据集安全**；采样模式在覆盖有余量时启用退火。

### 2.3 修改点清单

| 文件 | 修改 |
|---|---|
| `skillopt/optimizer/curriculum.py` | **新增** |
| `skillopt/engine/trainer.py` | ① L1178 后：`reorder_epoch` 调用；② 每步 rollout 完（L1305 附近 `all_rollout_results` 汇总后）：`curriculum.update(...)` + 状态落盘；③ 启动时从 out_root 恢复状态（resume 兼容） |
| `configs/_base_/default.yaml` | `train.curriculum: false` + 子参数 |
| `docs/reference/config.md` | 补配置行 |

### 2.4 配置

```yaml
train:
  curriculum: false            # 总开关
  curriculum_mode: e2h         # e2h（排序+退火）；phase 权重内置
  curriculum_easy_fade: 0.95   # 已掌握任务的保留概率
  curriculum_sampling: auto    # auto=仅当覆盖有余量时启用采样压力
```

### 2.5 与现有机制的交互

- **seed 决定性**：重排整批 `BatchSpec`（seed 随批走），不破坏现有 `shuffled_seeds` 日志与 resume 语义；
- slow_update 纵向对比：批次难度随 epoch 变化会让"同题跨 epoch 对比"变稀疏——`longitudinal_pair_policy: mixed` 已容忍，但需在实验解读时注意；
- 与 train_gate / prox_shrink：无接触。

### 2.6 成本与预期

- **API 增量为零**（纯本地重排序）；全量覆盖模式下连 rollout 题集都不变，只是顺序
- 预期：排序模式收益中等（先易后难让早期 patch 建立在有效梯度上）；采样模式收益更高但需扩 train_size（rollout 量不变、见过的题更少）
- 已知局限（诚实声明）：8 步训练里课程只有 4 个 epoch 边界可调，E2H 退火曲线基本走不完整；该方案的完整收益需要 `epochs ≥ 8` 或更大 train_size

***

## 三、ParetoGate（多目标帕累托门控，方案五 lite 版）

### 3.1 设计：保主指标、加次级否决/交易，GateResult 结构不动

原版提出完整帕累托前沿种群——那与方案一（PBE）重叠且动 best 谱系（破坏 prox_shrink/slow_update 的单谱系假设）。**lite 版只改 `evaluate_gate()` 纯函数**，目标向量：

| 目标 | 来源 | 说明 |
|---|---|---|
| primary | 现有 `select_gate_score()`（hard/soft/mixed + semantic_density，[gate.py:73](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/evaluation/gate.py#L73)） | 主指标，best 谱系仍按它排 |
| soft | `cand_soft` | 次级质量信号 |
| brevity | `1 - min(len(skill), 8000)/8000` | 越短越好，对齐 prox_shrink 的压缩精神 |

决策规则（在现有规则上叠加，不替换）：

```
1. cand_score > current_score                          → accept / accept_new_best（现有规则，不变）
2. |cand_score - current_score| ≤ primary_tol 且       → accept（新增：等价交易条款，
   candidate 在 soft、brevity 至少一项严格优于 current      等主分换次级收益）
   且不被 current 双指标同时压制（带容忍度）
3. 其余                                                 → reject（现有）
```

- `primary_tol` 复用 σ 自适应容忍度模式（`auto_train_gate_tolerances()` 同款：k·σ_diff，随批次规模/难度自适应，见 [trainer.py:1407-1422](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/engine/trainer.py#L1407-L1422) 的调用样例）；
- best/new_best 判定**只看 primary**——GateResult 四字段语义完全不变，下游（slow_update、prox_shrink、最终 test 选 best_skill）零感知；
- 40 题 selection 噪声 ±5% 的风险由容忍度吸收：次级收益必须**严格超过**噪声门才算交易达成。

### 3.2 修改点清单

| 文件 | 修改 |
|---|---|
| `skillopt/evaluation/gate.py` | `evaluate_gate()` 增加可选参数（`pareto_config: dict | None = None`，None=现有行为逐字节不变）；新增 `_pareto_trade_ok()` 私有函数 + `compute_brevity()` |
| `skillopt/engine/trainer.py` | L1907 gate 调用处透传 `pareto_config`（从 cfg 解析）；L1150 baseline 处的 `select_gate_score` 不动 |
| `configs/_base_/default.yaml` | `evaluation.pareto_gate: false` + 子参数 |
| `docs/reference/config.md` | 补配置行 |

### 3.3 配置

```yaml
evaluation:
  pareto_gate: false           # 总开关
  pareto_trade_tolerance: -1   # primary 交易容忍度；负数=σ自适应(scale 见下)，正数=固定，0=严格
  pareto_tolerance_scale: 1.5  # k：tol = k·σ_diff（与 train_gate 同语义）
  pareto_objectives: [soft, brevity]   # 参与交易的次级目标
  pareto_brevity_cap: 8000     # brevity 归一化上限字符数
```

### 3.4 与现有机制的交互

| 机制 | 交互 |
|---|---|
| `use_gate: false`（force-accept 路径，L1937+） | ParetoGate 自动失效（无 gate 决策可介入），无需特判 |
| train_gate | 相互独立：train_gate 管训练批回放保底，ParetoGate 管 selection 接受语义 |
| prox_shrink | 正协同：brevity 目标与 prox 的压缩目标同向；gate 阶段奖励短 skill，prox 阶段验证压缩不降分 |
| semantic_density | 已有 `use_semantic_density` 加分项与 Pareto 不冲突（一个改 primary 标量，一个管次级交易） |

### 3.5 成本与预期

- **API 与 rollout 增量为零**（纯本地比较）
- 预期：等主分候选不再被一刀切拒绝，soft/长度收益被保留；在 gate 拒绝率高、主分停滞的 run 里（正是 run 1 前身实验的形态：0.75→0.50 拒绝循环）提供额外接受通道
- 风险：交易条款可能接受"主分平、次级微优"的平庸候选 → 由 `pareto_tolerance_scale` 控制，k=1.5 时噪声误收率与 train_gate 同档

***

## 四、实施顺序与实验矩阵

### 4.1 实施顺序（每步独立可验证、可单独回退）

1. **CCE-Reflect**（改动集中在 reflect 引擎内，trainer 零改动，风险最低、预期最高）
2. **ParetoGate**（纯函数扩展，几十行，零成本）
3. **CL-Sampler**（唯一动 trainer 的，且依赖"是否扩 train_size"的决策）

### 4.2 实验矩阵（延续 run 1 / run 2 的单变量纪律）

| run | 配置 | 目的 |
|---|---|---|
| run 1（进行中） | gate=off, skill_aware=off | 基线 A |
| run 2（待跑） | gate=off, skill_aware=**on** | skill_aware 增量 |
| run 3 | run 1 + **CCE=on** | CCE 增量（对照 gate 拒绝率下降幅度） |
| run 4 | run 3 + **ParetoGate=on** | 交易条款增量（对照 accept 率） |
| run 5 | run 4 + **CL=on**（排序模式，不扩 train_size） | 课程排序增量 |
| run 6（可选） | train_size=120 + CL 采样模式 | 课程退火完整形态 |

### 4.3 每个方案的验证指标

- CCE：patch 数量/命中率（被 aggregate 保留比例）、gate 拒绝率、selection 曲线
- ParetoGate：交易型 accept 次数、被交易接受的 skill 最终 test 分
- CL：各 epoch 批难度序列、早期 epoch 的 rollout hard 分（应高于均匀基线）

### 4.4 统一回退保证

三个开关默认 false，关闭路径与现状**逐字节一致**（逐字面检查：CCE 不进调度器分支、gate 参数为 None 走原比较、curriculum 不触发 reorder）。任何一步实验异常，关开关重跑即回基线，无需代码回滚。
