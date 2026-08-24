# Meta Skill（元技能）—— Optimizer 端的跨 epoch 记忆

## 与 Slow Update 的关系

两者都是 **epoch 级更新**，但作用于不同层面：

| 维度 | Slow Update（慢更新） | Meta Skill（元技能） |
|---|---|---|
| **改什么** | 目标技能文档（target skill `.md`）—— 给技能尾部追加 `[SLOW_UPDATE_START]...[END]` 反思指导块 | Optimizer 端的记忆文档 —— 不改目标技能，改的是 "optimizer 怎么提 edits" 的元指导 |
| **输入** | prev_skill vs curr_skill 在 N 道题上的对比轨迹 | 同样复用 `format_comparison_text`（与 slow_update 共享比较文本 + token budget 机制） |
| **作用对象** | **target 模型**（如 gpt-5.2）下次 rollout 时用的技能 | **optimizer 模型**（如 h:gpt-5.5）下次 REFLECT/AGGREGATE 调用时注入到 system prompt 的 `meta_skill_context` 字段 |
| **设计意图** | "跨 epoch 的纵向对比 → 提炼反思指导 → 直接改进技能内容" | "跨 epoch 的优化模式总结 → 告诉 optimizer 以后提 edits 时要注意什么" |
| **触发时机** | epoch ≥ 2 边界（epoch 1 注入空占位符） | epoch ≥ 2 边界（epoch 1 跳过） |
| **日志标识** | `[SLOW UPDATE epoch 1] injected empty placeholder` | `[META SKILL epoch 1] skipped — first epoch` |

简单说：**slow update 教 agent 怎么做，meta skill 教 optimizer 怎么教 agent**。

## 代码位置

- 实现：[skillopt/optimizer/meta_skill.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/optimizer/meta_skill.py)
- 调用：[skillopt/engine/trainer.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/engine/trainer.py)
  - `_load_meta_skill_content(out_root, epoch - 1)`：加载上一 epoch 的元技能内容
  - `format_meta_skill_context(meta_skill_content)`：渲染成 optimizer 可读的 context block
  - 注入点：`chat_optimizer(..., meta_skill_context=active_meta_skill)`

## 工作流程

```
每个 epoch 边界（epoch ≥ 2）：

1. 加载上一 epoch 的 meta_skill 内容
   active_meta_skill = _load_meta_skill_content(out_root, epoch - 1)

2. 如果有内容，渲染成 context block：
   "## Optimizer Meta Skill
    This is optimizer-side memory distilled from prior epoch transitions in
    this environment. Use it to improve how you propose, merge, and rank skill
    edits. Prefer it when the current evidence is ambiguous, but do not force
    it if the current trajectories clearly contradict it.
    {content}"

3. 在当前 epoch 的每个 step 的 REFLECT/AGGREGATE 调用时，
   把 context block 注入 optimizer 的 system prompt

4. epoch 边界：用 prev_skill vs curr_skill 的对比轨迹（复用
   format_comparison_text + token budget 机制）调一次 optimizer，
   产出新的 meta_skill 内容，保存到 meta_skill/epoch_XX/meta_skill_result.json

5. 下一个 epoch 重复 1-4
```

## 配置

```yaml
# _base_/default.yaml
optimizer:
  use_meta_skill: true   # 开关
  use_slow_update: true  # slow update 开关（两者独立）
```

两者独立控制：可以只开 slow_update、只开 meta_skill、都开、都关。

## 与 Slow Update 共享的 token budget 机制

meta_skill 复用 `format_comparison_text`，因此 slow_update 的 token budget 机制
（`slow_update_max_prompt_tokens`）对 meta_skill 同样生效——按类别重要性剔除超长
轨迹，保证 optimizer prompt 不超限。

## 接受策略

meta_skill 产出的内容**不直接修改目标技能**，只影响 optimizer 的后续调用。
因此它没有 "accept/reject/gate" 流程——产出的内容直接保存为下一 epoch 的
optimizer context，由 optimizer 自己在下次调用时判断是否采纳。

这与 slow_update 的 `slow_update_gate_with_selection`（是否过 selection 门）
和 force-accept 机制不同——meta_skill 不需要门控，因为它的影响是间接的。
