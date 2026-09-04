# WikiSkill 落地 SkillOpt 可行性评估

> 基于论文 [WikiSkill: Compiling Agent Experience into Persistent Knowledge for Skill Evolution](https://arxiv.org/abs/2608.27454)（Google Research, 2026-08-27）与当前 SkillOpt 代码库的对照分析。
> 评估目标：在 SkillOpt 框架中引入 WikiSkill 的持久知识库（Wiki）层，评估架构兼容性、实现路径与成本。

---

## 一、WikiSkill 核心方法

### 1.1 问题定位

现有 skill 进化方法（EvoSkill、Trace2Skill、SkillOpt）的共同缺陷：**经验散落在优化历史中，缺乏独立、持久的知识表示**。具体表现为：

- EvoSkill：维护提案历史，但只是"日志"，不是结构化知识
- Trace2Skill：从轨迹提取教训后直接合并进 skill，知识混在技能里
- SkillOpt：用 rejected-edit 反馈和 epoch 级 meta guidance，但知识不独立沉淀

WikiSkill 的核心洞察：**把"经验"和"知识"分开**——在原始轨迹和可执行技能之间加一层持久知识库，让经验先沉淀为结构化知识，再指导技能进化。

### 1.2 三层知识架构

| 层 | 目录 | 内容 | 关键特性 |
|---|---|---|---|
| **Raw Layer** `raw/` | 每次迭代的执行轨迹 | 完整推理过程、工具调用、输出、最终答案 | **不可变**，供后续两层回溯 |
| **Wiki Layer** `wiki/` | 结构化知识库 | `patterns/`（每个失败/成功模式一个 md 文件）、`logs.md`（进化日志）、`skill-impact.md`（技能接受/拒绝历史 + diff） | **永不回滚**，跨迭代持续积累 |
| **Skills Layer** `skills/` | 当前生效的技能集 | `SKILL.md`（技能内容）、`PURPOSE.md`（溯源到 Wiki Pattern） | 可回滚，受 gating 控制 |

**Wiki 层的两个关键设计：**

1. **Wiki 永不回滚**：Skill 被拒绝时 Skills Layer 回到上一版本，但 Wiki 保留所有积累的知识。下一轮 Proposer 能看到"上次这个改法为什么被拒"，避免重复踩坑。
2. **知识与技能分离**：知识回答"我们知道什么"，技能回答"我们该怎么做"。以前的方法把两者混在一起，改技能时丢失了背后的推理上下文。

### 1.3 四步进化循环

每轮迭代执行：

1. **Inference Agent**：用当前 Skill 在训练集上跑 rollout，轨迹写入 Raw Layer。**训练时不允许访问 Wiki**（消融实验证明放开会降低效果——Agent 会直接查答案导致轨迹失去参考价值）。

2. **Wiki Maintainer**：采样成功+失败轨迹，做根因分析，更新 `patterns/` 目录和 `logs.md`。将零散轨迹编译为结构化知识。

3. **Skill Proposer**：以 **ReAct 方式**读 Wiki 索引 → 查 `skill-impact.md` 历史 → 按需读具体 Pattern 页面和原始轨迹 → 提出技能创建或补丁。

4. **Gating**：在验证集上评估候选 Skill，分数提升则接受，否则回滚。**Wiki 不受影响**。

### 1.4 实验结果

| 发现 | 数据 |
|---|---|
| WikiSkill 超越 SOTA | 5 benchmark × 5 model，全面优于 EvoSkill 和 SkillOpt |
| 技能进化与模型规模互补 | Qwen 4B +12.3pp，9B +17.5pp，27B +23.9pp（越强获益越多） |
| 技能弥补规模差距 | Qwen-3.5-9B + WikiSkill (47.4%) > Qwen-3.6-27B 无技能 (39.4%) |
| 跨模型迁移有效 | Qwen-3.5-9B 用 27B 进化的技能 = 70.2% vs 自进化 63.4%（ALFWorld） |
| **Wiki 消融** | **去掉 Wiki 访问后平均分从 63.7% 降至 48.7%（-15pp）** |

消融实验是 Wiki 价值的最强证据：持久知识积累是 Skill Proposer 能解决复杂失败模式的前提。

---

## 二、SkillOpt 现有知识持久化机制盘点

SkillOpt 已有多个"类 Wiki"的知识积累机制，但都没有做到**独立、持久、结构化**：

### 2.1 现有机制对照

| 机制 | 位置 | 持久性 | 结构化 | 与 WikiSkill 对应 |
|---|---|---|---|---|
| **slow_update** | skill 文档内 `<!-- SLOW_UPDATE_START/END -->` | 跨 epoch，但**仅相邻 epoch**（Markov） | ❌ 自由文本块 | 部分对应 Wiki Layer，但嵌入 skill 而非独立 |
| **meta_skill** | `out_root/meta_skill/epoch_XX/` | 跨 epoch，仅相邻 | ❌ 自由文本 | 部分对应 Wiki Layer，但面向 optimizer 而非通用知识库 |
| **step_buffer** | trainer 内存 | 仅 epoch 内，epoch 结束即重置 | ✅ 结构化条目 | 部分对应 `skill-impact.md`，但不持久 |
| **skill_aware appendix** | skill 文档内 `<!-- APPENDIX_START/END -->` | 跨 step（在 skill 内） | ❌ 自由笔记列表 | 部分对应 `patterns/`，但嵌入 skill |
| **_extract_failure_patterns** | trainer 内存 | 仅 step 内 | ✅ pattern + count + task_ids | 部分对应 `patterns/`，但即用即弃 |
| **prox_shrink LOO 审计** | 运行时计算 | 无持久化 | ✅ 逐单元效用 | 无对应（是收缩机制，非知识积累） |

### 2.2 关键差距

| 维度 | SkillOpt 现状 | WikiSkill |
|---|---|---|
| **知识独立性** | 知识嵌入 skill（slow_update）或 optimizer 内存（meta_skill），没有独立的持久层 | Wiki 是独立的第三层，skill 回滚不影响 wiki |
| **知识持久性** | slow_update/meta_skill 仅相邻 epoch 比较（Markov），无法跨全周期积累 | Wiki 跨所有迭代持续积累，pattern 只增不减 |
| **知识结构化** | 自由文本块，没有按 pattern 拆分为独立文件 | `patterns/` 每个模式独立 md 文件，带可操作修复方案 |
| **知识可查性** | reflect 时全量注入上下文（一次性塞入），长轨迹易超 token | ReAct 按需查阅：先看索引，再按需读具体 pattern |
| **技能溯源** | 无——skill 修改不记录"为什么改" | `PURPOSE.md` 将 skill 映射回 wiki pattern |
| **拒绝反馈持久性** | step_buffer 记录 rejected_edits，但 epoch 间重置 | `skill-impact.md` 跨迭代记录所有接受/拒绝 + diff |

### 2.3 现有代码中的有利条件

1. **模块化训练循环**：trainer.py 的 6 阶段管线（Rollout → Reflect → Aggregate → Select → Update → Evaluate）有清晰的阶段边界，易于插入新阶段
2. **配置开关体系**：`use_slow_update`、`use_meta_skill`、`use_skill_aware_reflection`、`use_train_gate`、`use_prox_shrink` 等开关已建立模式，新增 `use_wiki` 完全契合
3. **EnvAdapter 接口**：环境无关的 `rollout(env, skill, out_dir) → results` 和 `reflect(results, skill, out_dir) → patches` 接口，Wiki 层可在 trainer 级实现，不需要改 adapter
4. **step_buffer 已有 rejection 历史**：`_format_step_buffer` 和 `_extract_failure_patterns` 已实现 pattern 提取和拒绝反馈格式化，可直接复用
5. **slow_update 已有跨 epoch 比较基建**：`build_comparison_pairs`、`format_comparison_text` 等函数可复用于 Wiki Maintainer 的轨迹分析
6. **gate 机制成熟**：`evaluate_gate` / `GateResult` 已支持多种 gate 策略，Wiki 的 gating 可直接复用

---

## 三、架构映射：WikiSkill 组件 → SkillOpt 实现

### 3.1 逐组件映射

| WikiSkill 组件 | SkillOpt 对应物 | 状态 | 实现策略 |
|---|---|---|---|
| Raw Layer (`raw/`) | `step_dir/rollout/` 下已有完整轨迹 | ✅ 已有 | 无需新建，现有 rollout 输出即为 raw traces |
| Wiki Layer (`wiki/`) | 无 | **需新建** | 在 `out_root/wiki/` 下创建 `patterns/`、`logs.md`、`skill-impact.md` |
| Wiki Maintainer | reflect 阶段的 analyst（部分对应） | **需新建独立角色** | 新增 `skillopt/optimizer/wiki_maintainer.py`，在 reflect 之前运行 |
| Skill Proposer (ReAct) | reflect 阶段的 analyst | **需增强** | 修改 analyst prompt，注入 wiki 索引；或新建 ReAct 式 proposer |
| `patterns/` 目录 | `_extract_failure_patterns`（ephemeral） | **需持久化** | Wiki Maintainer 输出写入 `wiki/patterns/` 文件 |
| `logs.md` | 无（history.json 有部分记录） | **需新建** | Wiki Maintainer 每轮追加日志 |
| `skill-impact.md` | step_buffer（ephemeral） | **需持久化** | gate 后追加接受/拒绝记录 + diff |
| `PURPOSE.md` | 无 | **需新建** | skill 创建/修改时附加溯源信息 |
| Gating & Rollback | `evaluate_gate` / `GateResult` | ✅ 已有 | 复用现有 gate，只需确保 wiki 不随 skill 回滚 |
| 训练时 Wiki 隔离 | 无需改动 | ✅ 天然满足 | rollout 时 skill 注入 system prompt，本就不含 wiki |

### 3.2 插入位置（trainer.py 主循环）

```
现有流程:
  ① Rollout → ② Reflect → ③ Aggregate → ④ Select → ⑤ Update → ⑥ Evaluate
                                         ↑ step_buffer 记录拒绝历史（epoch 内）

WikiSkill 增强后:
  ① Rollout → ①.5 Wiki Maintainer → ② Reflect (Wiki-informed) → ③ Aggregate → ④ Select → ⑤ Update → ⑥ Evaluate → ⑥.5 Update skill-impact.md
                ↑ 读 raw traces + 现有 wiki     ↑ 注入 wiki 索引               ↑ gate 后追加 impact 记录
                ↑ 输出 patterns/ + logs.md

  Epoch 边界:
  [现有] slow_update + meta_skill
  [新增] wiki 跨 epoch 持久化（无需重置）
```

**关键设计决策**：Wiki Maintainer 作为新阶段 **①.5** 插入，在 rollout 之后、reflect 之前。这样：
- reflect（analyst）能利用已结构化的 wiki patterns，而非从零分析原始轨迹
- 与现有 slow_update/meta_skill 不冲突——slow_update 仍可保留作为 epoch 级纵向对比，wiki 是更细粒度的 step 级知识积累

---

## 四、逐组件实现可行性

### 4.1 Wiki 目录结构 — 难度：低

新建 `out_root/wiki/` 目录：
```
wiki/
├── patterns/
│   ├── pattern_001_searchqa_answer_format.md
│   ├── pattern_002_searchqa_multi_hop_reasoning.md
│   └── ...
├── logs.md
└── skill-impact.md
```

实现：约 30 行目录初始化代码 + 文件读写 helper。完全复用 `os.makedirs` + `json.dump` 模式。

### 4.2 Wiki Maintainer — 难度：中

**职责**：采样成功/失败轨迹 → 根因分析 → 更新 `patterns/` 和 `logs.md`

**实现路径**：
- 新增 `skillopt/optimizer/wiki_maintainer.py`，结构参考现有 `slow_update.py`
- 新增 prompt 文件 `skillopt/envs/<env>/prompts/wiki_maintainer.md`（或通用 prompt）
- 输入：采样轨迹 + 现有 wiki patterns 索引
- 输出：新建/更新的 pattern 文件 + logs.md 追加条目

**关键设计**：
- 采样策略：复用现有 rollout results 中的 hard/soft 分数，取失败 N 条 + 成功 M 条（参考论文的采样策略）
- Pattern 去重：Wiki Maintainer 需判断新 pattern 是否与已有 pattern 重叠，重叠则合并更新
- 写入策略：pattern 文件采用 append-only 语义（不删除已有 pattern，只新增或更新）

**预估改动**：~200 行新代码 + 1 个 prompt 文件

### 4.3 Wiki-Informed Reflect — 难度：低-中

**实现路径**：修改 reflect 阶段的 analyst prompt，注入 wiki 索引

**方案 A（推荐）：全量索引注入**
- 将 `wiki/patterns/` 的文件名 + 一句话摘要拼接成索引块，注入 analyst 的 system prompt
- 类似现有 `step_buffer_context` 和 `meta_skill_context` 的注入方式
- 优点：实现简单（~50 行），不增加 LLM 调用次数
- 缺点：analyst 看到的是索引而非全文，细节可能不够

**方案 B：ReAct 式按需查阅**
- 新建 Skill Proposer agent，用 ReAct 模式先读索引再按需读具体 pattern
- 优点：更忠实论文设计，token 效率更高
- 缺点：增加 1-3 次额外 LLM 调用/step，实现复杂（~300 行 + ReAct 循环）

**建议先实现方案 A 验证价值，再视效果决定是否升级为方案 B。**

### 4.4 skill-impact.md 持久化 — 难度：低

**实现路径**：在 gate 评估后（trainer.py ⑥ EVALUATE 之后），追加一条记录：

```markdown
## Step 5 (Epoch 1)
- Action: accept_new_best
- Score: 0.4523 (prev: 0.4301, +0.0222)
- Edits:
  + append: "When the question asks for a date range, always check..."
  + replace: "Look for the most recent..." → "Prioritize dates with..."
- Pattern refs: pattern_001, pattern_003
```

复用现有 `step_buffer` 条目的数据结构，改为写入文件而非仅存内存。~60 行。

### 4.5 PURPOSE.md — 难度：低

**实现路径**：在 skill 更新时（⑤ Update），附加/更新 `PURPOSE.md`：

```markdown
# Purpose

Created to address:
- pattern_001: Agent formats dates inconsistently
- pattern_003: Multi-hop questions fail at second hop

Last modified: Step 5, Epoch 1
```

~40 行，附加在 `_save_skill` 时。

### 4.6 Wiki 跨 Epoch 持久化 — 难度：低

**核心**：wiki 目录不被任何机制重置。现有 trainer 在 epoch 边界不清理 `out_root` 子目录，天然满足。

唯一需确认：slow_update 和 meta_skill 的 force-accept 模式会修改 `current_skill`，但不影响 `wiki/` 目录。需确保 wiki 读写不依赖 skill 内容。

---

## 五、成本分析

### 5.1 LLM 调用成本

| 组件 | 每步新增调用 | 每 epoch（~10 步）| 说明 |
|---|---|---|---|
| Wiki Maintainer | +1 | +10 | 采样轨迹分析 + pattern 生成 |
| Wiki-Informed Reflect（方案 A） | +0 | +0 | 注入索引到现有 analyst prompt |
| Wiki-Informed Reflect（方案 B） | +1~3 | +10~30 | ReAct 式按需查阅 |
| skill-impact.md 更新 | +0 | +0 | 纯文件 I/O |

**方案 A 总成本**：每 epoch +10 次 LLM 调用（Wiki Maintainer），相对现有 ~40-80 次/epoch（rollout + reflect + aggregate + meta_skill + slow_update），增幅约 12-25%。

### 5.2 Token 预算

| 数据集 | 单步 wiki 索引预估 | 风险 |
|---|---|---|
| searchqa | ~2-4K tokens（10-20 patterns × ~200 chars） | 低 |
| spreadsheetbench | ~1-2K tokens | 低 |
| livemath | ~1-2K tokens | 低 |
| officeqa | ~3-6K tokens | 中（已有 slow_update 超限问题，需控制 pattern 数量上限） |
| alfworld | ~2-3K tokens | 低 |

Wiki 索引注入远小于轨迹本身（officeqa 单条轨迹 66K 字符）。需设置 pattern 数量上限（建议 30-50 个）防止无限膨胀。

### 5.3 数据集匹配度

| 数据集 | 适配度 | 理由 |
|---|---|---|
| **searchqa** | ⭐⭐⭐ | val=200 足够支撑 pattern 验证；轨迹短，token 压力小 |
| **spreadsheetbench** | ⭐⭐⭐ | codegen 轨迹极短，pattern 提取信号清晰 |
| **livemath** | ⭐⭐ | val=17 噪声大，但 wiki 的 pattern 积累能部分弥补验证集小的不足 |
| **officeqa** | ⭐⭐ | 轨迹超长（66K chars），Wiki Maintainer 采样需限制条数 |
| **alfworld** | ⭐⭐⭐ | 有状态环境，pattern 跨迭代积累价值高 |

---

## 六、与现有机制的关系

### 6.1 Wiki vs slow_update

| 维度 | slow_update | Wiki |
|---|---|---|
| 粒度 | epoch 级（相邻 epoch 比较） | step 级（每次 rollout 后更新） |
| 持久性 | Markov（仅相邻 epoch） | 全周期（所有迭代积累） |
| 位置 | 嵌入 skill 文档 | 独立目录 |
| 回滚 | 随 skill 回滚 | **永不回滚** |
| 作用 | 写纵向对比 guidance 到 skill | 写结构化 pattern 供 reflect 参考 |

**结论**：互补而非替代。slow_update 做 epoch 级纵向对比，Wiki 做 step 级横向 pattern 积累。建议两者共存，`use_wiki` 独立于 `use_slow_update`。

### 6.2 Wiki vs meta_skill

| 维度 | meta_skill | Wiki |
|---|---|---|
| 面向 | optimizer（改善 edit 质量） | reflect analyst（改善 pattern 识别） |
| 位置 | 独立文件（`meta_skill/epoch_XX/`） | 独立目录（`wiki/`） |
| 持久性 | 相邻 epoch | 全周期 |
| 结构 | 自由文本 | 结构化 pattern 文件 |

**结论**：meta_skill 是 optimizer 的"元认知"，Wiki 是 analyst 的"知识库"。两者面向不同角色，可共存。

### 6.3 Wiki vs step_buffer

step_buffer 是 Wiki 的"前身"——它已经在做 pattern 提取和拒绝反馈记录，只是不持久、不结构化。**Wiki 本质上是 step_buffer 的持久化 + 结构化升级**。

实现时可考虑：step_buffer 继续在 epoch 内做即时反馈，Wiki 在 step 级做持久积累。step_buffer 结束时可将内容"提交"到 wiki。

---

## 七、主要风险

### 7.1 Pattern 质量风险

Wiki Maintainer 产出的 pattern 质量直接决定 Skill Proposer 的效果。低质量 pattern 会误导 analyst。

**缓解**：
- Pattern 需附带"证据"（trajectory IDs + 失败类型分类）
- 设置 pattern 数量上限（30-50），超出时触发合并/精简
- 参考 `skill_aware_consolidate_threshold` 的 consolidation 机制

### 7.2 Token 膨胀风险

长轨迹数据集（officeqa）的 Wiki Maintainer 分析可能超 token 上限。

**缓解**：
- 采样策略：限制每次分析的轨迹条数（参考 slow_update 的 `slow_update_max_prompt_tokens` 软上限 + 重要性驱逐机制）
- Pattern 文件控制：每个 pattern 限制在 500-1000 字符内
- 索引注入：reflect 时只注入 pattern 标题 + 一句话摘要，不注入全文

### 7.3 复杂度增加

新增 Wiki Maintainer agent 增加了系统复杂度。

**缓解**：
- 配置开关 `use_wiki: false`（默认关闭），按需启用
- 先在 1-2 个数据集上验证，再推广
- Wiki Maintainer 可复用现有 analyst 的 LLM 后端和 token 预算

### 7.4 与 slow_update 的功能重叠

两者都做"跨迭代知识积累"，可能产生冗余。

**缓解**：
- 明确分工：Wiki 做 step 级 pattern 积累，slow_update 做 epoch 级纵向对比
- 可逐步用 Wiki 替代 slow_update 的部分功能（先共存验证，再考虑整合）

---

## 八、实施建议

### 8.1 分阶段实施

| 阶段 | 内容 | 预估工作量 |
|---|---|---|
| **Phase 1** | Wiki 目录结构 + skill-impact.md 持久化 + logs.md | ~150 行 |
| **Phase 2** | Wiki Maintainer agent（prompt + 采样 + pattern 生成） | ~250 行 + 1 prompt |
| **Phase 3** | Wiki-Informed Reflect（方案 A：索引注入） | ~80 行 + prompt 修改 |
| **Phase 4** | PURPOSE.md 溯源 | ~50 行 |
| **Phase 5** | 消融实验：对比 use_wiki=true/false | 运行成本 |

### 8.2 配置设计

```yaml
# configs/_base_/default.yaml 新增
optimizer:
  use_wiki: false              # 总开关
  wiki_max_patterns: 40         # pattern 数量上限，超出触发合并
  wiki_sample_failures: 10      # Wiki Maintainer 每次采样的失败轨迹数
  wiki_sample_successes: 5      # Wiki Maintainer 每次采样的成功轨迹数
  wiki_max_prompt_tokens: 200000  # Wiki Maintainer 的 token 软上限
  wiki_inject_mode: index       # index（方案A）/ react（方案B）
```

### 8.3 验证计划

1. **在 searchqa 上先跑**：val=200 足够，轨迹短 token 压力小
2. **消融对比**：`use_wiki: true` vs `use_wiki: false`（其他配置不变）
3. **关键指标**：
   - test accuracy 提升
   - pattern 利用率（有多少 pattern 被 reflect 引用并导致有效 edit）
   - 首个被接受的 edit 出现的 step（预期更早，因为 wiki 积累加速 pattern 识别）
4. **与论文对比**：论文消融显示去 Wiki 降 15pp，若我们能看到 3-5pp 提升即为有效信号

---

## 九、结论

**WikiSkill 落地 SkillOpt 可行性：高。**

核心原因：

1. **架构兼容**：SkillOpt 的模块化训练循环和配置开关体系天然支持新层插入，不需重构
2. **复用度高**：step_buffer 的 pattern 提取、slow_update 的跨 epoch 比较、gate 的 accept/reject 机制均可直接复用
3. **增量可控**：方案 A（索引注入）仅需 ~500 行新代码 + 1 个 prompt 文件，不增加 reflect 阶段的 LLM 调用
4. **风险可缓**：配置开关默认关闭，token 膨胀有现成的软上限机制可复用
5. **价值明确**：论文消融证明 Wiki 层贡献 15pp，SkillOpt 现有的 slow_update/meta_skill 是"弱版 Wiki"（Markov、不独立、不结构化），升级为持久 Wiki 层有明确的改进空间

**最大收益点**：解决 SkillOpt 现有"知识 Markov 化"问题——slow_update 仅看相邻 epoch，step_buffer 仅看当前 epoch。Wiki 层让所有迭代的知识持续积累，这是论文消融 -15pp 的根因。

**建议优先级**：在 SkillProx 闭环门控（已实现）之后、作为下一个架构增强实施。两者互补：SkillProx 解决"前向未验证"，Wiki 解决"经验不复用"。
