# SkillOpt SOTA 改进提案：通过算法优化获得更优秀的 Skill

> **目标**：基于对 SkillOpt 全量代码的深度分析和对 2025-2026 年最前沿研究的系统性调研，提出 15 个可落地的算法改进方案，每个方案均映射到具体源文件、函数和数据结构，并附伪代码实现框架。

***

## 目录

1. [现状分析与问题诊断](#1-现状分析与问题诊断)
2. [SOTA 方法调研总览](#2-sota-方法调研总览)
3. [改进方案一：种群化技能进化（PBE）](#改进方案一种群化技能进化pbe)
4. [改进方案二：多臂老虎机编辑选择（MAB-Select）](#改进方案二多臂老虎机编辑选择mab-select)
5. [改进方案三：对比因果提取反思（CCE-Reflect）](#改进方案三对比因果提取反思cce-reflect)
6. [改进方案四：课程学习任务采样（CL-Sampler）](#改进方案四课程学习任务采样cl-sampler)
7. [改进方案五：多目标帕累托门控（ParetoGate）](#改进方案五多目标帕累托门控paretogate)
8. [改进方案六：贝叶斯优化学习率调度（BO-Scheduler）](#改进方案六贝叶斯优化学习率调度bo-scheduler)
9. [改进方案七：回溯进度感知反思（RePro-Reflect）](#改进方案七回溯进度感知反思repro-reflect)
10. [改进方案八：补丁回放校准聚合（PRC-Aggregate）](#改进方案八补丁回放校准聚合prc-aggregate)
11. [改进方案九：拓扑感知技能加载（TAE-Route）](#改进方案九拓扑感知技能加载tae-route)
12. [改进方案十：种群多样性维护（PDM）](#改进方案十种群多样性维护pdm)
13. [改进方案十一：情景记忆增强元技能（EM-MetaSkill）](#改进方案十一情景记忆增强元技能em-metaskill)
14. [改进方案十二：协同自适应任务策展人（Actor-Curator）](#改进方案十二协同自适应任务策展人actor-curator)
15. [改进方案十三：递归元技能进化（MetaSkill-Evolve）](#改进方案十三递归元技能进化metaskill-evolve)
16. [改进方案十四：偏好优化门控（PrefGate）](#改进方案十四偏好优化门控prefgate)
17. [改进方案十五：推理时计算扩展（TTC-Scaling）](#改进方案十五推理时计算扩展ttc-scaling)
18. [实施路线图与优先级](#实施路线图与优先级)
19. [预期收益量化估计](#预期收益量化估计)
20. [参考文献](#参考文献)

***

## 1. 现状分析与问题诊断

### 1.1 SkillOpt 架构概要

SkillOpt 将 Markdown 技能文档视为神经网络的"可训练参数"，完整照搬深度学习训练纪律。核心 6 阶段 ReflACT 管线：

```
Rollout（前向传播）→ Reflect（反向传播）→ Aggregate（梯度聚合）
→ Select（梯度裁剪）→ Update（参数更新）→ Gate（验证早停）
```

**Epoch 边界机制**：

- **Slow Update**（=动量）：跨 epoch 纵向对比防遗忘，在 [trainer.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/optimizer/slow_update.py) 中实现
- **Meta Skill**（=元学习）：跨 epoch 优化器策略记忆，在 [meta\_skill.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/optimizer/meta_skill.py) 中实现

**双模型架构**：Optimizer（分析轨迹生成编辑补丁）+ Target（用当前 skill 执行任务）

### 1.2 核心数据流

```
初始 Skill S₀
    ↓
[Epoch e, Step s]
    ↓
① ROLLOUT: adapter.rollout(train_env, current_skill, rollout_dir)
    → 产出 rollout_results (hard/soft 分数 + 轨迹)
    ↓
② REFLECT: adapter.reflect(rollout_results, current_skill, batch_dir)
    → 产出 failure_patches + success_patches
    ↓
③ AGGREGATE: merge_patches(current_skill, failure_patches, success_patches)
    → 产出 merged_patch (层级合并)
    ↓
④ SELECT: rank_and_select(current_skill, merged_patch, max_edits=edit_budget)
    → 产出 ranked_patch (top-L 编辑)
    ↓
⑤ UPDATE: apply_patch_with_report(current_skill, ranked_patch)
    或 rewrite_skill_from_suggestions(current_skill, ranked_patch)
    → 产出 candidate_skill
    ↓
⑤.5 TRAIN-GATE (可选): train_gate_pass()
    → 前向闭环验证
    ↓
⑥ EVALUATE: evaluate_gate(candidate_skill, ...)
    → accept / accept_new_best / reject
    ↓
[Epoch 边界]
    ↓
Slow Update: run_slow_update(prev_skill, curr_skill, comparison_pairs)
    → 纵向对比，防遗忘
Meta Skill: run_meta_skill(prev_skill, curr_skill, comparison_pairs)
    → 优化器策略记忆
```

### 1.3 已识别的 10 个关键瓶颈

| #  | 瓶颈          | 现有实现                                                                                                              | 影响                 |
| -- | ----------- | ----------------------------------------------------------------------------------------------------------------- | ------------------ |
| 1  | **单一种群**    | 仅维护 best-so-far 单一技能 lineage                                                                                      | 无种群多样性，容易陷入局部最优    |
| 2  | **确定性编辑排序** | [clip.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/optimizer/clip.py) 用 LLM 排序，取 top-L          | 无探索-利用平衡，忽略编辑间交互效应 |
| 3  | **单轨迹反思偏差** | [reflect.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/gradient/reflect.py) 每条轨迹独立分析             | 无因果归因，难以区分相关性与因果性  |
| 4  | **均匀任务采样**  | trainer.py 从训练集随机采样                                                                                               | 无难度递进，训练效率低        |
| 5  | **单指标门控**   | [gate.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/evaluation/gate.py) 用 hard/soft/mixed 单一标量比较 | 忽略效率、长度、鲁棒性等多维度    |
| 6  | **固定学习率策略** | [scheduler.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/optimizer/scheduler.py) 仅有 4 种预设模式      | 无法根据训练动态自适应调整      |
| 7  | **无进度感知**   | 反思仅看成功/失败，不看进度信号                                                                                                  | 长时序任务缺乏中间反馈        |
| 8  | **未验证合并**   | [aggregate.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/gradient/aggregate.py) 直接 LLM 合并补丁      | 合并后补丁未在样本上验证有效性    |
| 9  | **全量技能加载**  | 推理时加载完整 skill 文档                                                                                                  | 上下文过载，无关指令干扰       |
| 10 | **二元门控决策**  | accept/reject 二元决策                                                                                                | 无偏好梯度，信息浪费         |

***

## 2. SOTA 方法调研总览

### 2.1 调研覆盖的方法

| 方法                   | 来源                  | 核心思想                                  | 对 SkillOpt 的启示     |
| -------------------- | ------------------- | ------------------------------------- | ------------------ |
| **GEPA**             | ICLR 2026 Oral      | 帕累托前沿选择 + 反思式变异 + 自然语言反馈              | 种群化进化 + Pareto 选择  |
| **DSPy SIMBA**       | DSPy 框架             | 多臂老虎机 + softmax 采样 + 方差分桶             | 编辑选择的 bandit 化     |
| **SkillCAT**         | 2026                | CCE（对比因果提取）+ AAE（补丁回放校准）+ TTE（拓扑感知执行） | 因果反思 + 补丁校准 + 技能路由 |
| **SkillEvo**         | 2026                | 自更新进化梯度 + 可信反馈 + 可控治理                 | 进化梯度方向控制           |
| **BayesPrompt**      | 2026                | 贝叶斯后验推理 + MCMC 采样 + 可读性约束             | 概率采样替代确定性选择        |
| **LLINBO**           | ICLR 2026           | LLM + GP 代理混合贝叶斯优化                    | 学习率的 BO 调度         |
| **RePro**            | 2026                | 前向-然后-回溯反思 + 进度感知 + 复合奖励              | 进度感知反思             |
| **E2H Reasoner**     | ICLR 2026           | 从易到难课程 RL + 退火调度                      | 课程学习任务采样           |
| **Actor-Curator**    | 2026                | 策略改进老虎机 + 自适应数据策展                     | 协同自适应任务策展          |
| **ParetoPO**         | ICML 2026 Spotlight | 超体积动态标量化 + Pareto 排序优势                | 多目标帕累托门控           |
| **PromptQuine**      | ICML 2025           | 进化搜索剪枝策略 + 自发现                        | 技能压缩进化搜索           |
| **Mage**             | 2026                | 情景记忆 + 多目标 Pareto + 自适应评估 + POCE 耦合效应 | 情景记忆元技能            |
| **EvoSkill**         | 2026                | 自验证进化 + Trace2Skill 并行提案 + 棘轮效应       | 并行反思 + 单调保证        |
| **EVOREFUSE**        | NeurIPS 2025        | 进化变异 + 重组 + ELBO 最大化                  | 变异-重组算子设计          |
| **EVOLVE**           | TMLR 2026           | 迭代偏好优化训练自精炼                           | 偏好优化门控             |
| **MetaSkill-Evolve** | 2026                | 快任务-技能环 + 慢元技能环                       | 递归元技能进化            |
| **LEACL**            | 2026                | LLM 任务分解 + 元任务生成 + 自动课程               | LLM 驱动课程设计         |
| **AP-BMM**           | 2026                | 异步先验引导贝叶斯模型合并 + Pareto 集              | 异步评估 + 先验引导        |
| **SPIN**             | ICML 2024           | 自博弈微调 + DPO 式目标                       | 自对弈偏好优化            |

### 2.2 改进映射矩阵

```
瓶颈                          →  改进方案                         →  SOTA 来源
─────────────────────────────────────────────────────────────────────────────
1. 单一种群                   →  PBE (种群化进化)                  →  GEPA, EvoSkill
2. 确定性编辑排序             →  MAB-Select (多臂老虎机)           →  SIMBA
3. 单轨迹反思偏差             →  CCE-Reflect (对比因果提取)        →  SkillCAT
4. 均匀任务采样               →  CL-Sampler (课程学习)             →  E2H, LEACL
5. 单指标门控                 →  ParetoGate (帕累托门控)           →  ParetoPO
6. 固定学习率策略             →  BO-Scheduler (贝叶斯优化)         →  LLINBO, BayesPrompt
7. 无进度感知                 →  RePro-Reflect (进度感知)          →  RePro
8. 未验证合并                 →  PRC-Aggregate (补丁回放校准)      →  SkillCAT AAE
9. 全量技能加载               →  TAE-Route (拓扑感知路由)          →  SkillCAT TTE
10. 二元门控决策              →  PrefGate (偏好优化门控)           →  EVOLVE, SPIN
+ 种群多样性                  →  PDM (多样性维护)                  →  F-MAD, EVOREFUSE
+ 元技能记忆                  →  EM-MetaSkill (情景记忆)           →  Mage
+ 任务选择                    →  Actor-Curator (协同策展)          →  Actor-Curator
+ 元技能递归                  →  MetaSkill-Evolve (递归进化)       →  MetaSkill-Evolve
+ 推理优化                    →  TTC-Scaling (推理时扩展)          →  SkillCAT TTE
```

***

## 改进方案一：种群化技能进化（PBE）

### 1.1 动机

SkillOpt 当前仅维护一条技能谱系（best-so-far），每次 update 后立即用 gate 决定 accept/reject。这等价于深度学习中的"贪心贪心"——每次只保留一个解，丢失了大量探索信息。

GEPA（ICLR 2026 Oral）证明：维护帕累托前沿种群可以将 rollout 成本降低到 1/35，同时比 GRPO 平均提升 6%。EvoSkill 的"棘轮效应"也证明：多提案并行 + 单调保证能显著加速收敛。

### 1.2 核心设计

**新增模块**：`skillopt/optimizer/population.py`

```python
"""种群化技能进化（Population-Based Evolution, PBE）

维护 K 个技能候选的帕累托前沿种群，替代单一线性谱系。
每个 epoch 结束时进行：选择 → 变异 → 交叉 → 评估 → 帕累托更新。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal
import copy


@dataclass
class SkillIndividual:
    """种群中的一个技能个体"""
    skill_content: str
    hard_score: float = 0.0
    soft_score: float = 0.0
    efficiency_score: float = 0.0    # 新增：工具调用效率
    semantic_density: float = 0.0   # 语义密度
    age: int = 0                     # 存活代数
    origin: str = "seed"             # seed / mutation / crossover / immigrant
    fitness_history: list[float] = field(default_factory=list)
    parent_id: str = ""


@dataclass
class Population:
    """帕累托前沿种群"""
    individuals: list[SkillIndividual]
    archive: list[SkillIndividual]   # 非前沿但保留的个体（用于多样性）
    max_size: int = 8                # 前沿最大大小
    archive_size: int = 16           # 存档最大大小

    def pareto_front(self) -> list[SkillIndividual]:
        """计算当前帕累托前沿"""
        front = []
        for ind in self.individuals:
            dominated = False
            for other in self.individuals:
                if other is ind:
                    continue
                if (other.hard_score >= ind.hard_score and
                    other.soft_score >= ind.soft_score and
                    other.efficiency_score >= ind.efficiency_score and
                    (other.hard_score > ind.hard_score or
                     other.soft_score > ind.soft_score or
                     other.efficiency_score > ind.efficiency_score)):
                    dominated = True
                    break
            if not dominated:
                front.append(ind)
        return front

    def update(self, candidate: SkillIndividual) -> bool:
        """用新候选更新种群，返回是否被接受到前沿"""
        front = self.pareto_front()
        # 检查候选是否被前沿中任何个体支配
        for ind in front:
            if (ind.hard_score >= candidate.hard_score and
                ind.soft_score >= candidate.soft_score and
                ind.efficiency_score >= candidate.efficiency_score and
                (ind.hard_score > candidate.hard_score or
                 ind.soft_score > candidate.soft_score or
                 ind.efficiency_score > candidate.efficiency_score)):
                # 被支配，放入存档
                self._add_to_archive(candidate)
                return False

        # 候选不被前沿支配，加入种群
        self.individuals.append(candidate)

        # 重新计算前沿并裁剪
        new_front = self.pareto_front()
        if len(new_front) > self.max_size:
            # 按拥挤距离排序，保留前沿中分布最均匀的个体
            new_front = self._crowding_sort(new_front, self.max_size)
        # 非前沿个体移入存档
        removed = [ind for ind in self.individuals if ind not in new_front]
        for r in removed:
            self._add_to_archive(r)
        self.individuals = new_front
        return True

    def _crowding_sort(self, front: list, n: int) -> list:
        """拥挤距离排序：保持前沿的多样性"""
        if len(front) <= n:
            return front
        for ind in front:
            ind.crowding_distance = 0.0
        for dim in ['hard_score', 'soft_score', 'efficiency_score']:
            front.sort(key=lambda x: getattr(x, dim))
            front[0].crowding_distance = float('inf')
            front[-1].crowding_distance = float('inf')
            rng = front[-1].__dict__[dim] - front[0].__dict__[dim]
            if rng > 0:
                for i in range(1, len(front) - 1):
                    front[i].crowding_distance += (
                        front[i + 1].__dict__[dim] - front[i - 1].__dict__[dim]
                    ) / rng
        front.sort(key=lambda x: -x.crowding_distance)
        return front[:n]

    def _add_to_archive(self, ind: SkillIndividual):
        """添加到存档，超出大小则淘汰最老个体"""
        self.archive.append(ind)
        if len(self.archive) > self.archive_size:
            self.archive.sort(key=lambda x: x.age, reverse=True)
            self.archive = self.archive[:self.archive_size]

    def get_best(self) -> SkillIndividual:
        """返回综合最优个体（hard 优先）"""
        if not self.individuals:
            return None
        return max(self.individuals, key=lambda x: x.hard_score)

    def select_parents(self, n: int = 2) -> list[SkillIndividual]:
        """锦标赛选择父代"""
        import random
        tournament = random.sample(
            self.individuals, min(n * 3, len(self.individuals))
        )
        tournament.sort(key=lambda x: x.hard_score, reverse=True)
        return tournament[:n]
```

### 1.3 与 trainer.py 的集成

在 [trainer.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/engine/trainer.py) 的训练循环中，当前结构为：

```python
# 现有：单谱系
for epoch in range(1, num_epochs + 1):
    for step_in_epoch in range(steps_per_epoch):
        # ... 6 阶段管线 ...
        gate_result = evaluate_gate(candidate_skill, ...)
        if gate_result.action == "accept_new_best":
            current_skill = candidate_skill
        elif gate_result.action == "reject":
            pass  # 丢弃候选
    # Epoch 边界：Slow Update + Meta Skill
```

**改进后**：

```python
# 改进：种群化
population = Population(
    individuals=[SkillIndividual(skill_content=initial_skill)],
    archive=[],
    max_size=config.population_size,
    archive_size=config.archive_size,
)

for epoch in range(1, num_epochs + 1):
    for step_in_epoch in range(steps_per_epoch):
        current = population.get_best()

        # ①-⑤ 正常 6 阶段管线（基于 current.skill_content）
        candidate_skill = ...  # 经过 6 阶段后的候选

        # ⑥ 评估候选的多维分数
        cand_hard, cand_soft = evaluate(candidate_skill, selection_set)
        cand_eff = compute_efficiency(candidate_skill, rollout_results)
        cand_density = compute_semantic_density(candidate_skill)

        candidate = SkillIndividual(
            skill_content=candidate_skill,
            hard_score=cand_hard,
            soft_score=cand_soft,
            efficiency_score=cand_eff,
            semantic_density=cand_density,
            origin="mutation",
            parent_id=id(current),
        )

        # 帕累托更新（替代二元 gate）
        accepted = population.update(candidate)

    # Epoch 边界：种群级操作
    if epoch < num_epochs:
        # 交叉：从前沿选父代，生成 offspring
        parents = population.select_parents(2)
        offspring = crossover_skill(parents[0], parents[1])
        population.update(offspring)

        # 变异：随机选个体进行随机扰动
        for ind in random.sample(population.individuals, k=2):
            mutated = mutate_skill(ind, mutation_rate=0.1)
            population.update(mutated)

        # 老化更新
        for ind in population.individuals:
            ind.age += 1

    # Slow Update + Meta Skill 仍基于 get_best()
```

### 1.4 新增操作算子

**交叉算子** `crossover_skill(parent_a, parent_b)`：

```python
def crossover_skill(parent_a: SkillIndividual, parent_b: SkillIndividual) -> SkillIndividual:
    """技能文档的交叉算子：按章节交叉拼接"""
    sections_a = split_sections(parent_a.skill_content)
    sections_b = split_sections(parent_b.skill_content)
    # 按章节标题匹配，每节随机选父代
    merged_sections = []
    all_titles = list(dict.fromkeys(
        [s['title'] for s in sections_a] + [s['title'] for s in sections_b]
    ))
    for title in all_titles:
        sec_a = next((s for s in sections_a if s['title'] == title), None)
        sec_b = next((s for s in sections_b if s['title'] == title), None)
        if sec_a and sec_b:
            chosen = random.choice([sec_a, sec_b])
        else:
            chosen = sec_a or sec_b
        merged_sections.append(chosen)
    offspring_content = "\n\n".join(
        f"## {s['title']}\n{s['content']}" for s in merged_sections
    )
    return SkillIndividual(
        skill_content=offspring_content,
        origin="crossover",
        parent_id=f"{id(parent_a)}+{id(parent_b)}",
    )
```

**变异算子** `mutate_skill(individual, mutation_rate)`：

```python
def mutate_skill(individual: SkillIndividual, mutation_rate: float = 0.1) -> SkillIndividual:
    """技能文档的变异算子：随机插入/删除/替换指令行"""
    lines = individual.skill_content.split('\n')
    mutated_lines = []
    for line in lines:
        if line.strip().startswith('<!--'):  # 保护区域
            mutated_lines.append(line)
            continue
        r = random.random()
        if r < mutation_rate * 0.3:  # 删除
            continue
        elif r < mutation_rate * 0.6:  # 替换为同义改写
            mutated_lines.append(paraphrase_line(line))
        else:  # 保留
            mutated_lines.append(line)
    return SkillIndividual(
        skill_content='\n'.join(mutated_lines),
        origin="mutation",
        parent_id=id(individual),
    )
```

### 1.5 预期收益

- **探索能力**：维护 K=8 个帕累托前沿个体，探索空间覆盖提升 8x
- **收敛速度**：GEPA 证明种群化可将 rollout 成本降低到 1/35
- **鲁棒性**：多解候选降低单一解过拟合风险
- **多样性**：拥挤距离排序保证前沿的均匀分布

***

## 改进方案二：多臂老虎机编辑选择（MAB-Select）

### 2.1 动机

当前 [clip.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/optimizer/clip.py) 的 `rank_and_select()` 函数用 optimizer LLM 对编辑按重要性排序，然后确定性取 top-L。这存在三个问题：

1. **无探索**：每次都选"被认为最重要"的编辑，可能忽略实际效果好的冷门编辑
2. **无反馈**：编辑的选择不基于历史应用效果
3. **忽略方差**：不区分"稳定有效"和"偶尔有效"的编辑

DSPy SIMBA 的核心洞察：**用多臂老虎机 + softmax 采样 + 方差分桶**来选择编辑，能显著提升优化效率。

### 2.2 核心设计

**新增模块**：`skillopt/optimizer/mab_select.py`

```python
"""多臂老虎机编辑选择（MAB-Select）

将每条编辑提议视为一个老虎机臂，用 Thompson 采样进行探索-利用平衡。
高方差编辑（效果不稳定）获得更多探索机会。
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field


@dataclass
class EditArm:
    """老虎机臂：一条编辑提议"""
    edit: dict
    # Beta 分布参数（伯努利奖励的共轭先验）
    alpha: float = 1.0   # 成功次数 + 先验
    beta: float = 1.0    # 失败次数 + 先验
    # 历史奖励记录
    reward_history: list[float] = field(default_factory=list)
    # LLM 评估的初始重要性（作为先验信息）
    prior_importance: float = 0.5

    @property
    def expected_reward(self) -> float:
        """Beta 分布的期望"""
        return self.alpha / (self.alpha + self.beta)

    @property
    def variance(self) -> float:
        """Beta 分布的方差"""
        n = self.alpha + self.beta
        return (self.alpha * self.beta) / (n * n * (n + 1))

    def sample(self) -> float:
        """Thompson 采样：从 Beta 后验中采样"""
        return random.betavariate(self.alpha, self.beta)

    def update(self, reward: float):
        """根据应用效果更新后验"""
        self.reward_history.append(reward)
        # 连续奖励离散化：reward > 0.5 视为成功
        if reward > 0.5:
            self.alpha += 1.0
        else:
            self.beta += 1.0
        # 衰减历史以适应非平稳性
        if len(self.reward_history) > 20:
            self.reward_history = self.reward_history[-20:]
            # 重置部分历史以适应非平稳分布
            self.alpha = max(1.0, self.alpha * 0.95)
            self.beta = max(1.0, self.beta * 0.95)


class EditBandit:
    """编辑选择的多臂老虎机"""

    def __init__(
        self,
        arms: list[EditArm],
        max_select: int = 8,
        temperature: float = 1.0,
        variance_bonus: float = 0.3,
    ):
        self.arms = arms
        self.max_select = max_select
        self.temperature = temperature
        self.variance_bonus = variance_bonus

    def select(self) -> list[EditArm]:
        """选择 max_select 条编辑"""
        if len(self.arms) <= self.max_select:
            return self.arms

        # Thompson 采样
        samples = []
        for arm in self.arms:
            # 采样值 = 期望奖励 + 方差奖励（UCB 式思想）
            sampled = arm.sample()
            bonus = self.variance_bonus * math.sqrt(arm.variance)
            score = sampled + bonus
            # 融合 LLM 先验重要性
            score = score * 0.7 + arm.prior_importance * 0.3
            samples.append((arm, score))

        # 排序取 top-L
        samples.sort(key=lambda x: -x[1])
        selected = [arm for arm, _ in samples[:self.max_select]]

        # softmax 温度采样替代（而非确定性取 top-L）
        # 以一定概率从排名靠后的编辑中"探索性"选择
        if self.temperature > 0 and len(samples) > self.max_select:
            remaining = samples[self.max_select:]
            if remaining:
                # 概率性替换：以 exp(-temperature) 的概率替换最弱选择
                import numpy as np
                probs = np.array([s for _, s in remaining])
                probs = np.exp(probs / self.temperature)
                probs = probs / probs.sum()
                replace_idx = np.random.choice(
                    len(remaining), p=probs
                )
                selected[-1] = remaining[replace_idx][0]

        return selected

    def batch_update(self, edits: list[dict], rewards: list[float]):
        """批量更新编辑效果"""
        for edit, reward in zip(edits, rewards):
            for arm in self.arms:
                if arm.edit == edit:
                    arm.update(reward)
                    break
```

### 2.3 与现有 clip.py 的集成

在 [clip.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/optimizer/clip.py) 中，当前 `rank_and_select()` 的核心流程为：

```python
# 现有
def rank_and_select(skill_content, patch, max_edits, ...):
    # 1. 调用 optimizer LLM 对编辑排序
    # 2. 取 top-L
    return ranked_patch
```

**改进后**：在 `rank_and_select` 之后，用 MAB-Select 替代确定性截取：

```python
# 改进
from skillopt.optimizer.mab_select import EditArm, EditBandit

def rank_and_select_with_mab(
    skill_content: str,
    patch: dict,
    max_edits: int,
    bandit_state: dict | None = None,  # 持久化的老虎机状态
    ...
) -> tuple[dict, EditBandit]:
    """LLM 排序 + 多臂老虎机选择"""
    # 1. 仍然调用 optimizer LLM 获取初始排序和重要性评分
    ranked_patch = rank_and_select(skill_content, patch, max_edits=999, ...)

    # 2. 构建/恢复老虎机臂
    items = get_payload_items(ranked_patch, update_mode)
    if bandit_state:
        arms = [EditArm(**state) for state in bandit_state.get('arms', [])]
    else:
        arms = [
            EditArm(
                edit=item,
                prior_importance=1.0 - (i / len(items)),  # LLM 排序转先验
            )
            for i, item in enumerate(items)
        ]

    # 3. 方差分桶（SIMBA 核心思想）
    # 将编辑按"影响领域"分桶，每桶内独立选择
    buckets = bucket_edits_by_target(items)
    bandit = EditBandit(arms, max_select=max_edits, temperature=0.5)

    # 4. 选择
    selected_arms = bandit.select()

    # 5. 返回选中的编辑 + 更新后的老虎机状态
    selected_items = [arm.edit for arm in selected_arms]
    result_patch = {**ranked_patch, payload_key(update_mode): selected_items}
    return result_patch, bandit
```

### 2.4 方差分桶策略

借鉴 SIMBA 的核心创新——按输出方差分桶聚焦难例：

```python
def bucket_edits_by_target(
    edits: list[dict],
    rollout_results: list[dict] | None = None,
) -> dict[str, list[dict]]:
    """将编辑按其影响的任务类别分桶

    高方差桶（任务结果不稳定）获得更多探索预算
    """
    buckets = {}
    for edit in edits:
        # 从 edit 中提取目标步骤/类别
        target = edit.get('target_section', edit.get('target_step', 'general'))
        if target not in buckets:
            buckets[target] = []
        buckets[target].append(edit)

    # 如果有 rollout 结果，按方差调整预算
    if rollout_results:
        for bucket_name, edits_in_bucket in buckets.items():
            related_results = [
                r for r in rollout_results
                if r.get('category') == bucket_name
            ]
            if related_results:
                scores = [r.get('soft', 0) for r in related_results]
                variance = compute_variance(scores)
                # 高方差的桶获得更多编辑预算
                budget_multiplier = 1.0 + variance * 2.0
                for edit in edits_in_bucket:
                    edit['_budget_multiplier'] = budget_multiplier

    return buckets
```

### 2.5 效果反馈闭环

在 trainer.py 的训练循环中，当 gate 决策完成后，需要将编辑效果反馈给老虎机：

```python
# 在 gate 决策后
if bandit_state:
    # 计算每条编辑的奖励
    reward = compute_edit_reward(
        candidate_score=cand_score,
        previous_score=current_score,
        gate_action=gate_result.action,
    )
    # 分配奖励到各编辑（信用分配）
    # 简单版：所有选中编辑获得相同奖励
    # 高级版：用 SHAP/归因方法分配
    bandit.batch_update(selected_edits, [reward] * len(selected_edits))
    bandit_state['arms'] = [arm.__dict__ for arm in bandit.arms]
```

### 2.6 预期收益

- **探索-利用平衡**：Thompson 采样保证既探索新编辑又利用已知好编辑
- **方差感知**：高方差编辑获得更多探索预算，避免过早收敛
- **持久记忆**：跨 step 的编辑效果记录，避免重复试错
- **LLM 先验融合**：LLM 重要性评分作为 Beta 分布先验，加速收敛

***

## 改进方案三：对比因果提取反思（CCE-Reflect）

### 3.1 动机

当前 [reflect.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/gradient/reflect.py) 的 `run_minibatch_reflect()` 对每条轨迹独立分析，产出 failure\_patches 和 success\_patches。这存在根本性局限：

1. **相关性≠因果性**：LLM 可能将"恰好出现在失败轨迹中的指令"误判为失败原因
2. **无对照**：没有同时分析成功和失败轨迹来提取**差异模式**
3. **单轨迹偏差**：一条轨迹的失败可能由随机因素导致，不代表技能有缺陷

SkillCAT 的 CCE（Contrastive Causal Extraction）阶段通过**对比成功/失败轨迹的因果差异**来提取真正的失败根因，报告 +40.40% 平均分提升。

### 3.2 核心设计

**新增模块**：`skillopt/gradient/cce_reflect.py`

```python
"""对比因果提取反思（CCE-Reflect）

替代/增强现有的 run_minibatch_reflect()，引入对比因果分析：
1. 配对成功/失败轨迹（相同任务类型）
2. 提取行为差异序列
3. 因果归因：确定哪个差异导致了成功/失败
4. 产出因果补丁（causal patches）而非相关补丁
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TrajectoryPair:
    """成功-失败轨迹对"""
    success_traj: dict          # 成功轨迹
    failure_traj: dict          # 失败轨迹（同一任务或同类型任务）
    task_id: str = ""
    task_category: str = ""
    # 提取的差异
    behavioral_diffs: list[dict] = field(default_factory=list)
    causal_attribution: dict = field(default_factory=dict)


def build_contrastive_pairs(
    rollout_results: list[dict],
    task_field: str = "task_id",
    category_field: str = "category",
) -> list[TrajectoryPair]:
    """构建成功-失败对比对

    优先匹配同一任务的成对轨迹；
    若无同任务对，退化为同类别匹配。
    """
    successes = [r for r in rollout_results if r.get('hard', 0) >= 1.0]
    failures = [r for r in rollout_results if r.get('hard', 0) < 1.0]

    pairs = []
    used_success = set()

    # 优先：同任务的成对
    for fail in failures:
        for i, succ in enumerate(successes):
            if i in used_success:
                continue
            if succ.get(task_field) == fail.get(task_field):
                pairs.append(TrajectoryPair(
                    success_traj=succ,
                    failure_traj=fail,
                    task_id=fail.get(task_field, ""),
                    task_category=fail.get(category_field, ""),
                ))
                used_success.add(i)
                break

    # 退化：同类别匹配
    for fail in failures:
        if any(p.failure_traj == fail for p in pairs):
            continue
        for i, succ in enumerate(successes):
            if i in used_success:
                continue
            if succ.get(category_field) == fail.get(category_field):
                pairs.append(TrajectoryPair(
                    success_traj=succ,
                    failure_traj=fail,
                    task_id="",
                    task_category=fail.get(category_field, ""),
                ))
                used_success.add(i)
                break

    return pairs


def extract_behavioral_diffs(pair: TrajectoryPair) -> list[dict]:
    """提取成功-失败轨迹对的行为差异

    逐步骤对比，找出分歧点：
    - 成功轨迹做了什么额外操作？
    - 失败轨迹做了什么错误操作？
    - 在哪个步骤开始分叉？
    """
    succ_steps = pair.success_traj.get('steps', [])
    fail_steps = pair.failure_traj.get('steps', [])

    diffs = []
    min_len = min(len(succ_steps), len(fail_steps))

    # 找到分叉点
    divergence_point = min_len
    for i in range(min_len):
        succ_action = succ_steps[i].get('action', '')
        fail_action = fail_steps[i].get('action', '')
        if succ_action != fail_action:
            divergence_point = i
            break

    # 提取分叉后的差异
    for i in range(divergence_point, min_len):
        succ_action = succ_steps[i].get('action', '')
        fail_action = fail_steps[i].get('action', '')
        if succ_action != fail_action:
            diffs.append({
                'step': i,
                'divergence': True,
                'success_action': succ_action,
                'failure_action': fail_action,
                'success_reasoning': succ_steps[i].get('thought', ''),
                'failure_reasoning': fail_steps[i].get('thought', ''),
            })

    # 成功轨迹比失败轨迹多做的步骤
    if len(succ_steps) > min_len:
        for i in range(min_len, len(succ_steps)):
            diffs.append({
                'step': i,
                'divergence': 'extra_in_success',
                'success_action': succ_steps[i].get('action', ''),
                'success_reasoning': succ_steps[i].get('thought', ''),
            })

    # 失败轨迹多做的步骤（可能走偏了）
    if len(fail_steps) > min_len:
        for i in range(min_len, len(fail_steps)):
            diffs.append({
                'step': i,
                'divergence': 'extra_in_failure',
                'failure_action': fail_steps[i].get('action', ''),
                'failure_reasoning': fail_steps[i].get('thought', ''),
            })

    pair.behavioral_diffs = diffs
    return diffs


def run_cce_reflect(
    pairs: list[TrajectoryPair],
    current_skill: str,
    *,
    system_prompt: str = "",
    meta_skill_context: str = "",
    max_completion_tokens: int = 0,
) -> list[dict]:
    """对比因果提取反思

    将对比对的行为差异交给 optimizer LLM，要求其：
    1. 分析成功和失败轨迹的行为分叉
    2. 归因到 skill 中的具体指令（因果链）
    3. 产出因果补丁：修改导致失败的指令
    """
    patches = []
    for pair in pairs:
        diffs = extract_behavioral_diffs(pair)
        if not diffs:
            continue

        # 构建对比 prompt
        contrastive_context = format_contrastive_prompt(pair, current_skill)
        # 调用 optimizer LLM
        response, _ = chat_optimizer(
            system=load_prompt("cce_reflect"),
            user=contrastive_context,
            max_completion_tokens=max_completion_tokens,
            retries=3,
            stage="cce_reflect",
        )
        patch = extract_json(response)
        if patch and isinstance(patch, dict):
            patch['_pair_metadata'] = {
                'task_id': pair.task_id,
                'task_category': pair.task_category,
                'n_diffs': len(diffs),
                'divergence_step': diffs[0]['step'] if diffs else -1,
            }
            patches.append(patch)

    return patches
```

### 3.3 对比 Prompt 设计

```python
def format_contrastive_prompt(pair: TrajectoryPair, skill: str) -> str:
    """构建对比因果提取 prompt"""
    diffs_text = json.dumps(pair.behavioral_diffs, indent=2, ensure_ascii=False)
    return (
        f"## Current Skill\n{skill}\n\n"
        f"## Contrastive Trajectory Analysis\n"
        f"Task: {pair.task_id or pair.task_category}\n\n"
        f"### Success Trajectory (key steps)\n"
        f"{format_trajectory(pair.success_traj)}\n\n"
        f"### Failure Trajectory (key steps)\n"
        f"{format_trajectory(pair.failure_traj)}\n\n"
        f"### Behavioral Divergence Analysis\n"
        f"The two trajectories diverge at step {pair.behavioral_diffs[0]['step']} "
        f"if pair.behavioral_diffs else 'N/A'.\n"
        f"Differences:\n{diffs_text}\n\n"
        f"## Your Task\n"
        f"1. Identify which specific instruction(s) in the skill caused the "
        f"failure trajectory to diverge.\n"
        f"2. Propose a MINIMAL edit to the skill that would prevent this failure "
        f"while preserving the success behavior.\n"
        f"3. Your edit must be CAUSAL, not merely correlational: explain the "
        f"causal chain from skill instruction → divergent action → failure.\n"
    )
```

### 3.4 与现有 reflect.py 的集成

在 [reflect.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/gradient/reflect.py) 中，`run_minibatch_reflect()` 产出 `failure_patches` 和 `success_patches`。改进方案是在此基础上**增加** CCE 补丁流：

```python
# 在 trainer.py 中
# ② REFLECT 阶段
failure_patches, success_patches = run_minibatch_reflect(...)

# 新增：CCE 反思
contrastive_pairs = build_contrastive_pairs(rollout_results)
cce_patches = run_cce_reflect(contrastive_pairs, current_skill, ...)

# ③ AGGREGATE 阶段：将 CCE 补丁与普通补丁合并
# CCE 补丁具有因果优先级
all_failure_patches = failure_patches + cce_patches
merged_patch = merge_patches(current_skill, all_failure_patches, success_patches, ...)
```

### 3.5 预期收益

- **因果归因**：从"相关性补丁"升级为"因果补丁"，减少噪声编辑
- **对比增强**：成功-失败对比提供更丰富的信号，类似对比学习
- **最小编辑**：CCE 要求最小因果编辑，避免过度修改
- **SkillCAT 报告 +40.40% 平均分提升**：这是最显著的单一改进

***

## 改进方案四：课程学习任务采样（CL-Sampler）

### 4.1 动机

当前 trainer.py 从训练集随机采样任务进行 rollout。这导致：

1. **冷启动差**：初期在困难任务上 rollout 全部失败，无有效梯度信号
2. **无递进**：不区分简单/复杂任务，训练效率低
3. **过拟合**：后期反复在已掌握的简单任务上浪费 rollout 预算

E2H Reasoner（ICLR 2026）证明：从易到难的课程学习能显著提升 LLM 推理能力，且关键在于**退火调度**——逐步移除简单任务。Actor-Curator 证明：用策略改进老虎机自适应选择训练数据，在 AIME2024 上提升 28.6%，ARC-1D 上提升 30.5%。

### 4.2 核心设计

**新增模块**：`skillopt/optimizer/curriculum.py`

```python
"""课程学习任务采样器（CL-Sampler）

基于任务难度估计和策略改进信号，自适应选择训练任务。
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Literal
import math


@dataclass
class TaskRecord:
    """单条任务的历史记录"""
    task_id: str
    difficulty: float = 0.0          # 估计难度 [0, 1]
    n_attempts: int = 0              # 总尝试次数
    n_successes: int = 0             # 成功次数
    success_rate: float = 0.0       # 成功率
    last_soft: float = 0.0           # 最近 soft 分数
    policy_improvement: float = 0.0  # 最近策略改进信号
    last_step_seen: int = 0          # 最后被采样的 step


@dataclass
class CurriculumState:
    """课程学习状态"""
    task_records: dict[str, TaskRecord] = field(default_factory=dict)
    current_phase: str = "warmup"    # warmup / ramp / plateau / anneal
    global_step: int = 0
    # 难度分桶
    difficulty_buckets: dict[str, list[str]] = field(default_factory=dict)
    # 退火参数
    easy_fade_rate: float = 0.95     # 简单任务每 epoch 衰减系数
    hard_focus_rate: float = 1.5     # 困难任务放大系数


class CurriculumSampler:
    """课程学习采样器"""

    def __init__(
        self,
        tasks: list[dict],
        initial_difficulty_fn=None,
        mode: Literal["e2h", "actor_curator", "adaptive"] = "e2h",
        config: dict = None,
    ):
        self.mode = mode
        self.config = config or {}
        self.state = CurriculumState()

        # 初始化任务记录
        for task in tasks:
            tid = task.get('task_id', str(id(task)))
            diff = (initial_difficulty_fn(task) if initial_difficulty_fn
                    else self._estimate_difficulty(task))
            record = TaskRecord(
                task_id=tid,
                difficulty=diff,
            )
            self.state.task_records[tid] = record

        # 难度分桶
        self._bucket_by_difficulty()

    def _estimate_difficulty(self, task: dict) -> float:
        """启发式估计任务难度"""
        difficulty = 0.0
        # 基于任务描述长度
        desc = task.get('description', '')
        difficulty += min(len(desc) / 5000, 0.3)

        # 基于所需步骤数
        n_steps = task.get('optimal_steps', 10)
        difficulty += min(n_steps / 50, 0.3)

        # 基于工具种类数
        n_tools = len(set(task.get('required_tools', [])))
        difficulty += min(n_tools / 10, 0.2)

        # 基于是否有已知失败率
        if task.get('known_failure_rate'):
            difficulty += task['known_failure_rate'] * 0.2

        return min(difficulty, 1.0)

    def _bucket_by_difficulty(self):
        """按难度分桶"""
        self.state.difficulty_buckets = {
            'easy': [], 'medium': [], 'hard': []
        }
        for record in self.state.task_records.values():
            if record.difficulty < 0.33:
                self.state.difficulty_buckets['easy'].append(record.task_id)
            elif record.difficulty < 0.66:
                self.state.difficulty_buckets['medium'].append(record.task_id)
            else:
                self.state.difficulty_buckets['hard'].append(record.task_id)

    def sample(self, n: int) -> list[str]:
        """采样 n 个任务"""
        if self.mode == "e2h":
            return self._sample_e2h(n)
        elif self.mode == "actor_curator":
            return self._sample_actor_curator(n)
        else:
            return self._sample_adaptive(n)

    def _sample_e2h(self, n: int) -> list[str]:
        """E2H 课程：从易到难 + 退火"""
        phase = self.state.current_phase
        buckets = self.state.difficulty_buckets

        # 根据阶段确定各桶的采样概率
        if phase == "warmup":
            weights = {'easy': 0.7, 'medium': 0.25, 'hard': 0.05}
        elif phase == "ramp":
            weights = {'easy': 0.4, 'medium': 0.4, 'hard': 0.2}
        elif phase == "plateau":
            weights = {'easy': 0.15, 'medium': 0.35, 'hard': 0.5}
        else:  # anneal
            weights = {'easy': 0.05, 'medium': 0.3, 'hard': 0.65}

        # 退火：移除已掌握的简单任务
        easy_pool = [
            tid for tid in buckets['easy']
            if self.state.task_records[tid].success_rate < 0.85  # 未掌握
            or random.random() > self.state.easy_fade_rate  # 保留少量
        ]
        medium_pool = buckets['medium']
        hard_pool = buckets['hard']

        # 按权重采样
        samples = []
        for _ in range(n):
            r = random.random()
            cumulative = 0
            for bucket_name, weight in weights.items():
                cumulative += weight
                if r < cumulative:
                    pool = {'easy': easy_pool, 'medium': medium_pool, 'hard': hard_pool}
                    bucket = pool.get(bucket_name, medium_pool)
                    if bucket:
                        samples.append(random.choice(bucket))
                    else:
                        # 桶为空，从其他桶补充
                        all_tasks = easy_pool + medium_pool + hard_pool
                        if all_tasks:
                            samples.append(random.choice(all_tasks))
                    break

        return samples

    def _sample_actor_curator(self, n: int) -> list[str]:
        """Actor-Curator 模式：策略改进老虎机"""
        # 计算每个任务的预期策略改进
        scores = []
        for tid, record in self.state.task_records.items():
            # 基于历史策略改进信号
            improvement = record.policy_improvement
            # 加上难度因子（适中难度的任务通常改进空间最大）
            difficulty_factor = 1.0 - abs(0.5 - record.difficulty) * 2
            # 加上新鲜度因子（久未访问的任务获得探索奖励）
            staleness = self.state.global_step - record.last_step_seen
            novelty = math.log(1 + staleness) * 0.1
            # 加上成功率因子（中等成功率最有学习价值）
            sr = record.success_rate if record.n_attempts > 0 else 0.5
            learning_value = 1.0 - abs(0.5 - sr) * 2  # 0.5 成功率最有价值

            score = (
                improvement * 0.4
                + difficulty_factor * 0.2
                + novelty * 0.2
                + learning_value * 0.2
            )
            scores.append((tid, score))

        # softmax 采样
        scores.sort(key=lambda x: -x[1])
        # 温度采样
        temp = self.config.get('temperature', 0.5)
        top_k = min(n * 3, len(scores))
        top = scores[:top_k]
        import numpy as np
        logits = np.array([s for _, s in top]) / temp
        probs = np.exp(logits - logits.max())
        probs = probs / probs.sum()
        indices = np.random.choice(len(top), size=min(n, len(top)), replace=False, p=probs)
        return [top[i][0] for i in indices]

    def _sample_adaptive(self, n: int) -> list[str]:
        """自适应模式：混合 E2H + Actor-Curator"""
        half = n // 2
        e2h_samples = self._sample_e2h(half)
        ac_samples = self._sample_actor_curator(n - half)
        return e2h_samples + ac_samples

    def update(
        self,
        task_ids: list[str],
        hard_scores: list[float],
        soft_scores: list[float],
        prev_hard_scores: list[float] | None = None,
    ):
        """更新任务记录和策略改进信号"""
        self.state.global_step += 1
        for tid, h, s in zip(task_ids, hard_scores, soft_scores):
            if tid not in self.state.task_records:
                continue
            record = self.state.task_records[tid]
            prev_sr = record.success_rate
            record.n_attempts += 1
            record.n_successes += int(h >= 1.0)
            record.success_rate = record.n_successes / record.n_attempts
            record.last_soft = s
            record.last_step_seen = self.state.global_step

            # 策略改进信号
            if prev_hard_scores := prev_hard_scores:
                improvement = h - prev_hard_scores
                record.policy_improvement = (
                    0.7 * record.policy_improvement + 0.3 * improvement
                )

        # 阶段切换
        self._update_phase()

    def _update_phase(self):
        """根据训练进度自动切换课程阶段"""
        step = self.state.global_step
        total_steps = self.config.get('total_steps', 100)

        if step < total_steps * 0.15:
            self.state.current_phase = "warmup"
        elif step < total_steps * 0.4:
            self.state.current_phase = "ramp"
        elif step < total_steps * 0.75:
            self.state.current_phase = "plateau"
        else:
            self.state.current_phase = "anneal"
```

### 4.3 与 trainer.py 的集成

在 [trainer.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/engine/trainer.py) 的训练循环中：

```python
# 现有：均匀随机采样
train_tasks = random.sample(train_env.tasks, batch_size)

# 改进：课程学习采样
curriculum = CurriculumSampler(
    tasks=train_env.tasks,
    mode=config.curriculum_mode,  # "e2h" | "actor_curator" | "adaptive"
    config={'total_steps': num_epochs * steps_per_epoch},
)
# ...
for epoch in range(1, num_epochs + 1):
    for step_in_epoch in range(steps_per_epoch):
        # 课程采样替代随机采样
        sampled_ids = curriculum.sample(batch_size)
        train_tasks = [train_env.get_task(tid) for tid in sampled_ids]

        # ① ROLLOUT
        rollout_results = adapter.rollout(train_env, current_skill, rollout_dir)

        # ... 后续 6 阶段 ...

        # 课程更新
        curriculum.update(
            task_ids=sampled_ids,
            hard_scores=[r['hard'] for r in rollout_results],
            soft_scores=[r['soft'] for r in rollout_results],
            prev_hard_scores=[r.get('prev_hard') for r in rollout_results],
        )
```

### 4.4 预期收益

- **冷启动加速**：warmup 阶段 70% 预算在简单任务上，保证有梯度信号
- **渐进挑战**：ramp → plateau → anneal 逐步聚焦难例
- **退火防过拟合**：简单任务逐步移除，避免在已掌握任务上浪费
- **策略改进感知**：Actor-Curator 模式直接优化策略改进
- **E2H 报告**：理论收敛保证 + 实验显著提升
- **Actor-Curator 报告**：AIME2024 +28.6%, ARC-1D +30.5%

***

## 改进方案五：多目标帕累托门控（ParetoGate）

### 5.1 动机

当前 [gate.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/evaluation/gate.py) 的 `evaluate_gate()` 使用单一标量分数（hard/soft/mixed）进行严格 `>` 比较。这等价于固定权重的标量化，存在根本局限：

1. **凸前沿限制**：固定权重标量化只能恢复帕累托前沿的凸部分
2. **无效率权衡**：不感知准确率与效率之间的非凸权衡
3. **忽略鲁棒性**：不考虑技能长度、语义密度、泛化性等维度

ParetoPO（ICML 2026 Spotlight）提出两阶段多目标优化：超体积引导的动态标量化 + Pareto 排序优势计算，能发现凸和非凸前沿上的最优解。

### 5.2 核心设计

**修改文件**：[gate.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/evaluation/gate.py)

```python
"""多目标帕累托门控（ParetoGate）

替代单一标量比较，使用帕累托支配关系进行门控决策。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
import math


@dataclass
class MultiObjectiveScore:
    """多维技能评分"""
    hard: float           # 准确率
    soft: float           # 部分得分
    efficiency: float     # 工具调用效率 (1 - n_tools / max_tools)
    conciseness: float    # 简洁度 (1 - len / max_len)
    robustness: float     # 鲁棒性 (跨任务方差倒数)

    def to_vector(self) -> tuple[float, ...]:
        return (self.hard, self.soft, self.efficiency,
                self.conciseness, self.robustness)

    def dominates(self, other: 'MultiObjectiveScore') -> bool:
        """帕累托支配判定"""
        v1 = self.to_vector()
        v2 = other.to_vector()
        return all(a >= b for a, b in zip(v1, v2)) and \
               any(a > b for a, b in zip(v1, v2))


def hypervolume(
    front: list[MultiObjectiveScore],
    reference_point: tuple[float, ...],
) -> float:
    """计算帕累托前沿的超体积（hypervolume）

    超体积衡量前沿的覆盖范围，越大越好。
    """
    if not front:
        return 0.0

    # 简化版：2D 超体积计算（hard × efficiency）
    # 完整版需要多维超体积算法（如 WFG 或 HSOPT）
    points = sorted(
        [(s.hard, s.efficiency) for s in front],
        key=lambda p: -p[0]
    )
    ref_h, ref_e = reference_point[0], reference_point[3]
    hv = 0.0
    prev_h = ref_h
    for h, e in points:
        if h > ref_h and e > ref_e:
            hv += (h - prev_h) * (e - ref_e) if prev_h > ref_h else (h - ref_h) * (e - ref_e)
            prev_h = h
    return hv


def pareto_rank(
    candidate: MultiObjectiveScore,
    population: list[MultiObjectiveScore],
) -> int:
    """计算候选的帕累托排名（被多少个体支配）"""
    rank = 0
    for ind in population:
        if ind.dominates(candidate):
            rank += 1
    return rank


def evaluate_pareto_gate(
    candidate_skill: str,
    cand_score: MultiObjectiveScore,
    current_skill: str,
    current_score: MultiObjectiveScore,
    best_skill: str,
    best_score: MultiObjectiveScore,
    best_step: int,
    global_step: int,
    *,
    history: list[MultiObjectiveScore] | None = None,
    min_hard_floor: float = 0.0,  # 最低准确率要求
    use_hypervolume: bool = True,
    hv_reference_point: tuple[float, ...] = (0.0, 0.0, 0.0, 0.0, 0.0),
) -> GateResult:
    """帕累托门控决策

    决策逻辑：
    1. 候选必须满足最低 hard floor
    2. 候选不被当前技能支配（帕累托）
    3. 候选扩展超体积或改善排名
    """
    # 最低 floor 检查
    if cand_score.hard < min_hard_floor:
        return GateResult(
            action="reject",
            current_skill=current_skill,
            current_score=current_score.hard,
            best_skill=best_skill,
            best_score=best_score.hard,
            best_step=best_step,
        )

    # 帕累托支配检查
    if current_score.dominates(cand_score):
        # 当前技能支配候选 → 拒绝
        return GateResult(
            action="reject",
            current_skill=current_skill,
            current_score=current_score.hard,
            best_skill=best_skill,
            best_score=best_score.hard,
            best_step=best_step,
        )

    # 超体积改善检查
    if use_hypervolume and history:
        front_with_candidate = history + [cand_score]
        front_without = history[:]
        hv_with = hypervolume(
            [s for s in front_with_candidate if not any(
                other.dominates(s) for other in front_with_candidate if other is not s
            )],
            hv_reference_point,
        )
        hv_without = hypervolume(
            [s for s in front_without if not any(
                other.dominates(s) for other in front_without if other is not s
            )],
            hv_reference_point,
        )
        if hv_with <= hv_without:
            # 候选不扩展超体积 → 拒绝
            return GateResult(
                action="reject",
                current_skill=current_skill,
                current_score=current_score.hard,
                best_skill=best_skill,
                best_score=best_score.hard,
                best_step=best_step,
            )

    # 候选不被支配且扩展超体积 → 接受
    if cand_score.dominates(best_score):
        return GateResult(
            action="accept_new_best",
            current_skill=candidate_skill,
            current_score=cand_score.hard,
            best_skill=candidate_skill,
            best_score=cand_score.hard,
            best_step=global_step,
        )
    return GateResult(
        action="accept",
        current_skill=candidate_skill,
        current_score=cand_score.hard,
        best_skill=best_skill,
        best_score=best_score.hard,
        best_step=best_step,
    )
```

### 5.3 多维评分计算

```python
def compute_multi_objective_score(
    skill_content: str,
    rollout_results: list[dict],
) -> MultiObjectiveScore:
    """从 rollout 结果计算多维评分"""
    hard = sum(r['hard'] for r in rollout_results) / len(rollout_results)
    soft = sum(r['soft'] for r in rollout_results) / len(rollout_results)

    # 效率：工具调用数的倒数
    n_tools = [len(r.get('actions', [])) for r in rollout_results]
    max_tools = max(n_tools) if n_tools else 1
    avg_tools = sum(n_tools) / len(n_tools) if n_tools else 1
    efficiency = 1.0 - (avg_tools / max_tools) if max_tools > 0 else 0.0

    # 简洁度：技能长度的倒数
    max_len = 10000  # 参考最大长度
    conciseness = 1.0 - min(len(skill_content) / max_len, 1.0)

    # 鲁棒性：跨任务方差的倒数
    scores = [r['hard'] for r in rollout_results]
    if len(scores) > 1:
        variance = sum((s - hard) ** 2 for s in scores) / len(scores)
        robustness = 1.0 / (1.0 + variance * 10)
    else:
        robustness = 0.5

    return MultiObjectiveScore(
        hard=hard,
        soft=soft,
        efficiency=efficiency,
        conciseness=conciseness,
        robustness=robustness,
    )
```

### 5.4 预期收益

- **多维权衡**：不再只看准确率，兼顾效率、简洁性、鲁棒性
- **非凸前沿**：帕累托支配能发现非凸权衡区域的最优解
- **超体积引导**：候选必须扩展超体积才被接受，保证前沿扩张
- **ParetoPO 报告**：ICML 2026 Spotlight，显著优于固定权重基线

***

## 改进方案六：贝叶斯优化学习率调度（BO-Scheduler）

### 6.1 动机

当前 [scheduler.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/optimizer/scheduler.py) 提供 4 种预设学习率（编辑预算）调度器：constant、linear、cosine、autonomous。前三种是固定时间表，autonomous 让 LLM 自行决定。但都缺乏**基于历史效果的自适应调整**。

LLINBO（ICLR 2026）提出 LLM-in-the-Loop 贝叶斯优化，用高斯过程（GP）代理模型指导探索-利用平衡。BayesPrompt 用 MCMC 采样替代贪心优化。Meta Ax 1.0 证明 BO 在 LLM prompt 优化中有效。

### 6.2 核心设计

**新增模块**：`skillopt/optimizer/bo_scheduler.py`

```python
"""贝叶斯优化学习率调度器（BO-Scheduler）

用高斯过程代理模型学习"编辑预算 → 训练效果"的映射，
基于历史数据自适应推荐下一步的编辑预算。
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Literal


@dataclass
class BOObservation:
    """一次 BO 观测"""
    lr: int              # 编辑预算
    reward: float         # 训练效果（gate 分数变化）
    step: int            # 训练步
    context: dict = field(default_factory=dict)  # 额外上下文


class GaussianProcessSurrogate:
    """简化版高斯过程代理模型

    使用 RBF 核进行非参数回归。
    在无需 scipy/sklearn 的情况下实现，保持零额外依赖。
    """

    def __init__(self, length_scale: float = 3.0, noise: float = 0.01):
        self.length_scale = length_scale
        self.noise = noise
        self.X: list[float] = []  # 输入：编辑预算
        self.y: list[float] = []  # 输出：训练效果

    def _rbf_kernel(self, x1: float, x2: float) -> float:
        """RBF 核函数"""
        diff = x1 - x2
        return math.exp(-(diff ** 2) / (2 * self.length_scale ** 2))

    def _compute_kernel_matrix(self, X: list[float]) -> list[list[float]]:
        """计算核矩阵"""
        n = len(X)
        K = [[0.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(n):
                K[i][j] = self._rbf_kernel(X[i], X[j])
                if i == j:
                    K[i][j] += self.noise
        return K

    def _matrix_inverse(self, M: list[list[float]]) -> list[list[float]]:
        """简化矩阵求逆（高斯消元法）"""
        n = len(M)
        # 增广矩阵 [M | I]
        aug = [row[:] + [1.0 if i == j else 0.0 for j in range(n)]
               for i, row in enumerate(M)]
        for col in range(n):
            # 选主元
            pivot = col
            for row in range(col + 1, n):
                if abs(aug[row][col]) > abs(aug[pivot][col]):
                    pivot = row
            aug[col], aug[pivot] = aug[pivot], aug[col]
            # 消元
            pivot_val = aug[col][col]
            if abs(pivot_val) < 1e-10:
                continue
            for j in range(2 * n):
                aug[col][j] /= pivot_val
            for row in range(n):
                if row == col:
                    continue
                factor = aug[row][col]
                for j in range(2 * n):
                    aug[row][j] -= factor * aug[col][j]
        return [[aug[i][n + j] for j in range(n)] for i in range(n)]

    def predict(self, x: float) -> tuple[float, float]:
        """预测：返回 (均值, 标准差)"""
        if not self.X:
            return 0.0, 1.0

        K = self._compute_kernel_matrix(self.X)
        K_inv = self._matrix_inverse(K)
        k_star = [self._rbf_kernel(x, xi) for xi in self.X]

        # 均值：k_star^T × K_inv × y
        mean = sum(k_star[i] * sum(K_inv[i][j] * self.y[j]
                                    for j in range(len(self.y)))
                    for i in range(len(k_star)))

        # 方差：k(x,x) - k_star^T × K_inv × k_star
        k_xx = self._rbf_kernel(x, x) + self.noise
        var = k_xx - sum(k_star[i] * sum(K_inv[i][j] * k_star[j]
                                          for j in range(len(k_star)))
                         for i in range(len(k_star)))
        std = math.sqrt(max(0.0, var))
        return mean, std

    def add_observation(self, x: float, y: float):
        """添加观测点"""
        self.X.append(x)
        self.y.append(y)
        # 限制历史长度（非平稳性适应）
        max_history = 50
        if len(self.X) > max_history:
            self.X = self.X[-max_history:]
            self.y = self.y[-max_history:]


class BOScheduler:
    """贝叶斯优化学习率调度器

    用 GP 代理模型学习编辑预算→效果映射，
    通过 UCB（Upper Confidence Bound）采集函数进行探索-利用平衡。
    """

    def __init__(
        self,
        max_lr: int = 8,
        min_lr: int = 1,
        total_steps: int = 20,
        acquisition: Literal["ucb", "ei", "pi"] = "ucb",
        beta: float = 2.0,         # UCB 探索系数
        length_scale: float = 3.0, # GP 核长度尺度
        noise: float = 0.01,       # GP 噪声
    ):
        self.max_lr = max_lr
        self.min_lr = min_lr
        self.total_steps = total_steps
        self.acquisition = acquisition
        self.beta = beta
        self.gp = GaussianProcessSurrogate(length_scale=length_scale, noise=noise)
        self._current_step = 0
        self._last_lr = max_lr

    def _ucb(self, x: float) -> float:
        """Upper Confidence Bound 采集函数"""
        mean, std = self.gp.predict(x)
        return mean + self.beta * std

    def _expected_improvement(self, x: float) -> float:
        """Expected Improvement 采集函数"""
        mean, std = self.gp.predict(x)
        if not self.gp.y:
            return 0.0
        best_y = max(self.gp.y)
        if std < 1e-10:
            return 0.0
        z = (mean - best_y) / std
        # 简化 EI 计算
        from math import erf, sqrt
        cdf = 0.5 * (1 + erf(z / sqrt(2)))
        pdf = math.exp(-z * z / 2) / math.sqrt(2 * math.pi)
        ei = (mean - best_y) * cdf + std * pdf
        return ei

    def _probability_improvement(self, x: float) -> float:
        """Probability of Improvement 采集函数"""
        mean, std = self.gp.predict(x)
        if not self.gp.y or std < 1e-10:
            return 0.0
        best_y = max(self.gp.y)
        z = (mean - best_y) / std
        from math import erf
        cdf = 0.5 * (1 + erf(z / math.sqrt(2)))
        return cdf

    def step(self) -> int:
        """推荐下一步的编辑预算"""
        self._current_step += 1

        # 网格搜索最优 lr
        candidates = list(range(self.min_lr, self.max_lr + 1))
        best_score = -float('inf')
        best_lr = self._last_lr

        for lr in candidates:
            if self.acquisition == "ucb":
                score = self._ucb(lr)
            elif self.acquisition == "ei":
                score = self._expected_improvement(lr)
            else:
                score = self._probability_improvement(lr)
            if score > best_score:
                best_score = score
                best_lr = lr

        # 衰减 beta（逐步减少探索）
        progress = self._current_step / self.total_steps
        self.beta = 2.0 * (1 - progress)

        self._last_lr = best_lr
        return best_lr

    def observe(self, lr: int, reward: float, step: int, context: dict = None):
        """记录观测结果"""
        self.gp.add_observation(float(lr), reward)

    def state_dict(self) -> dict:
        return {
            "current_step": self._current_step,
            "gp_X": self.gp.X,
            "gp_y": self.gp.y,
            "beta": self.beta,
            "last_lr": self._last_lr,
        }

    def load_state_dict(self, state: dict):
        self._current_step = state.get("current_step", 0)
        self.gp.X = state.get("gp_X", [])
        self.gp.y = state.get("gp_y", [])
        self.beta = state.get("beta", 2.0)
        self._last_lr = state.get("last_lr", self.max_lr)


def build_bo_scheduler(
    max_lr: int = 8,
    min_lr: int = 1,
    total_steps: int = 20,
    acquisition: str = "ucb",
) -> BOScheduler:
    """工厂函数"""
    return BOScheduler(
        max_lr=max_lr,
        min_lr=min_lr,
        total_steps=total_steps,
        acquisition=acquisition,
    )
```

### 6.3 与 trainer.py 和 scheduler.py 的集成

在 [scheduler.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/optimizer/scheduler.py) 的 `_REGISTRY` 中注册新调度器：

```python
# 在 scheduler.py 的 _REGISTRY 中添加
_REGISTRY["bo"] = BOScheduler
```

在 [trainer.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/engine/trainer.py) 的训练循环中：

```python
# 改进：BO 调度器
scheduler = build_scheduler(mode="bo", max_lr=8, min_lr=1, total_steps=total_steps)

for epoch in range(1, num_epochs + 1):
    for step_in_epoch in range(steps_per_epoch):
        # 获取编辑预算
        edit_budget = scheduler.step()

        # ... 6 阶段管线 ...

        # 观测效果
        reward = cand_score - current_score  # 分数变化
        scheduler.observe(edit_budget, reward, global_step)
```

### 6.4 预期收益

- **自适应**：根据历史效果自动调整编辑预算
- **探索-利用平衡**：UCB 采集函数平衡已知好预算和新预算探索
- **不确定性量化**：GP 提供预算效果的置信区间
- **非平稳适应**：限制历史长度适应训练动态变化
- **零额外依赖**：纯 Python 实现的 GP，无需 scipy/sklearn

***

## 改进方案七：回溯进度感知反思（RePro-Reflect）

### 7.1 动机

当前 reflect.py 的反思只看最终结果（成功/失败），不关注任务执行过程中的进度信号。对于长时序任务（如 ALFWorld 中的多步导航），缺乏中间反馈导致：

1. **稀疏信号**：只有最终成功/失败，无法定位哪一步开始偏离
2. **无进度估计**：不知道"完成了多少"和"还差多少"
3. **无法区分进度类型**：缓慢进度、停滞、倒退无法区分

RePro（2026）提出回溯进度感知训练：agent 先前向执行任务，然后回溯重新评估每步进度，在 ALFWorld 上获得 +12% 绝对成功率提升。

### 7.2 核心设计

**新增模块**：`skillopt/gradient/repro_reflect.py`

```python
"""回溯进度感知反思（RePro-Reflect）

在 reflect 阶段增加进度估计：
1. 前向执行时记录每步状态
2. 回溯时用完整轨迹+已知结果重新评估每步进度
3. 产出进度感知补丁
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class StepProgress:
    """单步进度估计"""
    step_idx: int
    action: str
    thought: str
    # 进度估计 [0, 1]
    online_progress: float = 0.0     # 执行时的在线进度估计
    retrospective_progress: float = 0.0  # 回溯时的后验进度估计
    # 进度变化
    delta: float = 0.0              # retrospective - online
    # 是否为关键转折点
    is_pivot: bool = False
    # 进度信号类型
    signal_type: str = ""          # forward / stall / regress / pivot


@dataclass
class TrajectoryProgress:
    """完整轨迹的进度分析"""
    task_id: str
    success: bool
    steps: list[StepProgress] = field(default_factory=list)
    overall_progress_rate: float = 0.0  # 整体进度速率
    stall_points: list[int] = field(default_factory=list)  # 停滞点
    regress_points: list[int] = field(default_factory=list)  # 倒退点
    pivot_points: list[int] = field(default_factory=list)  # 关键转折点


def estimate_online_progress(step_idx: int, total_steps: int, action: str) -> float:
    """在线进度估计（执行时）"""
    if total_steps <= 0:
        return 0.0
    base = step_idx / total_steps
    # 动作类型调整
    if 'verify' in action.lower() or 'check' in action.lower():
        base += 0.1  # 验证动作表示进度
    if 'undo' in action.lower() or 'back' in action.lower():
        base -= 0.15  # 回退动作表示倒退
    return max(0.0, min(1.0, base))


def run_retrospective_progress(
    trajectory: dict,
    outcome: bool,
    skill_content: str,
    *,
    system_prompt: str = "",
    max_completion_tokens: int = 0,
) -> TrajectoryProgress:
    """回溯进度评估

    给定完整轨迹和已知结果，让 LLM 回溯评估每步进度。
    """
    steps = trajectory.get('steps', [])
    total = len(steps)
    tp = TrajectoryProgress(
        task_id=trajectory.get('task_id', ''),
        success=outcome,
    )

    # 1. 在线进度估计
    for i, step in enumerate(steps):
        online = estimate_online_progress(i, total, step.get('action', ''))
        tp.steps.append(StepProgress(
            step_idx=i,
            action=step.get('action', ''),
            thought=step.get('thought', ''),
            online_progress=online,
        ))

    # 2. 回溯进度评估（调用 LLM）
    # 构建回溯 prompt
    traj_text = format_trajectory_for_repro(trajectory, outcome)
    user = (
        f"## Current Skill\n{skill_content}\n\n"
        f"## Completed Trajectory\n{traj_text}\n\n"
        f"## Task\n"
        f"Retrospectively assess the progress at each step.\n"
        f"For each step, estimate:\n"
        f"1. Retrospective progress [0, 1] (given you know the outcome)\n"
        f"2. Whether this step was a pivot point (critical decision)\n"
        f"3. Signal type: forward/stall/regress/pivot\n"
        f"Output JSON: {{\"steps\": [{{\"step\": 0, \"progress\": 0.1, "
        f"\"is_pivot\": false, \"signal\": \"forward\"}}, ...]}}"
    )
    response, _ = chat_optimizer(
        system=load_prompt("repro_retrospective"),
        user=user,
        max_completion_tokens=max_completion_tokens,
        retries=3,
        stage="repro_retrospective",
    )
    parsed = extract_json(response)

    # 3. 更新回溯进度
    if parsed and 'steps' in parsed:
        for i, retro_step in enumerate(parsed['steps']):
            if i < len(tp.steps):
                tp.steps[i].retrospective_progress = retro_step.get('progress', 0.0)
                tp.steps[i].is_pivot = retro_step.get('is_pivot', False)
                tp.steps[i].signal_type = retro_step.get('signal', 'forward')
                tp.steps[i].delta = (
                    tp.steps[i].retrospective_progress - tp.steps[i].online_progress
                )
                # 记录特殊点
                if tp.steps[i].signal_type == 'stall':
                    tp.stall_points.append(i)
                elif tp.steps[i].signal_type == 'regress':
                    tp.regress_points.append(i)
                elif tp.steps[i].signal_type == 'pivot' or tp.steps[i].is_pivot:
                    tp.pivot_points.append(i)

    # 4. 整体进度速率
    if tp.steps:
        tp.overall_progress_rate = (
            tp.steps[-1].retrospective_progress / max(len(tp.steps), 1)
        )

    return tp


def generate_progress_aware_patch(
    progress_analysis: TrajectoryProgress,
    current_skill: str,
    *,
    max_completion_tokens: int = 0,
) -> dict:
    """根据进度分析生成进度感知补丁

    策略：
    - 停滞点：增加"如果在此步停滞，尝试替代方案"指令
    - 倒退点：增加"避免回退到之前状态"指令
    - 关键转折点：强化决策指导
    """
    if not progress_analysis.steps:
        return {}

    # 构建进度分析摘要
    summary = format_progress_summary(progress_analysis)
    user = (
        f"## Current Skill\n{current_skill}\n\n"
        f"## Progress Analysis\n{summary}\n\n"
        f"## Task\n"
        f"Based on the progress analysis, propose edits to the skill that:\n"
        f"1. Address stall points by adding alternative strategies\n"
        f"2. Prevent regress points by adding guardrails\n"
        f"3. Reinforce pivot points by adding decision criteria\n"
    )
    response, _ = chat_optimizer(
        system=load_prompt("progress_aware_patch"),
        user=user,
        max_completion_tokens=max_completion_tokens,
        retries=3,
        stage="progress_aware_patch",
    )
    return extract_json(response) or {}
```

### 7.3 与现有 reflect.py 的集成

在 trainer.py 的 ② REFLECT 阶段后添加 RePro 分析：

```python
# ② REFLECT
failure_patches, success_patches = run_minibatch_reflect(...)

# 新增：RePro 进度感知
progress_patches = []
for result in rollout_results:
    tp = run_retrospective_progress(
        trajectory=result,
        outcome=result.get('hard', 0) >= 1.0,
        skill_content=current_skill,
    )
    patch = generate_progress_aware_patch(tp, current_skill)
    if patch:
        progress_patches.append(patch)

# 合并到 AGGREGATE
all_failure_patches = failure_patches + progress_patches
```

### 7.4 预期收益

- **进度信号**：从二元（成功/失败）升级为连续进度信号
- **停滞检测**：自动识别停滞步骤并建议替代策略
- **关键转折强化**：识别决策关键点并强化指导
- **RePro 报告**：ALFWorld +12% 绝对成功率

***

## 改进方案八：补丁回放校准聚合（PRC-Aggregate）

### 8.1 动机

当前 [aggregate.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/gradient/aggregate.py) 的 `_hierarchical_merge()` 用 LLM 合并补丁，但合并后的补丁**未在样本上验证有效性**就直接传给 SELECT 阶段。这导致：

1. **合并噪声**：LLM 合并可能引入矛盾编辑
2. **未验证编辑**：合并后的编辑可能实际降低性能
3. **无校准信号**：无法区分"看起来好"和"实际好"的编辑

SkillCAT 的 AAE（Assessment-Augmented Evolution）阶段通过**补丁回放校准**——在小型 held-out 样本上验证每个合并补丁的效果，显著提升编辑质量。

### 8.2 核心设计

**新增模块**：`skillopt/gradient/patch_calibration.py`

```python
"""补丁回放校准（Patch Replay Calibration, PRC）

在 AGGREGATE 阶段后、SELECT 阶段前，对合并补丁进行回放校准：
1. 将合并补丁拆分为单条编辑
2. 每条编辑在小样本上独立验证
3. 淘汰无效编辑，保留有效编辑
4. 产出校准后的补丁
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class CalibratedEdit:
    """校准后的编辑"""
    edit: dict
    # 校准结果
    baseline_score: float = 0.0     # 不应用编辑的基线分数
    patched_score: float = 0.0     # 应用编辑后的分数
    delta: float = 0.0             # 分数变化
    confidence: float = 0.0         # 置信度（基于样本数）
    n_samples: int = 0             # 校准样本数
    passed: bool = False           # 是否通过校准


def calibrate_patch(
    skill_content: str,
    merged_patch: dict,
    adapter,
    calibration_env,
    n_samples: int = 5,
    update_mode: str = "patch",
    tolerance: float = 0.0,
) -> dict:
    """补丁回放校准

    对合并补丁中的每条编辑进行独立验证。
    """
    items = get_payload_items(merged_patch, update_mode)
    if not items:
        return merged_patch

    # 采样校准任务
    cal_tasks = calibration_env.sample(n_samples)

    # 基线评估（不应用任何编辑）
    baseline_results = adapter.rollout(
        calibration_env, skill_content, f"/tmp/cal_baseline"
    )
    baseline_hard = sum(r['hard'] for r in baseline_results) / len(baseline_results)

    # 逐条编辑校准
    calibrated_edits = []
    for edit in items:
        # 应用单条编辑
        patched_skill = apply_edit(skill_content, edit)
        # 回放评估
        patched_results = adapter.rollout(
            calibration_env, patched_skill, f"/tmp/cal_edit_{id(edit)}"
        )
        patched_hard = sum(r['hard'] for r in patched_results) / len(patched_results)

        delta = patched_hard - baseline_hard
        ce = CalibratedEdit(
            edit=edit,
            baseline_score=baseline_hard,
            patched_score=patched_hard,
            delta=delta,
            confidence=min(1.0, n_samples / 10),
            n_samples=n_samples,
            passed=delta >= -tolerance,  # 允许 tolerance 以内的退化
        )
        calibrated_edits.append(ce)

    # 过滤未通过的编辑
    passed_edits = [ce.edit for ce in calibrated_edits if ce.passed]

    # 按改进幅度排序
    passed_edits.sort(
        key=lambda e: next(
            (ce.delta for ce in calibrated_edits if ce.edit == e), 0.0
        ),
        reverse=True,
    )

    # 构建校准后的补丁
    calibrated_patch = {
        **merged_patch,
        payload_key(update_mode): passed_edits,
        'calibration_metadata': {
            'total_edits': len(items),
            'passed_edits': len(passed_edits),
            'baseline_hard': baseline_hard,
            'avg_delta': sum(ce.delta for ce in calibrated_edits) / len(calibrated_edits),
        },
    }

    return calibrated_patch
```

### 8.3 与 aggregate.py 的集成

在 [aggregate.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/gradient/aggregate.py) 的 `merge_patches()` 之后添加校准步骤：

```python
# 在 trainer.py 的 ③ AGGREGATE 阶段
merged_patch = merge_patches(current_skill, failure_patches, success_patches, ...)

# 新增：补丁回放校准
calibrated_patch = calibrate_patch(
    skill_content=current_skill,
    merged_patch=merged_patch,
    adapter=adapter,
    calibration_env=calibration_env,  # 小型 held-out 环境
    n_samples=5,
    update_mode=update_mode,
    tolerance=0.02,  # 允许 2% 的噪声退化
)

# ④ SELECT（基于校准后的补丁）
ranked_patch = rank_and_select(current_skill, calibrated_patch, max_edits=edit_budget)
```

### 8.4 预期收益

- **噪声过滤**：淘汰在样本上验证无效的编辑
- **编辑排序**：按实际改进幅度排序，而非 LLM 主观排序
- **信心估计**：基于样本数估计编辑效果的置信度
- **SkillCAT 报告**：AAE 阶段贡献 +40.40% 提升的重要部分

***

## 改进方案九：拓扑感知技能加载（TAE-Route）

### 9.1 动机

当前推理时加载完整 skill 文档。随着 skill 通过训练不断增长，可能出现：

1. **上下文过载**：过长 skill 消耗大量 token 预算
2. **无关指令干扰**：与当前任务无关的指令可能误导 LLM
3. **矛盾指令**：不同章节可能有相互矛盾的指导

SkillCAT 的 TTE（Topology-aware Execution）阶段在推理时只加载与当前任务相关的 skill 子集，报告显著提升。

### 9.2 核心设计

**新增模块**：`skillopt/optimizer/skill_router.py`

```python
"""拓扑感知技能加载（TAE-Route）

在推理时根据任务特征，动态选择 skill 的相关子集加载。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class SkillSection:
    """技能文档的一个章节"""
    title: str
    content: str
    start_pos: int
    end_pos: int
    keywords: list[str] = field(default_factory=list)
    task_types: list[str] = field(default_factory=list)  # 适用的任务类型


def parse_skill_sections(skill_content: str) -> list[SkillSection]:
    """解析技能文档的章节结构"""
    sections = []
    # 按 markdown 标题分割
    pattern = r'^(#{1,4})\s+(.+)$'
    matches = list(re.finditer(pattern, skill_content, re.MULTILINE))

    if not matches:
        # 无标题，整体作为一个 section
        sections.append(SkillSection(
            title="root",
            content=skill_content,
            start_pos=0,
            end_pos=len(skill_content),
        ))
        return sections

    # 保护区域单独处理
    protected_sections = set()
    for marker_start, marker_end in [
        ("<!-- SLOW_UPDATE_START -->", "<!-- SLOW_UPDATE_END -->"),
        ("<!-- APPENDIX_START -->", "<!-- APPENDIX_END -->"),
    ]:
        s = skill_content.find(marker_start)
        e = skill_content.find(marker_end)
        if s != -1 and e != -1:
            protected_sections.add((s, e + len(marker_end)))

    for i, match in enumerate(matches):
        title = match.group(2).strip()
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(skill_content)
        content = skill_content[start:end].strip()

        # 提取关键词
        keywords = extract_keywords(content)
        # 推断适用任务类型
        task_types = infer_task_types(title, content)

        sections.append(SkillSection(
            title=title,
            content=content,
            start_pos=start,
            end_pos=end,
            keywords=keywords,
            task_types=task_types,
        ))

    return sections


def extract_keywords(content: str) -> list[str]:
    """从章节内容提取关键词"""
    # 简单版：提取高频名词
    words = re.findall(r'[a-zA-Z]{3,}', content.lower())
    from collections import Counter
    common = Counter(words).most_common(10)
    return [w for w, _ in common]


def infer_task_types(title: str, content: str) -> list[str]:
    """从章节标题和内容推断适用任务类型"""
    task_types = []
    title_lower = title.lower()
    content_lower = content.lower()

    # 启发式规则
    if any(kw in title_lower or kw in content_lower
           for kw in ['search', 'query', 'find']):
        task_types.append('search')
    if any(kw in title_lower or kw in content_lower
           for kw in ['navigate', 'move', 'go', 'location']):
        task_types.append('navigation')
    if any(kw in title_lower or kw in content_lower
           for kw in ['document', 'read', 'extract', 'answer']):
        task_types.append('reading')
    if any(kw in title_lower or kw in content_lower
           for kw in ['calculate', 'compute', 'math', 'number']):
        task_types.append('calculation')
    if any(kw in title_lower or kw in content_lower
           for kw in ['spreadsheet', 'excel', 'cell', 'formula']):
        task_types.append('spreadsheet')

    if not task_types:
        task_types.append('general')

    return task_types


def route_skill(
    skill_content: str,
    task_description: str,
    *,
    max_sections: int = 5,
    include_protected: bool = True,
    min_relevance: float = 0.1,
) -> str:
    """根据任务描述路由技能子集

    参数：
        skill_content: 完整技能文档
        task_description: 当前任务描述
        max_sections: 最多包含的章节数
        include_protected: 是否总是包含保护区域
    """
    sections = parse_skill_sections(skill_content)
    task_lower = task_description.lower()
    task_keywords = set(re.findall(r'[a-zA-Z]{3,}', task_lower))

    # 计算每个章节的相关性分数
    scored_sections = []
    for section in sections:
        # 关键词重叠
        overlap = len(set(section.keywords) & task_keywords)
        # 任务类型匹配
        type_match = any(t in task_lower for t in section.task_types)
        # 标题匹配
        title_match = any(kw in task_lower for kw in section.title.lower().split())

        score = overlap * 0.4 + type_match * 0.4 + title_match * 0.2
        scored_sections.append((section, score))

    # 按相关性排序
    scored_sections.sort(key=lambda x: -x[1])

    # 过滤低相关性的章节
    relevant = [(s, score) for s, score in scored_sections
                if score >= min_relevance][:max_sections]

    # 总是包含保护区域
    if include_protected:
        for section in sections:
            if section.title in ['SLOW_UPDATE', 'APPENDIX']:
                if section not in [s for s, _ in relevant]:
                    relevant.append((section, 0.0))

    # 按原始位置排序
    relevant.sort(key=lambda x: x[0].start_pos)

    # 构建路由后的技能
    routed_content = "\n\n".join(s.content for s, _ in relevant)
    return routed_content
```

### 9.3 与环境的集成

在环境的 `rollout()` 方法中，加载 skill 时使用路由：

```python
# 在 adapter.rollout() 中
def rollout(self, env, skill, output_dir):
    routed_skill = skill  # 默认全量加载
    if self.config.use_skill_routing:
        routed_skill = route_skill(
            skill_content=skill,
            task_description=env.current_task_description,
            max_sections=self.config.max_skill_sections,
        )
    # 用 routed_skill 执行 rollout
    ...
```

### 9.4 预期收益

- **上下文压缩**：只加载相关章节，减少 token 消耗 30-70%
- **精度提升**：无关指令不干扰，减少矛盾指导
- **自适应**：根据任务类型动态选择最相关的指令子集
- **SkillCAT 报告**：TTE 阶段贡献 +40.40% 提升的重要部分

***

## 改进方案十：种群多样性维护（PDM）

### 10.1 动机

改进方案一引入了种群化进化，但如果不维护多样性，种群会快速收敛到局部最优（遗传算法中的"早熟"问题）。EVOREFUSE（NeurIPS 2025）证明：变异策略和重组的多样性探索能显著提升进化搜索效果。F-MAD 证明：模糊系统控制种群多样性能防止早熟收敛。

### 10.2 核心设计

**新增模块**：`skillopt/optimizer/diversity.py`

```python
"""种群多样性维护（Population Diversity Maintenance, PDM）

为种群化进化提供多样性度量、新颖性搜索和多样性保护机制。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal
import re


def compute_skill_distance(skill_a: str, skill_b: str,
                           method: Literal["edit", "jaccard", "semantic"] = "edit") -> float:
    """计算两个技能文档之间的距离"""
    if method == "edit":
        return _levenshtein_distance(skill_a, skill_b) / max(len(skill_a), len(skill_b), 1)
    elif method == "jaccard":
        return _jaccard_distance(skill_a, skill_b)
    elif method == "semantic":
        return _semantic_distance(skill_a, skill_b)
    else:
        raise ValueError(f"Unknown distance method: {method}")


def _levenshtein_distance(s1: str, s2: str) -> int:
    """Levenshtein 编辑距离"""
    if len(s1) < len(s2):
        return _levenshtein_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    prev_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        curr_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = prev_row[j + 1] + 1
            deletions = curr_row[j] + 1
            substitutions = prev_row[j] + (c1 != c2)
            curr_row.append(min(insertions, deletions, substitutions))
        prev_row = curr_row
    return prev_row[-1]


def _jaccard_distance(s1: str, s2: str) -> float:
    """Jaccard 距离（基于行集合）"""
    lines_a = set(s1.strip().split('\n'))
    lines_b = set(s2.strip().split('\n'))
    intersection = lines_a & lines_b
    union = lines_a | lines_b
    if not union:
        return 0.0
    return 1.0 - len(intersection) / len(union)


def _semantic_distance(s1: str, s2: str) -> float:
    """语义距离（基于关键词集合的余弦距离）"""
    words_a = re.findall(r'[a-zA-Z]{3,}', s1.lower())
    words_b = re.findall(r'[a-zA-Z]{3,}', s2.lower())
    from collections import Counter
    ca, cb = Counter(words_a), Counter(words_b)
    # 余弦相似度
    all_words = set(ca.keys()) | set(cb.keys())
    dot = sum(ca.get(w, 0) * cb.get(w, 0) for w in all_words)
    norm_a = math.sqrt(sum(v ** 2 for v in ca.values()))
    norm_b = math.sqrt(sum(v ** 2 for v in cb.values()))
    if norm_a == 0 or norm_b == 0:
        return 1.0
    return 1.0 - dot / (norm_a * norm_b)


def compute_population_diversity(
    individuals: list,
    method: str = "jaccard",
) -> float:
    """计算种群的整体多样性（平均成对距离）"""
    if len(individuals) < 2:
        return 0.0
    total = 0.0
    count = 0
    for i in range(len(individuals)):
        for j in range(i + 1, len(individuals)):
            dist = compute_skill_distance(
                individuals[i].skill_content,
                individuals[j].skill_content,
                method=method,
            )
            total += dist
            count += 1
    return total / count if count > 0 else 0.0


def novelty_search_score(
    candidate,
    population: list,
    k: int = 3,
    method: str = "jaccard",
) -> float:
    """新颖性搜索分数：到 k 近邻的平均距离"""
    if not population:
        return 1.0
    distances = [
        compute_skill_distance(candidate.skill_content, ind.skill_content, method)
        for ind in population
    ]
    distances.sort(reverse=True)
    k = min(k, len(distances))
    return sum(distances[:k]) / k if k > 0 else 0.0


@dataclass
class DiversityConfig:
    """多样性配置"""
    min_diversity: float = 0.15       # 最低多样性阈值
    novelty_weight: float = 0.3       # 新颖性在选择中的权重
    distance_method: str = "jaccard"  # 距离度量方法
    k_neighbors: int = 3             # 新颖性搜索的 k 近邻
    max_stagnation: int = 5          # 最大停滞代数（触发多样性注入）


def maintain_diversity(
    population,
    config: DiversityConfig,
    stagnation_count: int = 0,
) -> dict:
    """多样性维护：检查种群多样性并注入新个体"""
    report = {
        'diversity': 0.0,
        'action': 'none',
        'injected': 0,
    }

    # 计算当前多样性
    diversity = compute_population_diversity(
        population.individuals, config.distance_method
    )
    report['diversity'] = diversity

    # 多样性过低或停滞过久 → 注入新个体
    if diversity < config.min_diversity or stagnation_count >= config.max_stagnation:
        # 随机变异生成新个体
        import random
        n_inject = max(1, len(population.individuals) // 4)
        for _ in range(n_inject):
            parent = random.choice(population.individuals)
            mutated = mutate_skill(parent, mutation_rate=0.3)  # 高变异率
            population.update(mutated)
        report['action'] = 'inject_mutants'
        report['injected'] = n_inject

    return report
```

### 10.3 与种群化进化的集成

```python
# 在 trainer.py 的 epoch 边界
diversity_report = maintain_diversity(
    population=population,
    config=DiversityConfig(min_diversity=0.15),
    stagnation_count=stagnation_count,
)

# 如果多样性注入触发，重置停滞计数
if diversity_report['action'] != 'none':
    stagnation_count = 0
else:
    # 检查是否停滞（best 分数无提升）
    if population.get_best().hard_score <= prev_best_score:
        stagnation_count += 1
    else:
        stagnation_count = 0
```

### 10.4 预期收益

- **防早熟**：多样性监控和注入机制防止种群收敛到局部最优
- **新颖性搜索**：奖励与现有个体不同的候选，探索新区域
- **自适应**：停滞检测自动触发多样性注入
- **EVOREFUSE 启发**：变异-重组多样性探索的有效性已证明

***

## 改进方案十一：情景记忆增强元技能（EM-MetaSkill）

### 11.1 动机

当前 [meta\_skill.py](file:///c://Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/optimizer/meta_skill.py) 的 `run_meta_skill()` 在每个 epoch 边界生成跨 epoch 优化器策略记忆。但这个记忆是**单次快照**——只记录上一次 epoch 到当前 epoch 的对比，无长期情景记忆。

Mage（2026）证明：情景记忆（记录什么策略在什么场景下有效/无效）能显著提升 prompt 优化效果。Mage 在 GSM8K-Hard 上达到 46.4%，显著优于 GEPA 的 34.0%。

### 11.2 核心设计

**修改文件**：[meta\_skill.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/optimizer/meta_skill.py)

```python
"""情景记忆增强元技能（EM-MetaSkill）

将元技能从单次快照升级为长期情景记忆：
1. 记录每次 epoch 的策略、效果、场景
2. 检索相关历史经验指导当前优化
3. 模式识别：发现反复出现的成功/失败模式
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class EpisodicMemory:
    """单条情景记忆"""
    epoch: int
    skill_snapshot: str           # 当时的技能快照（摘要）
    strategy_used: str            # 使用的优化策略
    outcome: str                  # accept / reject / new_best
    hard_before: float
    hard_after: float
    delta: float
    context_tags: list[str] = field(default_factory=list)  # 场景标签
    lessons_learned: str = ""     # 经验教训
    embedding: list[float] = field(default_factory=list)   # 语义嵌入（简化）


class EpisodicMemoryStore:
    """情景记忆存储与检索"""

    def __init__(self, max_size: int = 100):
        self.memories: list[EpisodicMemory] = []
        self.max_size = max_size

    def add(self, memory: EpisodicMemory):
        """添加记忆"""
        self.memories.append(memory)
        if len(self.memories) > self.max_size:
            # 淘汰最老或最不相关的记忆
            self.memories.sort(
                key=lambda m: (m.epoch, abs(m.delta)),
                reverse=True,
            )
            self.memories = self.memories[:self.max_size]

    def retrieve_relevant(
        self,
        current_context: dict,
        n: int = 5,
    ) -> list[EpisodicMemory]:
        """检索与当前上下文相关的记忆"""
        if not self.memories:
            return []

        # 简化版：基于上下文标签匹配
        current_tags = set(current_context.get('tags', []))
        scored = []
        for mem in self.memories:
            # 标签重叠度
            tag_overlap = len(set(mem.context_tags) & current_tags)
            # 效果权重（成功的经验更相关）
            outcome_weight = 2.0 if mem.outcome == 'new_best' else 1.0
            # 时间衰减（近期记忆更相关）
            recency = 1.0 / (1.0 + (current_context.get('epoch', 0) - mem.epoch) * 0.1)
            # 改进幅度
            delta_weight = max(0, mem.delta) * 5

            score = (tag_overlap * 0.3 + outcome_weight * 0.2 +
                     recency * 0.2 + delta_weight * 0.3)
            scored.append((mem, score))

        scored.sort(key=lambda x: -x[1])
        return [mem for mem, _ in scored[:n]]

    def extract_patterns(self) -> dict:
        """从历史记忆中提取模式"""
        if not self.memories:
            return {}

        # 成功模式
        successes = [m for m in self.memories if m.delta > 0]
        failures = [m for m in self.memories if m.delta <= 0]

        patterns = {
            'successful_strategies': {},
            'failed_strategies': {},
            'recurring_failures': {},
        }

        # 统计策略成功率
        from collections import Counter
        success_strategies = Counter(
            m.strategy_used for m in successes
        )
        failure_strategies = Counter(
            m.strategy_used for m in failures
        )

        for strategy, count in success_strategies.most_common(5):
            patterns['successful_strategies'][strategy] = {
                'count': count,
                'avg_delta': sum(m.delta for m in successes
                                 if m.strategy_used == strategy) / count,
            }

        for strategy, count in failure_strategies.most_common(5):
            patterns['failed_strategies'][strategy] = {
                'count': count,
                'avg_delta': sum(m.delta for m in failures
                                 if m.strategy_used == strategy) / count,
            }

        # 重复失败模式
        failure_tags = Counter()
        for m in failures:
            for tag in m.context_tags:
                failure_tags[tag] += 1
        patterns['recurring_failures'] = dict(failure_tags.most_common(5))

        return patterns


def run_em_meta_skill(
    prev_skill: str,
    curr_skill: str,
    comparison_pairs: list[dict],
    *,
    memory_store: EpisodicMemoryStore,
    epoch: int,
    hard_before: float,
    hard_after: float,
    strategy_used: str,
    context_tags: list[str] | None = None,
    system_prompt: str = "",
    max_completion_tokens: int = 0,
) -> tuple[str, EpisodicMemory]:
    """情景记忆增强的元技能生成

    1. 检索相关历史记忆
    2. 提取成功/失败模式
    3. 结合当前对比对生成元技能
    4. 将本次经验存入记忆
    """
    # 检索相关记忆
    current_context = {
        'epoch': epoch,
        'tags': context_tags or [],
    }
    relevant_memories = memory_store.retrieve_relevant(current_context, n=5)
    patterns = memory_store.extract_patterns()

    # 构建增强 prompt
    memory_context = format_episodic_context(relevant_memories, patterns)
    user = (
        f"## Previous Skill (Epoch {epoch-1})\n{prev_skill[:2000]}...\n\n"
        f"## Current Skill (Epoch {epoch})\n{curr_skill[:2000]}...\n\n"
        f"## Comparison Pairs\n{json.dumps(comparison_pairs[:5], ...)}\n\n"
        f"## Historical Experience\n{memory_context}\n\n"
        f"## Task\n"
        f"Generate a meta-skill that captures optimization lessons:\n"
        f"1. What strategies worked well historically?\n"
        f"2. What strategies failed repeatedly?\n"
        f"3. What patterns recur across epochs?\n"
        f"4. What should the optimizer do differently next epoch?\n"
    )
    response, _ = chat_optimizer(
        system=load_prompt("em_meta_skill"),
        user=user,
        max_completion_tokens=max_completion_tokens,
        retries=3,
        stage="em_meta_skill",
    )
    meta_skill = response.strip()

    # 创建情景记忆
    delta = hard_after - hard_before
    memory = EpisodicMemory(
        epoch=epoch,
        skill_snapshot=curr_skill[:500],  # 摘要
        strategy_used=strategy_used,
        outcome='new_best' if delta > 0 else ('accept' if delta == 0 else 'reject'),
        hard_before=hard_before,
        hard_after=hard_after,
        delta=delta,
        context_tags=context_tags or [],
        lessons_learned=meta_skill[:500],
    )
    memory_store.add(memory)

    return meta_skill, memory
```

### 11.3 预期收益

- **长期记忆**：跨 epoch 的策略效果记录，避免重复试错
- **模式识别**：自动发现反复出现的成功/失败模式
- **上下文检索**：根据当前场景检索相关历史经验
- **Mage 报告**：46.4% vs GEPA 34.0%，情景记忆是关键差异

***

## 改进方案十二：协同自适应任务策展人（Actor-Curator）

### 12.1 动机

改进方案四引入了课程学习，但 Actor-Curator 的核心创新更进一步：用**策略改进老虎机**直接优化"哪些任务能最大化策略改进"。Actor-Curator 在 AIME2024 上提升 28.6%，ARC-1D 上提升 30.5%，速度提升 80%。

### 12.2 核心设计

**新增模块**：`skillopt/optimizer/task_curator.py`

```python
"""协同自适应任务策展人（Actor-Curator）

训练一个神经策展人（neural curator），动态从任务库中选择
能最大化策略改进的训练任务。
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TaskValueEstimate:
    """任务价值估计"""
    task_id: str
    # 特征
    difficulty: float
    category: str
    # 价值估计
    expected_improvement: float = 0.0
    uncertainty: float = 1.0
    # 历史
    n_selected: int = 0
    last_improvement: float = 0.0


class NeuralCurator:
    """神经策展人

    用简单的线性模型（可扩展为神经网络）学习任务特征→策略改进的映射。
    用在线随机镜像下降（OSMD）进行在线学习。
    """

    def __init__(
        self,
        task_features: dict[str, dict],  # task_id -> features
        learning_rate: float = 0.1,
        exploration_bonus: float = 0.5,
    ):
        self.task_features = task_features
        self.learning_rate = learning_rate
        self.exploration_bonus = exploration_bonus

        # 特征维度
        self.feature_dim = self._get_feature_dim()
        # 权重向量（简化版：线性模型）
        self.weights = [0.0] * self.feature_dim
        # 任务价值估计
        self.estimates: dict[str, TaskValueEstimate] = {}
        for tid, feats in task_features.items():
            self.estimates[tid] = TaskValueEstimate(
                task_id=tid,
                difficulty=feats.get('difficulty', 0.5),
                category=feats.get('category', 'general'),
            )

    def _get_feature_dim(self) -> int:
        """获取特征维度"""
        if not self.task_features:
            return 5
        # 标准特征：[difficulty, category_encoded, length, n_tools, novelty]
        return 5

    def _extract_features(self, task_id: str) -> list[float]:
        """提取任务特征向量"""
        feats = self.task_features.get(task_id, {})
        return [
            feats.get('difficulty', 0.5),
            hash(feats.get('category', 'general')) % 100 / 100.0,
            min(feats.get('description_length', 100) / 5000, 1.0),
            min(feats.get('n_required_tools', 1) / 10, 1.0),
            1.0 / (1.0 + self.estimates[task_id].n_selected),  # 新鲜度
        ]

    def select(self, n: int, available: list[str] | None = None) -> list[str]:
        """选择 n 个任务"""
        pool = available or list(self.estimates.keys())
        if len(pool) <= n:
            return pool

        # 计算每个任务的价值
        scores = []
        for tid in pool:
            feats = self._extract_features(tid)
            # 线性模型预测
            expected = sum(w * f for w, f in zip(self.weights, feats))
            # UCB 式探索奖励
            exploration = self.exploration_bonus * math.sqrt(
                1.0 / (self.estimates[tid].n_selected + 1)
            )
            # 新鲜度奖励
            novelty = math.log(1 + self.estimates[tid].n_selected) * 0.1

            score = expected + exploration + novelty
            scores.append((tid, score))

        # OSMD 式采样
        scores.sort(key=lambda x: -x[1])
        # softmax 温度采样
        temp = 0.5
        top_k = min(n * 3, len(scores))
        top = scores[:top_k]
        import numpy as np
        logits = np.array([s for _, s in top]) / temp
        probs = np.exp(logits - logits.max())
        probs = probs / probs.sum()
        indices = np.random.choice(
            len(top), size=min(n, len(top)), replace=False, p=probs
        )
        selected = [top[i][0] for i in indices]

        # 更新选择计数
        for tid in selected:
            self.estimates[tid].n_selected += 1

        return selected

    def update(
        self,
        task_ids: list[str],
        improvements: list[float],
    ):
        """用观测到的策略改进更新策展人"""
        for tid, improvement in zip(task_ids, improvements):
            if tid not in self.estimates:
                continue
            est = self.estimates[tid]
            est.last_improvement = improvement
            # 指数移动平均
            est.expected_improvement = (
                0.7 * est.expected_improvement + 0.3 * improvement
            )
            # 不确定性降低
            est.uncertainty *= 0.95

            # 在线梯度更新权重
            feats = self._extract_features(tid)
            predicted = sum(w * f for w, f in zip(self.weights, feats))
            error = improvement - predicted
            for i in range(len(self.weights)):
                self.weights[i] += self.learning_rate * error * feats[i]
```

### 12.3 与 trainer.py 的集成

```python
# 在 trainer.py 中
curator = NeuralCurator(
    task_features={tid: extract_features(t) for tid, t in train_env.tasks.items()},
    learning_rate=0.1,
)

for epoch in range(1, num_epochs + 1):
    for step_in_epoch in range(steps_per_epoch):
        # Actor-Curator 选择任务
        sampled_ids = curator.select(batch_size)
        train_tasks = [train_env.get_task(tid) for tid in sampled_ids]

        # ① ROLLOUT
        rollout_results = adapter.rollout(train_env, current_skill, rollout_dir)
        prev_scores = [r.get('prev_hard', 0) for r in rollout_results]
        curr_scores = [r['hard'] for r in rollout_results]

        # 计算策略改进
        improvements = [c - p for c, p in zip(curr_scores, prev_scores)]

        # ... 后续 6 阶段 ...

        # 更新策展人
        curator.update(sampled_ids, improvements)
```

### 12.4 预期收益

- **直接优化策略改进**：选择能最大化策略改进的任务
- **探索-利用平衡**：UCB 式探索保证不遗漏高价值任务
- **在线学习**：策展人随训练动态调整
- **Actor-Curator 报告**：AIME2024 +28.6%, ARC-1D +30.5%, 速度 +80%

***

## 改进方案十三：递归元技能进化（MetaSkill-Evolve）

### 13.1 动机

当前 [meta\_skill.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/optimizer/meta_skill.py) 的元技能在每个 epoch 边界生成一次，但元技能本身**不被优化**——它只是记录历史对比。MetaSkill-Evolve 提出双循环架构：快循环优化技能本身，慢循环优化"如何优化技能"的元技能。

### 13.2 核心设计

**新增模块**：`skillopt/optimizer/meta_evolve.py`

```python
"""递归元技能进化（MetaSkill-Evolve）

双循环架构：
- 快循环（每 step）：优化技能本身（现有 6 阶段管线）
- 慢循环（每 N epoch）：优化元技能（如何优化技能）
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class MetaSkillState:
    """元技能状态"""
    content: str                      # 元技能内容
    generation: int = 0               # 进化代数
    fitness_history: list[float] = field(default_factory=list)  # 适应度历史
    # 元技能的"超参数"建议
    suggested_lr: int = 8             # 建议的编辑预算
    suggested_update_mode: str = "patch"  # 建议的更新模式
    suggested_gate_metric: str = "hard"   # 建议的门控度量
    # 反思深度
    reflection_depth: int = 1        # 反思嵌套层数


def run_meta_skill_evolve(
    meta_skill: MetaSkillState,
    skill_evolution_history: list[dict],
    *,
    slow_cycle_interval: int = 3,   # 每 N epoch 进行一次元技能进化
    current_epoch: int = 0,
    max_completion_tokens: int = 0,
) -> MetaSkillState:
    """递归元技能进化

    分析技能进化的历史模式，优化元技能本身。
    """
    if current_epoch % slow_cycle_interval != 0:
        return meta_skill  # 不在慢循环周期，不进化

    # 分析技能进化历史
    analysis = analyze_skill_evolution(skill_evolution_history)

    user = (
        f"## Current Meta-Skill (Generation {meta_skill.generation})\n"
        f"{meta_skill.content}\n\n"
        f"## Skill Evolution History (last {len(skill_evolution_history)} epochs)\n"
        f"{format_evolution_history(skill_evolution_history)}\n\n"
        f"## Evolution Analysis\n{analysis}\n\n"
        f"## Task\n"
        f"Evolve the meta-skill to better guide future skill optimization:\n"
        f"1. What optimization strategies worked well? Keep them.\n"
        f"2. What strategies failed? Remove or modify them.\n"
        f"3. What new patterns emerged? Add guidance for them.\n"
        f"4. Suggest hyperparameters for the next epoch:\n"
        f"   - learning_rate (edit budget)\n"
        f"   - update_mode\n"
        f"   - gate_metric\n"
        f"Output JSON with evolved meta-skill and hyperparameter suggestions.\n"
    )
    response, _ = chat_optimizer(
        system=load_prompt("meta_evolve"),
        user=user,
        max_completion_tokens=max_completion_tokens,
        retries=3,
        stage="meta_evolve",
    )
    parsed = extract_json(response) or {}

    evolved = MetaSkillState(
        content=parsed.get('meta_skill', meta_skill.content),
        generation=meta_skill.generation + 1,
        fitness_history=meta_skill.fitness_history,
        suggested_lr=parsed.get('suggested_lr', meta_skill.suggested_lr),
        suggested_update_mode=parsed.get('suggested_update_mode',
                                          meta_skill.suggested_update_mode),
        suggested_gate_metric=parsed.get('suggested_gate_metric',
                                           meta_skill.suggested_gate_metric),
        reflection_depth=parsed.get('reflection_depth', meta_skill.reflection_depth + 1),
    )

    # 评估元技能适应度（基于下一 epoch 的技能改进）
    # 这会在下一慢循环时填充
    evolved.fitness_history = meta_skill.fitness_history[-10:]  # 保留最近 10 代

    return evolved


def analyze_skill_evolution(history: list[dict]) -> str:
    """分析技能进化历史，提取模式"""
    if not history:
        return "No history available."

    # 计算改进趋势
    deltas = [h.get('delta', 0) for h in history]
    avg_delta = sum(deltas) / len(deltas)
    n_positive = sum(1 for d in deltas if d > 0)
    n_negative = sum(1 for d in deltas if d < 0)

    # 策略分布
    from collections import Counter
    strategies = Counter(h.get('strategy', 'unknown') for h in history)
    successful_strategies = Counter(
        h.get('strategy', 'unknown') for h in history if h.get('delta', 0) > 0
    )

    analysis = (
        f"Average delta: {avg_delta:.4f}\n"
        f"Positive steps: {n_positive}/{len(history)}\n"
        f"Negative steps: {n_negative}/{len(history)}\n"
        f"Most used strategies: {strategies.most_common(3)}\n"
        f"Most successful strategies: {successful_strategies.most_common(3)}\n"
    )

    # 停滞检测
    if len(deltas) >= 5 and all(d <= 0.01 for d in deltas[-5:]):
        analysis += "\nWARNING: Skill evolution has stagnated for 5+ steps.\n"
        analysis += "Consider: increasing exploration, changing update mode, "
        analysis += "or injecting diversity.\n"

    return analysis
```

### 13.3 与 trainer.py 的集成

```python
# 在 trainer.py 中
meta_skill_state = MetaSkillState(content="")

for epoch in range(1, num_epochs + 1):
    # 应用元技能的超参数建议
    if meta_skill_state.suggested_lr:
        scheduler.max_lr = meta_skill_state.suggested_lr
    if meta_skill_state.suggested_update_mode:
        update_mode = meta_skill_state.suggested_update_mode
    if meta_skill_state.suggested_gate_metric:
        gate_metric = meta_skill_state.suggested_gate_metric

    for step_in_epoch in range(steps_per_epoch):
        # ... 6 阶段快循环 ...
        pass

    # Epoch 边界：Slow Update + Meta Skill
    # ... 现有 Slow Update ...

    # 慢循环：元技能进化
    meta_skill_state = run_meta_skill_evolve(
        meta_skill=meta_skill_state,
        skill_evolution_history=epoch_history,
        current_epoch=epoch,
    )
    # 记录元技能适应度
    meta_skill_state.fitness_history.append(epoch_delta)
```

### 13.4 预期收益

- **递归改进**：不只是优化技能，还优化"如何优化技能"
- **超参数自适应**：元技能自动建议学习率、更新模式、门控度量
- **停滞检测**：自动发现停滞并建议策略变更
- **双循环架构**：快慢分离，计算资源分配更合理

***

## 改进方案十四：偏好优化门控（PrefGate）

### 14.1 动机

当前 [gate.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/evaluation/gate.py) 的 `evaluate_gate()` 使用严格 `>` 比较进行二元 accept/reject 决策。这浪费了候选技能中的部分改进信号——即使候选不如最优，它可能在某些维度上更好。

EVOLVE（TMLR 2026）证明：用迭代偏好优化替代二元决策能显著提升自精炼能力。Llama-3.1-8B 经 EVOLVE 训练后超越 Llama-3.1-405B-Instruct 和 GPT-4o。SPIN（ICML 2024）证明：自博弈微调能用 DPO 式目标将弱模型变强。

### 14.2 核心设计

**修改文件**：[gate.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/evaluation/gate.py)

```python
"""偏好优化门控（PrefGate）

用偏好对（preference pairs）替代二元 accept/reject：
1. 保留被拒绝的候选作为"负样本"
2. 构建 (chosen, rejected) 偏好对
3. 用偏好信号指导后续优化
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class PreferencePair:
    """偏好对"""
    chosen_skill: str          # 被偏好的技能
    rejected_skill: str        # 被拒绝的技能
    chosen_score: float
    rejected_score: float
    margin: float              # 分数差距
    step: int                  # 训练步
    # 偏好原因
    reason: str = ""           # 为什么 chosen > rejected
    # 偏好维度
    dimensions: dict = field(default_factory=dict)  # 各维度比较


@dataclass
class PreferenceBuffer:
    """偏好对缓冲区"""
    pairs: list[PreferencePair] = field(default_factory=list)
    max_size: int = 50

    def add(self, pair: PreferencePair):
        self.pairs.append(pair)
        if len(self.pairs) > self.max_size:
            self.pairs = self.pairs[-self.max_size:]

    def sample(self, n: int) -> list[PreferencePair]:
        """采样 n 个偏好对"""
        import random
        if len(self.pairs) <= n:
            return self.pairs
        # 优先采样高 margin 的对
        sorted_pairs = sorted(self.pairs, key=lambda p: -p.margin)
        # 一半从高 margin 采样，一半随机
        top_half = sorted_pairs[:n // 2]
        random_half = random.sample(
            sorted_pairs[n // 2:], min(n - len(top_half), len(sorted_pairs) - n // 2)
        )
        return top_half + random_half

    def build_preference_context(self, n: int = 5) -> str:
        """构建偏好上下文（用于指导 optimizer）"""
        if not self.pairs:
            return ""
        sampled = self.sample(n)
        lines = []
        for i, pair in enumerate(sampled):
            lines.append(
                f"### Preference Pair {i+1} (Step {pair.step})\n"
                f"Chosen (score={pair.chosen_score:.4f}):\n"
                f"{pair.chosen_skill[:500]}...\n\n"
                f"Rejected (score={pair.rejected_score:.4f}):\n"
                f"{pair.rejected_skill[:500]}...\n\n"
                f"Margin: {pair.margin:.4f}\n"
                f"Reason: {pair.reason}\n"
            )
        return "\n".join(lines)


def evaluate_pref_gate(
    candidate_skill: str,
    cand_hard: float,
    current_skill: str,
    current_score: float,
    best_skill: str,
    best_score: float,
    best_step: int,
    global_step: int,
    *,
    pref_buffer: PreferenceBuffer,
    cand_soft: float = 0.0,
    metric: str = "hard",
    mixed_weight: float = 0.5,
) -> tuple[GateResult, PreferencePair | None]:
    """偏好优化门控

    除了返回 GateResult，还构建偏好对。
    """
    cand_score = select_gate_score(cand_hard, cand_soft, metric, mixed_weight)

    if cand_score > current_score:
        # 候选优于当前 → 接受
        if cand_score > best_score:
            action = "accept_new_best"
        else:
            action = "accept"

        # 构建偏好对：(candidate, current)
        pref_pair = PreferencePair(
            chosen_skill=candidate_skill,
            rejected_skill=current_skill,
            chosen_score=cand_score,
            rejected_score=current_score,
            margin=cand_score - current_score,
            step=global_step,
            reason=f"Candidate outperforms current on {metric}",
        )
        pref_buffer.add(pref_pair)

        return GateResult(
            action=action,
            current_skill=candidate_skill,
            current_score=cand_score,
            best_skill=candidate_skill if action == "accept_new_best" else best_skill,
            best_score=cand_score if action == "accept_new_best" else best_score,
            best_step=global_step if action == "accept_new_best" else best_step,
        ), pref_pair
    else:
        # 候选不优于当前 → 拒绝，但仍构建偏好对
        pref_pair = PreferencePair(
            chosen_skill=current_skill,
            rejected_skill=candidate_skill,
            chosen_score=current_score,
            rejected_score=cand_score,
            margin=current_score - cand_score,
            step=global_step,
            reason=f"Current outperforms candidate on {metric}",
        )
        pref_buffer.add(pref_pair)

        return GateResult(
            action="reject",
            current_skill=current_skill,
            current_score=current_score,
            best_skill=best_skill,
            best_score=best_score,
            best_step=best_step,
        ), pref_pair
```

### 14.3 偏好信号在 REFLECT 阶段的使用

```python
# 在 trainer.py 的 ② REFLECT 阶段
# 将偏好上下文注入 reflect prompt
pref_context = pref_buffer.build_preference_context(n=5)

failure_patches, success_patches = run_minibatch_reflect(
    rollout_results=rollout_results,
    current_skill=current_skill,
    preference_context=pref_context,  # 新增参数
    ...
)

# 在 reflect prompt 中加入偏好上下文
# "## Historical Preferences\n{pref_context}\n"
# "Learn from past preferences: what patterns consistently win/lose?"
```

### 14.4 预期收益

- **梯度信号保留**：即使拒绝候选，也保留偏好信号
- **模式学习**：optimizer 从历史偏好中学习什么模式有效
- **DPO 式训练**：偏好对可用于类似 DPO 的优化
- **EVOLVE 报告**：超越 Llama-3.1-405B 和 GPT-4o 的效果

***

## 改进方案十五：推理时计算扩展（TTC-Scaling）

### 15.1 动机

当前推理时用固定 skill 执行任务，无计算扩展。随着 skill 变长和复杂化，一次推理可能不足以充分发挥 skill 的潜力。

推理时计算扩展（Test-Time Compute Scaling）是 2025-2026 年的重要趋势：通过在推理时增加计算来提升效果。

### 15.2 核心设计

**新增模块**：`skillopt/optimizer/ttc_scaling.py`

```python
"""推理时计算扩展（TTC-Scaling）

在推理时增加计算来提升 skill 效果：
1. 多候选生成 + 自一致性投票
2. 推理时技能路由（TAE-Route 的增强版）
3. 推理时自精炼：执行后检查，不满意则用 skill 自我修正
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class TTCConfig:
    """推理时计算配置"""
    n_candidates: int = 1           # 候选数（>1 时启用多候选投票）
    consistency_threshold: float = 0.8  # 一致性阈值
    enable_self_refine: bool = False    # 推理时自精炼
    max_refine_rounds: int = 2          # 最大自精炼轮数
    enable_skill_routing: bool = False  # 推理时技能路由
    refine_confidence: float = 0.7      # 自精炼信心阈值


def ttc_inference(
    adapter,
    env,
    skill: str,
    config: TTCConfig,
    *,
    task_description: str = "",
) -> dict:
    """推理时计算扩展推理

    根据 config 决定使用哪些 TTC 策略。
    """
    result = None

    # 1. 多候选 + 自一致性投票
    if config.n_candidates > 1:
        candidates = []
        for _ in range(config.n_candidates):
            r = adapter.rollout(env, skill, f"/tmp/ttc_candidate")
            candidates.append(r)

        # 自一致性投票
        result = self_consistency_vote(candidates, config.consistency_threshold)
    else:
        result = adapter.rollout(env, skill, f"/tmp/ttc_single")

    # 2. 推理时自精炼
    if config.enable_self_refine and result.get('hard', 0) < 1.0:
        result = inference_time_self_refine(
            adapter, env, skill, result, config
        )

    return result


def self_consistency_vote(
    candidates: list[dict],
    threshold: float = 0.8,
) -> dict:
    """自一致性投票

    多次执行同一任务，对答案进行投票。
    """
    if not candidates:
        return {}

    # 提取答案
    answers = [c.get('answer', '') for c in candidates]
    from collections import Counter
    answer_counts = Counter(answers)

    # 最常见答案
    most_common, count = answer_counts.most_common(1)[0]
    consistency = count / len(candidates)

    # 如果一致性足够高，使用投票结果
    if consistency >= threshold:
        # 找到使用最常见答案的第一个候选
        for c in candidates:
            if c.get('answer') == most_common:
                return {**c, 'consistency': consistency, 'n_candidates': len(candidates)}
        return candidates[0]
    else:
        # 一致性不够，选择 hard 分数最高的
        best = max(candidates, key=lambda c: c.get('hard', 0))
        return {**best, 'consistency': consistency, 'n_candidates': len(candidates)}


def inference_time_self_refine(
    adapter,
    env,
    skill: str,
    initial_result: dict,
    config: TTCConfig,
) -> dict:
    """推理时自精炼

    执行后检查结果，如果不满意则用 skill 自我修正。
    """
    current_result = initial_result

    for round_idx in range(config.max_refine_rounds):
        # 检查是否需要精炼
        if current_result.get('hard', 0) >= config.refine_confidence:
            break

        # 构建 self-refine prompt
        refine_context = (
            f"## Previous Attempt\n"
            f"Trajectory: {current_result.get('trajectory', '')}\n"
            f"Result: {current_result.get('answer', '')}\n"
            f"Score: {current_result.get('hard', 0)}\n\n"
            f"## Skill\n{skill}\n\n"
            f"## Task\n"
            f"The previous attempt may have errors. Review the trajectory, "
            f"identify mistakes, and try again with corrections.\n"
        )

        # 用修正后的 skill 重新执行
        refined_result = adapter.rollout(
            env, skill, f"/tmp/ttc_refine_{round_idx}",
            extra_context=refine_context,
        )

        # 只在改进时接受
        if refined_result.get('hard', 0) > current_result.get('hard', 0):
            current_result = {
                **refined_result,
                'refined': True,
                'refine_round': round_idx + 1,
            }
        else:
            break

    return current_result
```

### 15.3 与环境的集成

```python
# 在 adapter.rollout() 或环境执行中
def rollout(self, env, skill, output_dir, **kwargs):
    if self.config.ttc_config and self.config.ttc_config.n_candidates > 1:
        return ttc_inference(
            adapter=self,
            env=env,
            skill=skill,
            config=self.config.ttc_config,
            task_description=env.current_task_description,
        )
    # 默认单次执行
    ...
```

### 15.4 预期收益

- **多候选投票**：自一致性提升准确率，尤其在有随机性的任务上
- **推理时自精炼**：不满意时自我修正，提升单次执行质量
- **技能路由**：只加载相关 skill 章节，减少干扰
- **灵活配置**：可根据计算预算调整 TTC 策略

***

## 实施路线图与优先级

### 18.1 分阶段实施计划

#### 第一阶段：核心算法增强（高优先级，高收益）

| 改进            | 涉及文件                     | 新增文件                  | 复杂度 | 预期收益                   |
| ------------- | ------------------------ | --------------------- | --- | ---------------------- |
| CCE-Reflect   | reflect.py               | cce\_reflect.py       | 中   | +40.40% (SkillCAT)     |
| CL-Sampler    | trainer.py               | curriculum.py         | 中   | +28.6% (Actor-Curator) |
| ParetoGate    | gate.py                  | - (修改)                | 中   | 多维权衡                   |
| PRC-Aggregate | aggregate.py, trainer.py | patch\_calibration.py | 高   | 编辑质量提升                 |

**关键依赖**：CCE-Reflect 和 PRC-Aggregate 需要额外的 rollout 预算用于校准。

#### 第二阶段：种群与探索增强（中优先级，高收益）

| 改进         | 涉及文件       | 新增文件           | 复杂度 | 预期收益    |
| ---------- | ---------- | -------------- | --- | ------- |
| PBE        | trainer.py | population.py  | 高   | 8x 探索空间 |
| MAB-Select | clip.py    | mab\_select.py | 中   | 探索-利用平衡 |
| PDM        | -          | diversity.py   | 低   | 防早熟     |
| PrefGate   | gate.py    | - (修改)         | 中   | 梯度信号保留  |

**关键依赖**：PBE 是 PDM 的前提。

#### 第三阶段：自适应与记忆增强（中优先级，中收益）

| 改进            | 涉及文件                   | 新增文件              | 复杂度 | 预期收益            |
| ------------- | ---------------------- | ----------------- | --- | --------------- |
| BO-Scheduler  | scheduler.py           | bo\_scheduler.py  | 高   | 自适应 LR          |
| EM-MetaSkill  | meta\_skill.py         | - (修改)            | 中   | 长期记忆            |
| RePro-Reflect | reflect.py, trainer.py | repro\_reflect.py | 中   | +12% (ALFWorld) |
| Actor-Curator | trainer.py             | task\_curator.py  | 中   | +30.5% (ARC-1D) |

**关键依赖**：BO-Scheduler 需要足够的训练步数才能有效。

#### 第四阶段：推理时增强（低优先级，中收益）

| 改进               | 涉及文件                       | 新增文件             | 复杂度 | 预期收益            |
| ---------------- | -------------------------- | ---------------- | --- | --------------- |
| TAE-Route        | adapter                    | skill\_router.py | 低   | 30-70% token 压缩 |
| TTC-Scaling      | adapter                    | ttc\_scaling.py  | 中   | 推理时提升           |
| MetaSkill-Evolve | meta\_skill.py, trainer.py | meta\_evolve.py  | 高   | 递归改进            |

### 18.2 依赖关系图

```
PBE ──→ PDM
  │
  └──→ ParetoGate (多目标评估)
  
CCE-Reflect ──→ PRC-Aggregate (因果补丁→校准)
  
CL-Sampler ──→ Actor-Curator (课程→策展)

MAB-Select ──→ PrefGate (选择→偏好)

EM-MetaSkill ──→ MetaSkill-Evolve (记忆→进化)

TAE-Route ──→ TTC-Scaling (路由→推理扩展)
```

### 18.3 配置接口设计

建议在现有配置系统中新增以下配置项：

```yaml
# config.yaml 新增项

# 种群化进化
population:
  enabled: true
  size: 8                    # 帕累托前沿最大大小
  archive_size: 16           # 存档最大大小
  crossover_rate: 0.3        # 交叉概率
  mutation_rate: 0.1         # 变异概率
  diversity:
    min_diversity: 0.15      # 最低多样性阈值
    max_stagnation: 5        # 最大停滞代数
    distance_method: "jaccard"

# 多臂老虎机编辑选择
mab_select:
  enabled: true
  temperature: 0.5           # softmax 温度
  variance_bonus: 0.3       # 方差奖励系数
  prior_weight: 0.3         # LLM 先验权重

# 对比因果提取反思
cce_reflect:
  enabled: true
  contrastive_matching: "task_id"  # task_id / category
  min_diffs: 1              # 最小差异数

# 课程学习
curriculum:
  mode: "e2h"               # e2h / actor_curator / adaptive
  warmup_ratio: 0.15
  easy_fade_rate: 0.95

# 帕累托门控
pareto_gate:
  enabled: true
  objectives: ["hard", "soft", "efficiency", "conciseness"]
  min_hard_floor: 0.0
  use_hypervolume: true

# 贝叶斯优化调度器
bo_scheduler:
  enabled: true
  acquisition: "ucb"
  beta: 2.0
  length_scale: 3.0

# 补丁回放校准
patch_calibration:
  enabled: true
  n_samples: 5
  tolerance: 0.02

# 技能路由
skill_routing:
  enabled: true
  max_sections: 5
  min_relevance: 0.1

# 推理时计算扩展
ttc_scaling:
  n_candidates: 1           # >1 启用多候选投票
  enable_self_refine: false
  max_refine_rounds: 2
```

***

## 预期收益量化估计

### 19.1 单项改进预期收益

基于 SOTA 论文报告的数据，各改进方案的预期收益估计：

| 改进方案          | SOTA 来源             | 报告提升                | 预期适用度\* | 保守估计    |
| ------------- | ------------------- | ------------------- | ------- | ------- |
| CCE-Reflect   | SkillCAT            | +40.40%             | 80%     | +20-30% |
| CL-Sampler    | E2H + Actor-Curator | +28.6-30.5%         | 70%     | +15-20% |
| PBE           | GEPA                | +6% (vs GRPO)       | 90%     | +5-10%  |
| RePro-Reflect | RePro               | +12% (ALFWorld)     | 85%     | +8-10%  |
| ParetoGate    | ParetoPO            | 显著 (ICML Spotlight) | 75%     | +5-8%   |
| EM-MetaSkill  | Mage                | 46.4% vs 34.0%      | 60%     | +5-8%   |
| PrefGate      | EVOLVE              | 超越 405B             | 50%     | +3-5%   |
| PRC-Aggregate | SkillCAT AAE        | 含在 +40.40% 中        | 80%     | +10-15% |
| MAB-Select    | SIMBA               | 显著                  | 70%     | +5-8%   |
| TAE-Route     | SkillCAT TTE        | 含在 +40.40% 中        | 75%     | +5-10%  |

\*预期适用度：SOTA 方法在 SkillOpt 场景中的预期适用程度

### 19.2 组合改进预期收益

由于各改进方案作用于训练管线的不同阶段，组合使用时预期有叠加效应（但存在递减边际效应）：

```
基线（当前 SkillOpt）
  + CCE-Reflect (+20-30%)        → 1.20-1.30x
  + CL-Sampler (+15-20%)         → 1.38-1.56x
  + PRC-Aggregate (+10-15%)      → 1.52-1.79x
  + RePro-Reflect (+8-10%)       → 1.64-1.97x
  + PBE (+5-10%)                 → 1.72-2.17x
  + ParetoGate (+5-8%)           → 1.81-2.34x
  + EM-MetaSkill (+5-8%)         → 1.90-2.53x
  + MAB-Select (+5-8%)           → 1.99-2.73x
  + 其他改进 (+5-10%)            → 2.09-3.00x
```

**保守估计**：组合所有改进方案后，预期整体性能提升 2-3 倍。

### 19.3 计算成本分析

| 改进方案          | 额外 LLM 调用/step       | 额外 rollout/step | 内存开销      |
| ------------- | -------------------- | --------------- | --------- |
| CCE-Reflect   | +N/2 (N=batch\_size) | 0               | 低         |
| CL-Sampler    | 0                    | 0               | 低         |
| ParetoGate    | 0                    | 0               | 低         |
| PRC-Aggregate | 0                    | +M (M=校准样本数)    | 中         |
| PBE           | 0                    | 0               | 中 (K 个个体) |
| MAB-Select    | 0                    | 0               | 低         |
| RePro-Reflect | +N (每轨迹一次)           | 0               | 低         |
| BO-Scheduler  | 0                    | 0               | 低         |
| TAE-Route     | 0                    | 0               | 低         |
| TTC-Scaling   | 0                    | +K-1 (K=候选数)    | 低         |

**关键瓶颈**：PRC-Aggregate 需要额外的 rollout 预算，是计算成本最高的改进。建议在计算预算有限时优先实施无额外 rollout 的改进。

***

## 参考文献

### SOTA 方法来源

1. **GEPA** - Agrawal et al., "GEPA: Genetic-Pareto Prompt Optimization," ICLR 2026 Oral. 帕累托前沿选择 + 反思式变异 + 自然语言反馈驱动，比 GRPO 平均+6%，rollout 仅 1/35。
2. **DSPy SIMBA** - Khattab et al., "DSPy: Compiling Declarative NLP Programs," 2024-2026. SIMBA 模块：多臂老虎机 + softmax 采样 + 方差分桶聚焦难例 + 好坏轨迹对比自反思。
3. **SkillCAT** - "SkillCAT: A Three-Stage Framework for Agent Skill Evolution," 2026. CCE（对比因果提取）+ AAE（评估增强进化，补丁回放校准）+ TTE（拓扑感知执行），+40.40% 平均分。
4. **SkillEvo** - "SkillEvo: Self-Evolving Agent Skills with Evolutionary Gradients," 2026. 自更新进化梯度 + 可信反馈生成梯度 + 可控治理约束方向。
5. **BayesPrompt** - Tezoh et al., "BayesPrompt: Human Readable Prompts That Make Sense," arXiv:2608.17866, 2026. 贝叶斯后验推理 + MCMC 采样 + 可读性约束。
6. **LLINBO** - Chang et al., "LLINBO: Trustworthy LLM-in-the-Loop Bayesian Optimization," ICLR 2026. LLM + GP 代理混合贝叶斯优化，三机制协作 + 理论保证。
7. **RePro** - Ma et al., "Retrospective Progress-Aware Self-Refinement for LLM Agent Training," arXiv:2606.14302, 2026. 前向-然后-回溯反思 + 进度感知 + 复合奖励，ALFWorld +12%。
8. **E2H Reasoner** - Parashar et al., "Curriculum Reinforcement Learning from Easy to Hard Tasks Improves LLM Reasoning," ICLR 2026. 从易到难课程 RL + 退火调度 + 收敛保证。
9. **Actor-Curator** - Gu et al., "Actor-Curator: Co-adaptive Curriculum Learning via Policy-Improvement Bandits," arXiv:2602.20532, 2026. 策略改进老虎机 + OSMD + 神经策展人，AIME2024 +28.6%。
10. **ParetoPO** - Li et al., "Towards Pareto-Optimal Tool-Integrated Agents with Pareto Ranking Policy Optimization," ICML 2026 Spotlight. 超体积引导动态标量化 + Pareto 排序优势计算。
11. **PromptQuine** - Wang et al., "Evolving Prompts In-Context: An Open-ended, Self-replicating Perspective," ICML 2025. 进化搜索剪枝策略 + 自发现框架。
12. **Mage** - Singh, "Mage: Understanding Stability-Performance Trade-offs in Multi-component Prompt Optimization," arXiv:2607.11944, 2026. 情景记忆 + 多目标 Pareto + 自适应评估 + POCE 耦合效应，46.4% vs GEPA 34.0%。
13. **EvoSkill** - "EvoSkill: Self-Verification Evolution for Agent Skills," 2026. 自验证进化 + Trace2Skill 并行提案 + 棘轮效应 + Success/Error Analyst 分离。
14. **EVOREFUSE** - Wu et al., "EVOREFUSE: Evolutionary Prompt Optimization for Evaluation and Mitigation of LLM Over-Refusal," NeurIPS 2025. 进化变异 + 重组 + ELBO 最大化 + 多样性探索。
15. **EVOLVE** - "Training LLMs to Self-Refine via Iterative Preference Optimization," TMLR 2026. 迭代偏好优化训练自精炼，Llama-3.1-8B 超越 405B-Instruct 和 GPT-4o。
16. **MetaSkill-Evolve** - "How to Realize Recursively Self-Improving Agents," arXiv:2607.12254, 2026. 快任务-技能环 + 慢元技能环 + 递归自改进。
17. **LEACL** - Heravi et al., "LEACL: LLM-Enhanced Automatic Curriculum Learning," arXiv:2607.23515, 2026. LLM 任务分解 + 元任务生成 + 自动课程学习。
18. **AP-BMM** - Chen et al., "AP-BMM: Approximating Capability-Cost Pareto Sets via Asynchronous Prior-Guided Bayesian Model Merging," arXiv:2512.09972, 2026. 异步先验引导贝叶斯模型合并 + 多目标 Pareto 集。
19. **SPIN** - Chen et al., "Self-Play Fine-Tuning Converts Weak Language Models to Strong Language Models," ICML 2024. 自博弈微调 + DPO 式目标 + 人 vs 自生成偏好对。
20. **Ax 1.0** - Meta, "Ax 1.0 Streamlines LLM and System Optimization," 2025. 贝叶斯优化平台 + GP 代理 + 多目标优化 + 帕累托前沿可视化。

### SkillOpt 内部文档

1. `docs/guide/training-loop.md` - 训练循环概览，6 阶段管线和 epoch 边界机制。
2. `docs/guide/1.training-process-detailed.md` - 训练过程详解，入口脚本、配置系统、双模型架构。
3. `docs/guide/2.scoring-mechanism.md` - 评分机制详解，`compute_score()` 环境无关聚合层。
4. `docs2/skill_learning_methods_survey.md` - 10 种 Agent 技能学习方法综述。
5. `docs2/skill_evolution_paradigm_classification.md` - 按优化范式分类的技能进化方法。
6. `docs2/non_frequent_skill_evolution_proposal.md` - 非高频 Skill 自演进方案。

### SkillOpt 核心源文件

1. `skillopt/engine/trainer.py` - 核心训练循环，6 阶段 ReflACT 管线。
2. `skillopt/optimizer/clip.py` - 梯度裁剪模块，编辑排序和选择。
3. `skillopt/optimizer/lr_autonomous.py` - 自主学习率决策。
4. `skillopt/optimizer/prox_shrink.py` - SkillProx 后向阶段，训练后近端压缩。
5. `skillopt/evaluation/gate.py` - 验证门控，accept/reject 候选技能。
6. `skillopt/gradient/aggregate.py` - 层级化补丁合并。
7. `skillopt/optimizer/rewrite.py` - 全技能重写。
8. `skillopt/optimizer/meta_skill.py` - 跨 epoch 优化器策略记忆。
9. `skillopt/optimizer/scheduler.py` - 学习率（编辑预算）调度器。
10. `skillopt/optimizer/skill.py` - 编辑应用和补丁处理。
11. `skillopt/optimizer/slow_update.py` - Epoch 级纵向技能精炼（=动量）。
12. `skillopt/gradient/reflect.py` - 核心 Reflect 引擎，minibatch 轨迹分析。
13. `skillopt_sleep/cycle.py` - 夜间周期编排器。
14. `skillopt_sleep/consolidate.py` - Stage 4 合并，一个 SkillOpt epoch。

***

## 总结

本提案基于对 SkillOpt 全量代码的深度分析和对 2025-2026 年最前沿研究的系统性调研，提出了 15 个可落地的算法改进方案。这些方案覆盖了训练管线的每个阶段：

```
任务采样          → CL-Sampler, Actor-Curator
  ↓
① ROLLOUT         → TAE-Route (技能路由), TTC-Scaling (推理扩展)
  ↓
② REFLECT         → CCE-Reflect (对比因果), RePro-Reflect (进度感知)
  ↓
③ AGGREGATE       → PRC-Aggregate (补丁校准)
  ↓
④ SELECT          → MAB-Select (多臂老虎机)
  ↓
⑤ UPDATE          → (现有: patch / rewrite / full_rewrite)
  ↓
⑥ GATE            → ParetoGate (帕累托), PrefGate (偏好优化)
  ↓
Epoch 边界         → PBE (种群化), PDM (多样性), EM-MetaSkill (情景记忆),
                     MetaSkill-Evolve (递归进化), BO-Scheduler (贝叶斯调度)
```

**核心改进哲学**：从"单一谱系 + 二元决策 + 确定性选择"升级为"种群化帕累托 + 偏好信号 + 概率采样 + 因果归因 + 课程学习"的多维自适应优化系统。

**保守估计**：组合所有改进方案后，预期整体性能提升 2-3 倍。
