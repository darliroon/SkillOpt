# CL-Sampler 在 SkillOpt 项目中的落地可行性分析

## 1. 背景

本文整理自对 `implementation_plan_cce_cl_pareto.md` 中 CL-Sampler 方案的讨论，目标是判断课程学习采样器能否落到当前 SkillOpt 项目，以及实施时需要修正哪些设计假设。

CL-Sampler 的原始设想是在 dataloader 生成一个 epoch 的 `BatchSpec` 后，由 trainer 统一进行课程学习后处理：

```python
epoch_batches = dataloader.plan_train_epoch(...)
if use_curriculum:
    epoch_batches = curriculum.reorder_epoch(
        epoch_batches,
        epoch,
        num_epochs,
    )
```

课程难度主要由任务启发式信息和历史成功率共同决定，并支持易到难排序、已掌握任务衰减和断点恢复。

---

## 2. 总体结论

CL-Sampler 技术上可以落到当前项目，但需要区分三种实现层级：

| 实现形态 | 可行性 | 风险 | 实际作用 |
| --- | --- | --- | --- |
| 整批重排序 | 高 | 低 | 不丢任务，只调整容易批次和困难批次的执行顺序 |
| 任务级重新组批 | 中 | 中 | 精确控制每道题的顺序，但必须适配不同 dataloader 的特殊语义 |
| 概率采样与任务淘汰 | 中 | 较高 | 减少已掌握任务、强化困难任务，但会改变训练分布和恢复语义 |

推荐首先实现低风险的 **V1 整批重排序**。这一版本与当前架构最契合，改动集中，不会破坏 ALFWorld 等环境已有的 batch metadata。

需要注意：对于当前 ALFWorld 的约 39 条训练任务、较少 epoch 且每个 epoch 基本全量覆盖的设置，CL-Sampler 的收益预计有限。它主要改变“先训练哪个 batch”，而不是“训练哪些任务”。

---

## 3. 为什么当前架构支持 CL-Sampler

### 3.1 Trainer 存在合适的单点注入位置

当前 trainer 会在每个 epoch 开始时统一调用 `dataloader.plan_train_epoch()`，得到完整的 `epoch_batches`，随后按照 `batch_idx` 顺序消费。

因此，在 `plan_train_epoch()` 后重排 `BatchSpec` 列表，可以真实改变任务执行顺序，而不需要修改 rollout、reflect、aggregate、selection 和 update 等后续流程。

### 3.2 BatchSpec 已具备必要的信息承载能力

当前 `BatchSpec` 包含：

- `phase`
- `split`
- `seed`
- `batch_size`
- `payload`
- `metadata`

对于 split-backed 数据集，`payload` 通常是具体任务列表，可以读取任务 ID 和题目内容；`metadata` 则可以保留环境所需的附加信息。

因此，CL-Sampler 不需要引入新的 batch 协议。

### 3.3 Rollout 结果可以更新历史难度

Trainer 已将一个 step 内所有 accumulation batch 的 rollout 结果汇总到 `all_rollout_results`。CL-Sampler 可以在 step 成功完成后，根据结果中的任务 ID 和 hard score 更新：

- 尝试次数；
- 成功次数；
- 收缩后的历史成功率；
- 综合任务难度；
- 最近出现的 epoch。

---

## 4. 推荐的 V1：整批重排序

V1 不拆分、不删除也不重新构造 `BatchSpec`，只按照批内任务平均难度调整原 batch 的顺序。

其优点包括：

1. `BatchSpec.seed` 始终跟随原 batch；
2. `payload` 保持不变；
3. `metadata` 保持不变；
4. 不降低任务覆盖率；
5. 不增加 rollout 或 API 调用；
6. 对 payload-backed 和 seed-only dataloader 都可以安全降级；
7. 对 ALFWorld、LiveMathematicianBench 等具有特殊 batch 语义的环境风险较低。

严格来说，这一版本更适合称为 **Curriculum Batch Reorder**，而不是完整的 task sampler。

---

## 5. 原方案需要修正的问题

### 5.1 不能假设所有环境都有统一的任务字段

原方案设想使用以下信息计算启发式难度：

- instruction 长度；
- 对话轮数；
- fail reason；
- 历史成功率。

但这些字段可能分别存在于 payload item、rollout result 或环境专用结构中，而且不同环境字段名不统一。seed-only 环境甚至可能没有具体任务 payload。

建议采用以下策略：

1. 初始难度默认设为中性值 `0.5`；
2. 环境启发式只作为可选信号；
3. 历史成功率作为主要的跨环境通用信号；
4. 找不到稳定任务 ID 时，退化为 batch-level 统计；
5. seed-only batch 只允许整批重排序，不进行任务级采样。

### 5.2 配置方案遗漏了 config.py 映射

当前项目会将结构化 YAML 配置映射为 trainer 使用的 flat config，因此除了修改 `configs/_base_/default.yaml`，还必须在 `skillopt/config.py` 中加入类似映射：

```python
"train.curriculum": "curriculum",
"train.curriculum_mode": "curriculum_mode",
"train.curriculum_easy_fade": "curriculum_easy_fade",
"train.curriculum_sampling": "curriculum_sampling",
```

否则 YAML 中新增的 curriculum 参数不一定能传递到 trainer。

### 5.3 全量覆盖判断必须使用真实训练集大小

不能仅使用：

```python
sum(batch.batch_size for batch in batches) >= n_train
```

判断一个 epoch 是否全量覆盖。小数据集出现 trailing empty microbatch 时，现有 dataloader 可能重新使用打乱后的任务前缀，导致 batch size 总和大于唯一任务数。

推荐由 trainer 使用统一接口获取训练池大小：

```python
train_size = dataloader.get_train_size()
```

然后显式传给 curriculum。

### 5.4 BatchSpec 级采样不等于任务级采样

如果 `_sample_with_pressure()` 的输入仍然是 `list[BatchSpec]`，它只能选择、删除或重复整个 batch，不能精确控制某一道任务是否出现。

真正的任务级采样需要：

1. 展平所有 batch 的 payload；
2. 按 item ID 计算权重；
3. 对 item 进行采样或排序；
4. 重新切分 batch；
5. 重建正确的 seed 和 metadata。

这已经不再是简单的 trainer 后处理，应作为 V2/V3 单独实现。

---

## 6. 不同环境的兼容性

### 6.1 ALFWorld

ALFWorld 的 batch metadata 包含：

- `gamefiles`；
- `result_ids`；
- `eval_dataset`；
- `is_train`。

因此：

- 重排原始 `BatchSpec` 是安全的；
- 拆分 payload 后重新组 batch，必须由 ALFWorld dataloader 重新生成 metadata；
- 不能由通用 curriculum 模块自行猜测或拼接 gamefile 信息。

否则可能出现 payload、gamefile 和 rollout result ID 不一致。

### 6.2 LiveMathematicianBench

LiveMathematicianBench 会根据 batch seed 对选项进行 materialize 和 shuffle。如果 curriculum 将已经 materialize 的任务拆开重组，可能改变：

- seed 与选项顺序的对应关系；
- 同一道题跨 epoch 的选项排列；
- 断点恢复后的确定性。

因此 V1 应保持原 batch 完整不变。任务级 rebatching 只能对明确声明支持该能力的 dataloader 开启。

### 6.3 Seed-only 环境

部分环境只依赖 batch size 和 seed 构造训练环境，`payload` 可能为空。此时无法可靠计算单任务难度，应：

- 以 batch seed 作为批次标识；
- 只记录 batch-level 历史；
- 或直接保持原始顺序；
- 禁止启用任务级采样。

---

## 7. Resume 一致性风险

仅保存 `curriculum_state.json` 不足以保证断点恢复正确。

当前 trainer 恢复时会重新生成当前 epoch 的 batch，并跳过已完成的 global step。假设一个 epoch 最初排序为：

```text
[A, B, C]
```

完成 A 后 curriculum 状态发生变化，程序中断。恢复后如果根据新状态重新排序为：

```text
[B, A, C]
```

Trainer 仍会跳过第一个 step，结果跳过的是 B，而 A 可能再次执行。

### 推荐做法：持久化 epoch plan

在 epoch 开始时保存固定计划，例如：

```json
{
  "epoch": 2,
  "batch_order": [
    {"seed": 2043, "task_ids": ["task_a", "task_b"]},
    {"seed": 2044, "task_ids": ["task_c", "task_d"]}
  ]
}
```

恢复同一 epoch 时直接复用该计划，不重新排序或采样。

### Curriculum 状态的提交边界

Curriculum 状态不应在 rollout 刚完成时单独落盘，而应与以下操作保持在同一个 completed-step 边界：

- history 保存；
- `last_completed_step` 更新；
- runtime state 保存。

否则可能出现 curriculum 认为某批任务已经完成，但 trainer 仍认为该 step 未完成的状态错位。

较简单的 V1 也可以采用“epoch 内只积累统计，epoch 结束统一更新”的策略，使本 epoch 的排序不会被中途结果改变。

---

## 8. 对当前 ALFWorld 的收益判断

ALFWorld 技术上适合课程学习，因为：

- payload 包含明确任务；
- 每道任务有稳定 ID；
- 任务关联具体 gamefile；
- rollout result 可与任务 ID 对齐；
- 能持续记录任务成功率。

但当前训练集约 39 条，且每 epoch 基本全量覆盖，因此整批排序不会增加困难任务的训练次数，只会改变任务先后顺序。

在少量 epoch 下还有以下限制：

- 第一个 epoch 主要依赖启发式难度；
- 历史成功率只能影响后续 epoch；
- 课程退火曲线难以充分展开；
- 只有少数 epoch 边界可以调整课程顺序。

SkillOpt 每个 step 都可能更新 Skill，因此“先易后难”仍可能产生正向作用：先通过容易任务形成基础 patch，再处理困难任务，可能比随机顺序更稳定。但不应预期仅靠 CL-Sampler 就让 ALFWorld valid_unseen 指标大幅提高。

影响最终效果更大的因素可能仍包括：

- reflect patch 的因果质量；
- selection gate 的连续拒绝问题；
- Skill 是否过度特化；
- selection split 与 valid_unseen 的分布差异；
- 训练任务是否覆盖足够多的 ALFWorld task type。

---

## 9. 推荐实施路线

### V1：整批课程排序

- 默认关闭；
- 不修改 batch 内容；
- 不丢弃或重复 batch；
- 初始按可用启发式计算批次平均难度；
- 后续结合收缩后的历史成功率；
- 保存固定 epoch batch plan；
- payload 缺失时降级为 batch-level 或原始顺序；
- 先在 ALFWorld、SearchQA 上进行 A/B 对照。

### V2：仅对明确支持的 dataloader 进行任务级排序

建议增加 dataloader 能力接口，例如：

```python
def supports_task_rebatching(self) -> bool:
    ...

def rebuild_train_batches(self, items, *, epoch, batch_size, seed):
    ...
```

由各 dataloader 自己负责重建环境专用 metadata，通用 curriculum 模块只决定任务顺序。

### V3：真正的采样压力

在 V1/V2 得到稳定实验信号后，再加入：

- 已掌握任务衰减；
- 困难任务增权；
- 非全量覆盖；
- 有放回或无放回采样；
- 最低任务覆盖率保护；
- 防止困难任务过采样的权重上限。

该阶段会真实改变训练分布，需要重点验证是否造成困难题过拟合、基础任务过早消失，以及 slow update 的跨 epoch 配对密度下降。

---

## 10. 最终建议

CL-Sampler 可以在当前 SkillOpt 中实施，但建议遵循以下边界：

1. 第一版只重排原始 `BatchSpec`；
2. 补充 `skillopt/config.py` 的配置映射；
3. 使用 `dataloader.get_train_size()` 判断覆盖模式；
4. 区分 payload-backed 与 seed-only batch；
5. 持久化每个 epoch 的 batch plan；
6. Curriculum 状态只在 completed-step 边界提交；
7. 不在通用模块中直接拆分和重组 ALFWorld/LiveMath payload；
8. 先比较关闭课程、随机顺序和易到难排序三组实验；
9. V1 验证有效后，再开发任务级 rebatching 和概率采样。

按以上方案落地，V1 的代码侵入性较低、API 增量为零，也不会破坏现有训练链路。完整 task-level CL-Sampler 则应作为后续独立阶段实现。
