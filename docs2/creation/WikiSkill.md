# WikiSkill 模块完整文档

> 论文来源: [WikiSkill: Compiling Agent Experience into Persistent Knowledge for Skill Evolution](https://arxiv.org/abs/2608.27454) (Google Research, 2026)
> 实现状态: 10/10 核心设计已对齐 | 88 单元测试通过 | 3 模式仿真验证

---

## 1. 解决什么问题

### 1.1 之前的困境（无 Wiki）

SkillOpt 的训练循环每步做：Rollout（跑轨迹）→ Reflect（分析失败+改技能）→ Evaluate（验证）。
**Reflect 每次都是"失忆"的**——只能看到当前这一步的失败，之前迭代踩过的坑不会记住。

```
Step 1: rollout → reflect 从零分析失败 → 改 skill    ← 经验用一次就丢
Step 2: rollout → reflect 又从零分析失败 → 改 skill   ← Step 1 的教训丢了
Step 3: rollout → reflect 又从零分析失败 → 改 skill   ← Step 1、2 的教训都丢了
```

### 1.2 Wiki 的解法

在 Rollout 和 Reflect 之间插入一层**持久知识库**，让经验先沉淀再复用：

```
Step 1: rollout → 【Wiki 记录经验】 → reflect（带着经验分析）→ 改 skill
Step 2: rollout → 【Wiki 更新经验】 → reflect（带着更多经验分析）→ 改 skill
Step 3: rollout → 【Wiki 更新经验】 → reflect（带着全部经验分析）→ 改 skill
```

关键设计：**Wiki 永不回滚**。技能被拒绝时 skill 回退，但 wiki 保留所有积累的知识。

---

## 2. 三层知识架构（对齐论文 §3.1）

```
workspace/
├── raw/                                    ← Raw Layer（不可变执行轨迹）
│   └── step_XXXX/task_YYY/
│       └── conversation.json               （推理链、工具调用、输出、最终答案）
│
├── wiki/                                   ← Wiki Layer（持久知识库，永不回滚）
│   ├── index.md                            （pattern 目录：所有 pattern 的 ID+摘要）
│   ├── patterns/                           （每个 pattern 一个 md 文件）
│   │   ├── pattern_answer_format.md
│   │   ├── pattern_multi_hop.md
│   │   └── pattern_date_range.md
│   ├── logs.md                             （进化日志：每步发现了什么、改了什么）
│   └── skill-impact.md                     （技能变更记录：接受/拒绝+diff+分数变化）
│
└── skills/                                 ← Skills Layer（当前技能，可回滚）
    ├── SKILL.md                            （技能内容，Agent 执行时读取）
    └── PURPOSE.md                          （技能溯源：本技能为哪个 wiki pattern 而创建）
```

### 三层生命周期对比

| 层 | 生命周期 | 写入者 | 读取者 |
|---|---|---|---|
| Raw Layer | 写入后不可变 | Inference Agent (rollout) | Wiki Maintainer, ReAct Proposer |
| Wiki Layer | **跨所有迭代持续积累，永不回滚** | Wiki Maintainer, 外层 harness | ReAct Proposer, Reflect |
| Skills Layer | 经验证后更新，可回滚 | Skill Proposer (reflect) | Inference Agent |

---

## 3. 四个核心组件（对齐论文 §3.2）

### 3.1 组件总览

```
每轮迭代:
  ① Inference Agent    → 用当前技能跑 rollout，产出轨迹到 raw/
  ①.5 Wiki Maintainer  → 分析轨迹，沉淀 pattern 到 wiki/
  ② Skill Proposer      → 读 wiki + 轨迹，提出技能修改
  ⑥ Gating + Rollback   → 验证集评估，接受/拒绝 + 写 skill-impact.md
```

### 3.2 组件 1: Inference Agent

- 用当前技能在训练集跑 rollout
- 技能内容全量注入 system prompt
- **训练时禁止访问 Wiki**（论文消融证明放开会变差）
- 产出: `raw/step_XXXX/task_YYY/conversation.json`

### 3.3 组件 2: Wiki Maintainer

在 `run_wiki_maintainer()` 中实现，位于 [wiki_maintainer.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/optimizer/wiki_maintainer.py)。

**工作流程**:
```
输入: rollout_results, wiki 目录
  │
  ├─ 1. 采样: 从失败中挑 N 条（默认10），从成功中挑 M 条（默认5）
  │         每条轨迹最多 wiki_max_traj_chars 字符（默认15000，论文值）
  │
  ├─ 2. 读取已有 pattern 列表（跨迭代积累的）
  │
  ├─ 3. 调 LLM (chat_optimizer):
  │     system = wiki_maintainer.md prompt（角色: 经验手册维护者）
  │     user = 已有 pattern 索引 + 失败/成功轨迹摘要
  │     输出 = JSON: {"patterns": [{id, type, description, workaround, task_ids}]}
  │     LLM 做根因分析: 不是"答案错了"，而是"技能缺少日期格式转换规则"
  │
  ├─ 4. 把 LLM 返回的 pattern 写成文件:
  │     wiki/patterns/pattern_<id>.md
  │     同一个 id = 覆盖更新（加新 evidence）
  │     不同 id = 新增 pattern
  │
  ├─ 5. 如果 pattern 数量 > wiki_max_patterns，删除最旧的
  │
  ├─ 6. 更新 wiki/index.md（持久化 pattern 目录）
  │
  └─ 7. 往 wiki/logs.md 追加日志:
        "Step 3: 写了2个pattern, 总共5个, 关键发现: ..."
```

**Pattern 文件格式** (`wiki/patterns/pattern_answer_format.md`):
```markdown
# Pattern: answer_format

**Type:** failure

**Description:** Agent returns dates in ISO format instead of natural language

**Workaround:** Add rule: when question asks for a date, output in 'Month DD, YYYY' format

**Evidence (task IDs):** q001, q003, q005

---
```

### 3.4 组件 3: Skill Proposer

有两种模式，通过 config 切换：

#### 模式 A: 标准注入模式 (`wiki_react_proposer: false`)
- `format_wiki_context()` 读取所有 pattern，拼成一段文字
- `format_skill_impact_context()` 读取最近 5 条技能变更记录
- 两者拼合后注入 reflect 的 user prompt
- Reflect 调 `run_minibatch_reflect()` → 多个 minibatch 并行产出 patch

**注入后的 reflect prompt**:
```
## Current Skill
{技能内容}

## Wiki Knowledge Base          ← 新增
- answer_format: Agent returns dates in ISO format...
- multi_hop: Agent stops at first hop...
- date_range: Agent returns single date when question asks for range...

## Recent Skill Changes (from wiki skill-impact tracker)   ← 新增
- Step 2: reject, -0.0300, tried replace old rule → new rule
  Do NOT re-propose edits that were rejected.

## Failed Trajectories
{失败轨迹}
```

#### 模式 B: ReAct 按需检索模式 (`wiki_react_proposer: true`)

这是论文的原始设计（§3.2.3），在 [react_proposer.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/optimizer/react_proposer.py) 中实现。

**与标准注入的核心区别**: Proposer 不是一次看到所有内容，而是像侦探一样一步步查。

**ReAct 循环**:
```
Proposer 启动时只获得:
  - wiki/index.md (pattern 目录，只有标题+摘要)
  - wiki/skill-impact.md 最近记录
  - 本轮训练结果摘要 (哪些 task 失败, 一句话原因)

然后 ReAct 循环:
  Thought: "今天的失败都跟日期有关，我看看 answer_format pattern"
  Action: read_file("wiki/patterns/pattern_answer_format.md")
  Observation: (读到 pattern 详情: 问题描述+解法)
  
  Thought: "我想看看具体失败轨迹"
  Action: read_file("raw/step_005/task_021/conversation.json")
  Observation: (读到原始执行轨迹)
  
  Thought: "搜索结果是 ISO 格式，技能里没有转换规则"
  Final Answer: {"patch": {"edits": [{"op": "append", "content": "[wiki:answer_format] ..."}]}}
```

**ReAct 的优势**:
- 更少 token（只读需要的文件，不全部注入）
- 更聚焦（不被无关 pattern 干扰）
- 能回溯原始轨迹细节（标准模式只看摘要）
- LLM 调用量更少（仿真: 15 vs 20）

**ReAct 的限制**:
- 最多 `wiki_react_max_iterations` 轮（默认8）
- 每轮产出单个 patch（非多个 minibatch patch）
- 需要 LLM 支持 tool-use 格式

### 3.5 组件 4: Gating + Rollback

使用 SkillOpt 已有的验证集门控（SkillProx）:
- 验证集评估候选技能
- 分数严格提升才接受，否则回滚
- **Wiki 不受影响** — 技能回滚时 wiki 保留所有积累

门控后调用两个函数:
1. `update_skill_impact()` — 往 `wiki/skill-impact.md` 追加变更记录
2. `write_purpose_md()` — 往 `skills/PURPOSE.md` 写技能溯源

**skill-impact.md 格式**:
```markdown
## Step 3 (Epoch 1)
- **Action:** accept_new_best
- **Score:** 0.5200 (prev: 0.4500, delta: +0.0700)
- **Pattern refs:** answer_format, date_range
- **Edits:**
  + append: [wiki:answer_format] When the question involves dates...
```

**PURPOSE.md 格式**:
```markdown
# Purpose

**Last modified:** Step 3 (Epoch 1)
**Action:** accept_new_best

## Motivating Wiki Patterns
- `answer_format` (see `wiki/patterns/pattern_answer_format.md`)
- `date_range` (see `wiki/patterns/pattern_date_range.md`)

## Edits Summary
2 edit(s), delta=+0.0700
```

---

## 4. 完整训练流程（7 步）

```
对每个 epoch:
  对每个 step:
    对每个 accumulation batch (默认1):
    
      ① ROLLOUT
      │  Agent 用当前技能跑训练集，产出轨迹
      │  产出: raw/step_XXXX/task_YYY/conversation.json + rollout_results
      │
      ①.5 WIKI MAINTAINER (if use_wiki)
      │  ├─ run_wiki_maintainer():
      │  │   采样轨迹 → LLM 根因分析 → 写 pattern 文件 → 写 logs.md
      │  ├─ _write_index_md():
      │  │   更新 wiki/index.md (pattern 目录)
      │  └─ wiki_context = format_wiki_context() + format_skill_impact_context()
      │      (标准模式: 拼成文字给 reflect; ReAct模式: 只给 index+impact+摘要)
      │
      ② REFLECT (Skill Proposer)
      │  if wiki_react_proposer:
      │    run_react_proposer():
      │      Thought→Action(read_file)→Observation 循环 → 产出单个 patch
      │  else:
      │    adapter.reflect():
      │      标准多 minibatch reflect, wiki_context 注入 prompt
      │  产出: raw_patches (技能修改方案)
      │
      ③ AGGREGATE
      │  合并多个 patch, 排序, 去重
      │
      ④ SELECT
      │  按 edit_budget 选最优 patch
      │
      ⑤ UPDATE
      │  apply_patch: 把 patch 应用到技能内容
      │  产出: candidate_skill
      │
      ⑤.5 TRAIN GATE (if use_train_gate)
      │  SkillProx 前向闭环: 在训练集上重执行验证
      │
      ⑥ EVALUATE
      │  在验证集上评估 candidate_skill
      │  if 分数提升: accept (保留 candidate_skill)
      │  else: reject (回滚到 current_skill)
      │
      ⑥.5 WIKI SKILL-IMPACT (if use_wiki)
      │  ├─ update_skill_impact():
      │  │   写 wiki/skill-impact.md (接受/拒绝 + diff + 分数变化)
      │  └─ write_purpose_md():
      │      写 skills/PURPOSE.md (技能溯源到 wiki pattern)
```

---

## 5. 代码文件清单

### 5.1 新建文件

| 文件 | 作用 |
|---|---|
| [skillopt/optimizer/wiki_maintainer.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/optimizer/wiki_maintainer.py) | Wiki Maintainer 核心模块（知识沉淀+读取） |
| [skillopt/optimizer/react_proposer.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/optimizer/react_proposer.py) | ReAct Skill Proposer（按需检索 tool-use agent） |
| [skillopt/prompts/wiki_maintainer.md](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/prompts/wiki_maintainer.md) | Wiki Maintainer 的 LLM prompt |
| [skillopt/prompts/react_proposer.md](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/prompts/react_proposer.md) | ReAct Proposer 的 LLM prompt |
| [tests/test_wiki_maintainer.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/tests/test_wiki_maintainer.py) | 14 个测试场景，88 个断言 |
| [tests/sim_wiki_comparison.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/tests/sim_wiki_comparison.py) | 3 模式对比仿真脚本 |

### 5.2 修改文件

| 文件 | 改动 |
|---|---|
| [skillopt/engine/trainer.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/engine/trainer.py) | 导入 wiki 函数; 配置读取; ①.5 Wiki 阶段插入; ReAct/标准 reflect 分支; gate 后 skill-impact + PURPOSE.md |
| [skillopt/envs/base.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/envs/base.py) | reflect() 传递 wiki_context |
| [skillopt/gradient/reflect.py](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/skillopt/gradient/reflect.py) | 三个 reflect 函数均加 wiki_context 参数，注入 user prompt |
| [configs/_base_/default.yaml](file:///c:/Users/huawei/Desktop/SkillOpt/SkillOpt/configs/_base_/default.yaml) | 新增 wiki 配置区段（8 个选项） |

### 5.3 wiki_maintainer.py 函数清单

| 函数 | 作用 | 读/写 |
|---|---|---|
| `init_wiki(out_root)` | 创建 wiki 目录结构 | 写 |
| `run_wiki_maintainer(...)` | LLM 分析轨迹 → 写 pattern + logs + index | 写 |
| `format_wiki_context(out_root)` | 读取所有 pattern，拼成索引文字 | 只读 |
| `format_skill_impact_context(out_root)` | 读取最近 N 条技能变更记录 | 只读 |
| `update_skill_impact(...)` | gate 后追加接受/拒绝记录 | 写 |
| `write_purpose_md(...)` | 写技能溯源文件 PURPOSE.md | 写 |
| `_write_index_md(wiki_dir)` | 持久化 pattern 目录到 index.md | 写 |
| `_write_pattern(...)` | 写单个 pattern 文件 | 写 |
| `_list_patterns(wiki_dir)` | 列出所有 pattern 的 ID+摘要 | 只读 |
| `get_wiki_summary(out_root)` | 调试用: 当前 wiki 状态 | 只读 |

### 5.4 react_proposer.py 函数清单

| 函数 | 作用 |
|---|---|
| `run_react_proposer(...)` | ReAct 主循环: Thought→Action→Observation→Final Answer |
| `_read_file(path, max_chars)` | 读取文件，截断到 max_chars（论文: 15000） |
| `_parse_action(response)` | 从 LLM 响应中提取 read_file 路径 |
| `_is_final_answer(response)` | 检测 LLM 是否产出了 Final Answer |
| `_format_iteration_summary(...)` | 格式化本轮训练摘要（失败列表+原因） |

---

## 6. 配置选项

```yaml
# configs/_base_/default.yaml → optimizer 区段

  # ── WikiSkill: persistent knowledge base (wiki_stage) ──────────────
  use_wiki: false                    # 总开关，默认关闭
  wiki_max_patterns: 40              # pattern 数量上限，超出删最旧的
  wiki_sample_failures: 10           # Wiki Maintainer 每次采样的失败轨迹数
  wiki_sample_successes: 5           # Wiki Maintainer 每次采样的成功轨迹数
  wiki_max_completion_tokens: 32000  # Wiki Maintainer LLM 调用的 token 上限
  wiki_max_traj_chars: 15000         # 单条轨迹最大字符数 (论文: 15000)，0=不截断
  wiki_react_proposer: false         # true=用 ReAct Proposer 替代标准 reflect
  wiki_react_max_iterations: 8       # ReAct 循环最大轮数 (最多 read_file 8 次)
```

### 推荐配置组合

| 场景 | 配置 | 说明 |
|---|---|---|
| 不用 Wiki（基线） | `use_wiki: false` | 不影响现有训练流程 |
| Wiki + 标准注入 | `use_wiki: true, wiki_react_proposer: false` | 全量注入 wiki 索引到 reflect prompt |
| Wiki + ReAct | `use_wiki: true, wiki_react_proposer: true` | 按需检索，论文原始设计 |
| 论文对齐 | `use_wiki: true, wiki_react_proposer: true, wiki_sample_failures: 5, wiki_sample_successes: 3` | 完全对齐论文参数 |

---

## 7. Wiki 三个文件的读写闭环

| 文件 | 写入者 | 读取者 | 用途 |
|---|---|---|---|
| `wiki/patterns/*.md` | `run_wiki_maintainer()` | `format_wiki_context()`, ReAct `read_file` | 知识库: 每个失败/成功模式+解法 |
| `wiki/index.md` | `_write_index_md()` (在 run_wiki_maintainer 末尾) | ReAct Proposer 启动时读取 | pattern 目录: 所有 ID+摘要 |
| `wiki/logs.md` | `run_wiki_maintainer()` | `get_wiki_summary()` (调试) | 进化日志: 每步发现了什么 |
| `wiki/skill-impact.md` | `update_skill_impact()` | `format_skill_impact_context()` → 注入 reflect | 变更记录: 接受/拒绝+diff+分数 |
| `skills/PURPOSE.md` | `write_purpose_md()` | 未来修改时追溯 | 技能溯源: 为哪个 pattern 而创建 |

---

## 8. 论文对齐状态

### 8.1 已对齐的设计（10/10）

| 论文设计 | 实现方式 | 状态 |
|---|---|---|
| 三层架构 (Raw/Wiki/Skill) | raw/ + wiki/ + skills/ 目录分离 | ✅ |
| patterns/ + logs.md + skill-impact.md | 三个文件，分别由不同组件写入 | ✅ |
| Wiki 永不回滚 | wiki 在独立目录，skill 回滚不影响 | ✅ |
| Wiki Maintainer 做根因分析 | prompt 要求找 root cause 非症状 | ✅ |
| 单条轨迹 15k 字符截断 | `wiki_max_traj_chars: 15000` | ✅ |
| index.md 持久化知识索引 | `_write_index_md()` 在 wiki_maintainer 末尾 | ✅ |
| skill-impact 被后续 Proposer 读取 | `format_skill_impact_context()` 注入 reflect | ✅ |
| PURPOSE.md 技能溯源 | `write_purpose_md()` 在 gate 后调用 | ✅ |
| ReAct-based Skill Proposer | `run_react_proposer()` tool-use agent 循环 | ✅ |
| 训练时禁止访问 Wiki | rollout 阶段不注入 wiki_context | ✅ |

### 8.2 参数对比

| 参数 | 论文 | 默认实现 | 可配置 |
|---|---|---|---|
| 采样失败轨迹数 | 5 | 10 | `wiki_sample_failures` |
| 采样成功轨迹数 | 3 | 5 | `wiki_sample_successes` |
| 单条轨迹截断 | 15000 字符 | 15000 | `wiki_max_traj_chars` |
| Pattern 数量上限 | 未提及 | 40 | `wiki_max_patterns` |
| ReAct 最大轮数 | 未提及 | 8 | `wiki_react_max_iterations` |

---

## 9. 测试覆盖

### 9.1 单元测试（88 个断言，14 个场景）

| 测试 | 验证点 |
|---|---|
| Test 1 | Wiki 目录初始化 + 幂等性 |
| Test 2 | Pattern 文件读写 + 同 ID 覆盖更新 |
| Test 3 | Wiki 索引格式化 + max_chars 截断 |
| Test 4 | Skill-impact 追踪 + format_skill_impact_context 读回 |
| Test 5 | 完整 Wiki Maintainer 流程（mock LLM） |
| Test 6 | **跨 3 轮迭代持久性**（pattern 累积+更新+不丢） |
| Test 7 | **Skill 回滚时 wiki 保留**（核心特性） |
| Test 8 | Pattern 数量上限淘汰最旧 |
| Test 9 | 边界情况（全成功/空结果） |
| Test 10 | **LLM 异常优雅降级**（无效 JSON + API 错误） |
| Test 11 | **单条轨迹字符截断**（wiki_max_traj_chars） |
| Test 12 | **index.md 持久化**（run_wiki_maintainer 后写入） |
| Test 13 | **PURPOSE.md 技能溯源**（pattern_refs 追溯） |
| Test 14 | **ReAct Proposer**（read_file 循环 + Final Answer） |

### 9.2 三模式仿真结果

```
┌─────────┬────────────────────┬────────────────────┬────────────────────┐
│ Step    │   Wiki OFF         │   Wiki ON (inject) │   Wiki + ReAct      │
├─────────┼────────────────────┼────────────────────┼────────────────────┤
│ Step 0  │ e=3 r=0 Δ=+0.030   │ e=6 r=6 Δ=+0.180   │ e=2 r=2 Δ=+0.060   │
│ Step 1  │ e=3 r=0 Δ=+0.030   │ e=9 r=9 Δ=+0.270   │ e=3 r=3 Δ=+0.090   │
│ Step 2  │ e=3 r=0 Δ=+0.030   │ e=9 r=9 Δ=+0.270   │ e=3 r=3 Δ=+0.090   │
│ Step 3  │ e=3 r=0 Δ=+0.030   │ e=9 r=9 Δ=+0.270   │ e=3 r=3 Δ=+0.090   │
│ Step 4  │ e=3 r=0 Δ=+0.030   │ e=9 r=9 Δ=+0.270   │ e=3 r=3 Δ=+0.090   │
└─────────┴────────────────────┴────────────────────┴────────────────────┘

┌─────────────────────────────────┬──────────┬──────────┬──────────┐
│ Metric                          │ Wiki OFF │ Wiki ON  │ ReAct    │
├─────────────────────────────────┼──────────┼──────────┼──────────┤
│ Total reflect edits             │       15 │       42 │       14 │
│ Wiki-referenced edits           │        0 │       42 │       14 │
│ Total simulated Δ               │  +0.1500 │  +1.2600 │  +0.4200 │
│ Final wiki patterns             │        0 │        5 │        5 │
│ LLM calls (total)               │       15 │       20 │       15 │
│ LLM calls (react_proposer)      │        0 │        0 │       10 │
└─────────────────────────────────┴──────────┴──────────┴──────────┘
```

**关键发现**:
1. 5 个 pattern 在 5 步内沉淀，3 种模式共享同一知识库
2. Wiki ON 的 reflect 产出 42 个引用具体 pattern 的 edit（vs OFF 的 0 个）
3. ReAct 用更少 LLM 调用（15 vs 20）产出 100% wiki-referenced 的 edit
4. ReAct 产出的 edit 更少但更精准（每轮单个精心设计的 patch）

---

## 10. 已发现并修复的 Bug

| Bug | 描述 | 修复 |
|---|---|---|
| `_list_patterns` ID 提取 | `str.replace("pattern_", "")` 替换所有匹配，导致 `pattern_pattern_a.md` → `a` | 改为前缀切片 `fname[len("pattern_"):-len(".md")]` |
| skill-impact.md 只写不读 | `update_skill_impact()` 写入但无函数读回 | 新增 `format_skill_impact_context()` 注入 reflect |

---

## 11. 数据流转示例

以 Step 1 为例（3 个日期格式失败 + 3 个日期范围失败 + 2 个多跳失败）:

```
Step 1: rollout 产出 12 个结果 (8 失败 + 4 成功)
  │
  ├─ Wiki Maintainer 分析后:
  │   更新 wiki/patterns/pattern_answer_format.md
  │     → "日期格式问题，已在 2 个 step 中出现" (覆盖更新)
  │   新增 wiki/patterns/pattern_date_range.md
  │     → "日期范围问题，返回单日期而非范围"
  │   更新 wiki/index.md
  │     → 新增 date_range 条目
  │   追加 wiki/logs.md
  │     → "Step 1: 写了2个pattern, 总共3个"
  │
  ├─ format_wiki_context() 生成:
  │   "## Wiki Knowledge Base
  │    - answer_format: Agent returns dates in ISO format... (recurring)
  │    - multi_hop: Agent stops at first hop...
  │    - date_range: Agent returns single date when question asks for range..."
  │
  ├─ format_skill_impact_context() 生成:
  │   "## Recent Skill Changes
  │    - Step 0: accept, +0.1500, appended answer_format rule"
  │
  ├─ Reflect (标准模式) 看到 wiki + impact + 失败轨迹:
  │   产出 3 个 patch，9 个 edit，每个引用具体 pattern
  │   [wiki:answer_format] When the question involves answer_format...
  │   [wiki:date_range] When the question involves date_range...
  │   [wiki:multi_hop] When the question involves multi_hop...
  │
  └─ Gate 评估:
      接受 → update_skill_impact: "Step 1: accept, +0.2700"
            → write_purpose_md: pattern_refs=[answer_format, date_range, multi_hop]
```

---

## 12. 运行测试

```bash
# 单元测试
.venv\Scripts\python.exe tests\test_wiki_maintainer.py

# 三模式仿真
.venv\Scripts\python.exe tests\sim_wiki_comparison.py

# 仿真结果保存在
# tests/sim_wiki_results.json
```

---

## 13. 关键设计原则

1. **Wiki 永不回滚** — 技能被拒时 wiki 保留，下一步仍可复用已积累的知识
2. **知识与技能分离** — 知识（wiki）回答"我们知道了什么"，技能（skills）回答"我们该怎么做"
3. **按需检索优于全量注入** — ReAct 让 Proposer 聚焦于相关 pattern，避免无关信息干扰
4. **可追溯** — PURPOSE.md 让每个技能修改能追溯到 motivating wiki pattern
5. **优雅降级** — LLM 调用失败时返回 None，不中断训练
6. **配置驱动** — 所有参数可通过 config 控制，默认关闭不影响现有训练
