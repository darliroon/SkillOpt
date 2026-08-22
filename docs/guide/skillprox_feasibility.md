# SkillProx 复现可行性评估

> 基于论文 [arXiv:2608.07449](https://arxiv.org/abs/2608.07449)(2026-08)与当前 SkillOpt 代码库的对照分析。
> 评估目标:在任意数据集(searchqa / livemathematicianbench / spreadsheetbench 等)上复现 SkillProx 的核心思路。

## 一、背景:SkillProx 是什么

SkillProx 是一个受\*\*近端梯度下降(PGD)\*\*启发的 skill 自进化框架,以 SkillOpt 这类"梯度式"skill 优化方法为基线,针对其两大缺陷演进:

1. **前向更新未经验证(open-loop)**:SkillOpt 的 optimizer 诊断出 patch 后直接提交(或仅在独立 selection 集上验证),诊断"看起来合理" ≠ 实际有效,失败方向不反馈给后续诊断。
2. **skill 无限膨胀(growth-oriented)**:删除只是普通 edit 操作之一,没有专门的知识巩固机制;重复指令、冲突启发式、错误泛化的题解持续堆积甚至干扰有效知识。

框架对应 PGD 的 `x_{k+1} = prox(x_k - η∇f(x_k))`,分两阶段:

- **Forward(梯度步)**:闭环诊断进化——在训练批 B\_k 上执行 skill → 诊断(失败 + 成功轨迹对比 + 历史 + 上次被拒原因)→ Patcher 产候选 → **同批重执行** → 双指标门控(hard 与 cell accuracy 均不降)→ 不通过则**回滚重试(≤3 次)**。
- **Backward(近端步)**:Prox 收缩——把 skill 解析为 L2 section / L3 reference group 单元,逐单元 leave-one-out 效用审计 → 负效用单元入选 → Shrinker 生成 trial(consolidate/demote/remove)→ 三重门控(结构有效且严格减字符、验证集 hard 不降、累计压缩率软上限 10%)→ 单遍有限终止。

论文关键实验结论(供对比参考):

- SpreadsheetBench IID 上全部三个 backbone 最优(21.0 / 51.3 / 54.5),平均 +3.0pp;
- 种子方差 ±0.5 vs **SkillOpt 的 ±7.6**;
- OOD(WikiTQ/HiTab)上 SkillProx 大多最优,SkillOpt 被指 OOD 崩溃;
- 消融:去闭环诊断 -1.5pp,去 Prox 收缩 -2.5pp。

本项目此前的运行观察与论文批评相互印证:livemath 两次 run 的 selection 分与 test 分完全倒挂(0.4118→0.288 vs 0.2353→0.368),skill 从 5K 涨到 19K 字符而后续 8 步全被 gate 拒绝——正是"小验证集噪声"与"只增不减"两个结构性弱点的体现。

## 二、架构映射:SkillProx 需要什么 vs 当前代码有什么

| SkillProx 组件       | 当前项目对应物                                     | 状态                     |
| ------------------ | ------------------------------------------- | ---------------------- |
| 前向同批重执行门控          | 无(UPDATE 后仅在 valid\_seen 上评估)               | **需新建**,钩子位置已存在        |
| 回滚+重试(≤3次)         | 无(拒绝即结束本步)                                  | **需新建**                |
| 拒绝原因反馈下次诊断         | `step_buffer` 已记录 rejected\_edits + 分数变化    | **已有 \~70%**(步级有,尝试级无) |
| 单元分解(L2/L3)        | skill 本身即 `##` 分节 markdown                  | **天然支持**               |
| leave-one-out 效用审计 | 无                                           | **需新建**                |
| Shrinker 收缩 + 三重门控 | 无                                           | **需新建**(新 prompt + 循环) |
| hard/cell 双指标      | `compute_score` 返回 hard/soft,gate 已支持 mixed | **已有**                 |
| 验证集评估基建            | `build_eval_env(split)` + rollout           | **已有**                 |

关键有利条件:

- SkillOpt 的 adapter 接口是环境无关的(`rollout(env_manager, skill, out_dir) → [{hard, soft}]`),`BatchSpec` 带 seed 可确定性重建训练批——**同批重执行对任意数据集都成立**,包括 alfworld 这类有状态环境(按 seed 重建即可)。
- SkillProx 论文本身沿用 SkillOpt 的训练配置(2:1:8 切分),两者同源,不存在配置体系冲突。

## 三、逐组件实现可行性

### 1. 前向闭环(同批重执行门控)—— 难度:低-中

- 位置:trainer 主循环 ⑥ EVALUATE 之前插入:用同一个训练批(或按 seed 重建)对 `candidate_skill` 再跑一次 rollout,比较 `hard_cand ≥ hard_cur 且 soft_cand ≥ soft_cur`。
- 改动量约 50-80 行,不改 adapter 接口,所有数据集通用。
- 唯一结构性改动是**步内重试环**:当前 reflect→aggregate→update 每步只跑一次,需包成 `for attempt in range(3)` 循环,把拒绝信息追加进 `step_buffer_context` 再跑 reflect。这是最大的一处手术,但逻辑上就是把现有步级机制下沉到尝试级。

### 2. 尝试级反馈 —— 难度:低

现有 `step_buffer` 机制直接复用,只需在重试环内追加"attempt j 被拒,尝试方向 X,hard 变化 -0.03"类条目。analyst prompt 已支持 `step_buffer_context` 注入。

### 3. 单元分解 —— 难度:低(含一个降级)

- SkillProx 分 L2 section + L3 reference file 两级;本项目 skill 是单文件 markdown,只有 L2(`##` 节),用 `re.split(r'\n(?=## )')` 即可解析。
- searchqa 的 skill 约 10-15 个 `##` 节,粒度合适。若需更细,可把节内 `-` 列表条目作为子单元(审计成本相应上升)。

### 4. 效用审计(leave-one-out)—— 难度:低-中,成本是主要约束

- 实现:n 个单元 → n+1 次 val 集 rollout(全 skill + n 个消融版),纯 bookkeeping,约 80 行。
- 成本按数据集差异巨大,见第四节。

### 5. Shrinker —— 难度:中

- 新增一个 optimizer 角色 prompt(consolidate/demote/remove 单个单元)+ trial 循环 + 三重门控(结构有效、字符数严格减少、val 上 hard 不降且 soft 降幅 ≤0.02、累计压缩软上限 10%)。
- 每个候选 1 次 val rollout。约 150 行 + 1 个 prompt 文件。gate 逻辑可参考现有 `skillopt/evaluation/gate.py` 的纯函数风格。

## 四、成本与数据集匹配度(基于实际数据)

| 数据集                  | train/val/test | 同批重执行开销                              | 审计+收缩开销(一次性)                        | Prox 适配度                                               |
| -------------------- | -------------- | ------------------------------------ | ----------------------------------- | ------------------------------------------------------ |
| **searchqa**         | 400/200/1400   | 每步 +1\~3 次 40 题 rollout,约 +3\~8 分钟/步 | n≈12 单元 → \~15 次 200 题 rollout(数小时) | **最佳**:val=200 足够支撑效用估计                                |
| **livemath**         | 35/17/125      | 每步 +1\~3 次 35 题 rollout,便宜           | \~14 次 17 题 rollout,便宜              | **有隐患**:val=17 做效用审计噪声极大(1 题=5.9pp),与此前 selection 噪声同源 |
| **spreadsheetbench** | 2:1:8 切分(论文主场) | 中                                    | 中                                   | 仓库有现成 env,最忠实复现路径                                      |

## 五、主要风险

1. **LLM 重执行的随机性**:同批重执行时 target 模型采样可能不同,门控翻转可能源于噪声而非 skill 效果。缓解:temperature=0,或对边界情形取 2 次平均。SkillProx 论文未讨论,需自行处理。
2. **小 val 集噪声**:livemath val=17 时,δ=0.02 级别的精细门控基本失效(一步就是 0.059)。审计需 bootstrap 或降级为"只删明显负效用的单元"。
3. **与现有机制冲突**:`slow_update` / `meta_skill` / `skill_aware` 都会改写 skill。Prox 的 backward 阶段应在 forward 全部结束、这些机制静默后运行;否则单元边界会被 appendix 标记污染(`<!-- APPENDIX_START -->` 块需先剥离——gate.py 已有现成剥离代码可复用)。
4. **官方代码未放出**:GitHub 仓库(`github.com/Steven011018/SkillProx`)标注 "will be available",prompt 细节(尤其 Shrinker)只能按论文附录自拟,复现存在解释空间。

## 六、建议落地路径

1. **第一步:在 searchqa 上实现前向同批门控 + 步内重试**(收益最大,直接针对"未验证更新"问题)。val=200 最健康,且已有刚跑完的基线可直接对比。
2. **第二步:实现单元审计 + Shrinker,作为训练结束后的独立阶段**(不动主循环,风险隔离),对照已观察到的 skill 膨胀问题(5K→19K、后 8 步全拒)验证"负效用删除"是否解决。
3. **第三步:livemath 上验证小 val 场景的鲁棒性**,必要时加 bootstrap。

## 七、总体判断

**可行性高**:这不是重写,而是在现有 trainer 的 ⑥ EVALUATE 阶段前后各插入一段逻辑 + 末尾追加一个阶段。预计新增代码 400 行以内 + 2 个 prompt 文件,全部走现有 adapter 接口,环境无关,可泛化到任意数据集。

我在 SkillOpt 上新增了 SkillProx 第一阶段核心机制：前向同批门控（forward closed-loop gate）+ 步内重试（in-step retries） ，共涉及 4 个文件：

## 改动内容

1. gate.py — train\_gate\_pass() 纯函数

- 对比候选 skill 在 同一训练批 上的重执行分数 vs 当前 skill 的分数
- 语义是"正确性检查"而非"严格提升"： cand >= cur - tolerance 即通过（相等也过，因为修住失败案例同时保住训练分仍是有效前进）
- 支持 hard / soft / mixed 三种指标 + tolerance 容差（当前 0.0）

1. default.yaml + config.py — 配置项

config.py 中注册进 \_FLATTEN\_MAP ，否则 YAML 分段键无法平铺进 trainer。

1. trainer.py — 主循环重构

原来的单次执行流程改成了 attempt 环：

```
① ROLLOUT → ② REFLECT → ③ AGGREGATE → ④ SELECT → ⑤ UPDATE
     ↓                                              ↓
     ↓                                    ⑤.5 TRAIN-GATE（新增）
     ↓                                    在同批重执行候选 skill
     ↓                                          ↓ pass → ⑥ EVALUATE(selection 
     gate)
     ↓                                          ↓ fail → 回滚 + 带失败反馈重试 ②'
     └── train_batch_infos 保存批规格/种子/结果，供重执行与重试复用
```

关键机制：

- 重执行 ：用 ① 保存的批 spec + seed 重建环境（确定性），只有候选 hash 变了才重跑（相同则平凡通过，省 rollout）
- 重试反馈闭环 ：失败 attempt 的分数变化 + 失败模式 + 被拒编辑注入下次 re-reflect 的诊断上下文
- 双层门控 ：train gate（同批保底）→ 原 selection gate（模型选择），后者逻辑未动
- 工件 ：重试写入 step\_dir/retry\_{n}/ ，门控执行写入 train\_gate/batch\_{a}/ ， step\_record.json 记录 train\_gate.attempts

## 解决的问题

原 SkillOpt 是 开环更新 ：补丁生成 → 应用 → 只在 selection 集上验收，训练批上是否退化无从得知；补丁一旦让训练分掉下去，只能等下一步浪费整个 rollout 才发现。现在每步先在训练批上闭环验证，退化即回滚重试，切断坏补丁进入 skill 轨迹的路径（SkillProx 论文里针对的 skill bloat / 质量回退问题）。

use\_train\_gate: false （默认）时行为与原版逐字节一致，不影响其他数据集。

<br />

<br />

我还是不太清楚这个同批保底机制和循环机制都是什么

用一个具体例子讲清楚。先看原来的问题，再看两个机制分别在干嘛。

## 背景：一步训练里发生什么

每一步（step）的简化流程：

## 原来的问题：开环，没有“退货检查”

原版第 ⑤ 步应用完补丁就直接进 ⑥ 了。 但没人验证过：这个新 skill 放回刚才那 40 道训练题上，还能得 0.875 吗？

- 补丁是 LLM 生成的，完全可能“修好了 1 道失败题，却弄坏了 5 道原来做对的题”
- 这个退化要等很多步之后才会在 selection 分数上显现，而且到那时你根本不知道是哪一步埋的雷
- 坏补丁一旦被 ⑥ 接收，就永久留在 skill 里，越积越多（论文说的 skill bloat）

## 同批保底（train gate）是什么

就是在 ⑤ 和 ⑥ 之间插了一道检查：

“同批” 就是字面意思：和 ① 用的是 完全相同的 40 道题 （同一批数据、同一个种子重建的环境）。

为什么必须同批？ 因为这样对比才公平。同一份考卷，换了个学生（新 skill），分数从 87.5 掉到 60——你就能确定是学生变差了，而不是考卷变难了。如果换一批题，分数波动你分不清是补丁的问题还是题目难度的问题。

“保底” 就是保住训练分这条底线：新 skill 至少不能比旧的在训练题上做得更差。注意判定是 >= 而不是 > ——持平也算过。因为“修住失败案例 + 不伤及原有正确案例”本身就是有效的推进，没必要要求严格提升。

## 循环机制（步内重试）是什么

被 ⑤.5 拒绝之后，旧版逻辑只能放弃这一步。新逻辑是 当场重试，最多 3 次 ：

关键点：

1. 重试不是盲抽卡 。第二次反思时，优化器拿到的诊断材料里多了一段“上一次你改的东西把训练分改掉了，具体是这几道题坏了”——LLM 是带着失败教训重新出补丁的，这就是论文说的 closed-loop（闭环）。
2. 重试不重跑 rollout 。① 的 40 道题结果原样复用（当前 skill 没变，重跑结果一样，纯浪费钱），只重跑 ② 反思。省 token。
3. 3 次全失败就放弃这一步 ，skill 保持原样不动，并把失败原因记进跨步缓冲区，下一步反思时还能看到。

## 和 selection gate（⑥）的区别

⑤.5 train gate（新） ⑥ selection gate（原有） 考卷 当前这批 40 道训练题 固定的 selection 验证集 问题 “新 skill 有没有变差？” “新 skill 值不值得替换当前版？” 性质 正确性检查（>= 即过） 择优（必须 > 当前分） 没过的后果 当场回滚重试 拒绝但保留反馈到下一步

所以完整语义是： train gate 负责保证“不带伤”，selection gate 负责保证“值得换” 。一个候选 skill 要先证明自己不退步，才有资格去竞争“要不要成为正式版”。

一句话总结： 同批保底 = 同一份考卷重考一遍防退化；循环机制 = 考砸了带着错题分析当场补考，最多补考两次。

<br />

<br />

<br />

<br />

前 run 的数据恰好演示了为什么还需要后面的部分：skill 从 3.5K 涨到 10.1K 字符，但 step 11 之后 21 步连续被拒 ——每步仍烧一整轮 rollout+reflect（约 7 分钟），纯浪费。这就是论文说的 growth-oriented 问题。

## 已完成的（第一阶段）

组件 状态 前向同批门控（train gate） ✅ 已实现并验证 步内重试（≤3 次） ✅ 尝试级失败反馈注入 re-reflect ✅ 步级拒绝反馈（step\_buffer） ✅ 原本就有

## 剩余可用点（按价值排序）

1. Backward/Prox 收缩阶段 —— 价值最大，消融显示去掉它 -2.5pp（比闭环的 -1.5pp 还大）

就是“近端步”：训练结束后独立运行，专门做减法。

- 单元分解 ：skill 按 ## 节切分， re.split(r'\n(?=## )') 一行搞定
- leave-one-out 效用审计 ：逐节删除后在 val 集上重评，找出负效用单元（你现在的 10.1K skill 里大概率有）
- Shrinker ：新 optimizer 角色，对负效用单元生成 consolidate/demote/remove 三类操作
- 三重门控 ：结构有效且严格减字符 + val hard 不降 + 累计压缩率软上限 10%
- 改动约 230 行 + 1 个 prompt 文件， 不动主循环 ，风险隔离
  关键优势：可以直接拿当前 nogate run 的产物做实验 ——它已经积累了 10.1K 的膨胀 skill 和“后 21 步全拒”的病理样本，是完美的测试对象，不用重新训练。

1. 双指标 AND 门控 —— 小改动

论文要求 hard 和 cell accuracy（对应我们的 soft） 都不降 才过门；我们目前是单指标三选一。改 gate.py 的 train\_gate\_pass() 加一个 and 模式即可，十几行。

1. 重执行确定性 —— 风险缓解

论文没讨论的问题：同批重执行时 target 模型采样随机，门控翻转可能纯属噪声。缓解：门控 rollout 用 temperature=0，或边界情形（分差 < 0.02）取 2 次平均。改动很小。

1. livemath 小 val 鲁棒性 —— 仅影响 livemath

val=17 时一道题就是 5.9pp，精细门控失效。需要 bootstrap 置信区间，或降级为“只删明显负效用单元”。searchqa（val=200）不受影响。

## 建议

nogate run 还剩 8 步（预计 1 小时内跑完）。跑完后最有价值的动作是： 在它的最终 skill 上实现并运行 Backward 阶段 ——既能验证 Prox 收缩能不能把 10.1K 压回有效核心、分数还能保住 0.805，又不用付重新训练的成本。

要现在就开始规划 Backward 阶段的代码改动点吗？

<br />

<br />

<br />

是关于训练执行流程的概念梳理。基于我们之前的讨论，我按层次拆解：

## **Step（单步迭代）**

一个 Step 是训练循环的**最小完整单元**，在一个训练 batch 上执行：

Plain Text

```
Step k:
  1. Execute（Rollout）
     - 在训练 batch B_k 上运行当前 skill
     - use_eval_feedback=True → 收集 NL 反馈信号
     - 产出轨迹数据

  2. Score
     - compute_score(轨迹) → r_hard, r_soft
     - r_hard: 任务成功率（硬指标）
     - r_soft: LLM judge 质量分（软指标）

  3. Reflect
     - 模块级归因：分析 r_hard/r_soft 的变化
       归因到 skill 的哪些模块（Instruction / Body / 某个子策略）
     - 产出诊断信息：哪些模块需要改、怎么改

  4. Update
     - 基于 Reflect 的诊断，对 skill 做 bounded text edit
     - "textual learning rate" 限制修改幅度（防止一步改太多）
     - 产出 skill 候选版本 X_k'

  5. Validate（Gate）
     - 在 held-out 验证集上重执行 X_k'
     - 严格要求：性能必须 ≥ 上一版，否则拒绝
     - 被拒绝的 edit → 存入 Rejected-Edit Buffer（供后续 Reflect 回顾）
     - 通过则接受，X_k' 成为新的 current skill
```

## **Epoch（一个完整轮次）**

一个 Epoch = **遍历一遍全部训练数据**（所有 batch）：

Plain Text

```
Epoch e:
  ─ Step 1 (B_1): Execute→Score→Reflect→Update→Validate
  ─ Step 2 (B_2): Execute→Score→Reflect→Update→Validate
  ─ ...
  ─ Step N (B_N): Execute→Score→Reflect→Update→Validate
  ──────────────────────────────────────────────
  │ Slow / Meta Update（epoch 级慢更新）          │
  │ - 回顾整个 epoch 的 Rejected-Edit Buffer      │
  │ - 检查累积的失败模式（反复被拒绝的 edit 方向）  │
  │ - 调整 textual learning rate 或策略           │
  │ - 更新 meta 层面的参数                        │
  └──────────────────────────────────────────────┘
```

<br />

## **在 SkillProx 中的位置**

Plain Text

```
Epoch 1 (Steps 1..N + Slow Update)
Epoch 2 (Steps 1..N + Slow Update)
...
Epoch E (Steps 1..N + Slow Update)
  → 产出 X_f（前向训练结束）

Backward Prox（一次性，在验证集 V 上）
  → 产出 X*

Hold-out 测试评估
  → 最终性能报告
```

所以 K 轮前向迭代 = E 个 epoch × N 个 step。Prox 在所有 epoch 跑完之后才启动，不参与任何 epoch 内部的 step 循环。

<br />

Step（batch 级更新）= Rollout + Score + Reflect + Update + Validate                      ↑执行采样    ↑评分   ↑归因     ↑文本编辑  ↑门控

```
batch 级  →  Step: Rollout → Score → Reflect → Update → Validate(门控)
epoch 级  →  Slow/Meta Update: 回顾本 epoch 累积模式
系统级    →  Backward Prox(验证集V) → 最终测试(测试集)
```

<br />

<br />

## 起点

训练产出的 best\_skill.md， 14243 字符 ，在 val 集（200 题）上测得基线： hard=0.7800, soft=0.8591 。这两条线就是后面所有门控的“地板”。

## Round 0

### ① 单元分解

粒度细化的作用就在这：旧版只有 2 个单元（Core rules 整节 + Learned Rules 整节 8363c 一刀切），现在是 5 个可移除单元 。

### ② LOO 效用审计（5 次消融 × 200 题 = 1000 次 rollout）

每次拿掉一个单元，重测 val：

单元 拿掉后 hard Δhard Δsoft 判定 u0 Core rules 0.755 -0.025 -0.011 valuable u2 ### 1) 0.790 +0.010 -0.008 removable（负资产） u3 ### 2) 0.760 -0.020 -0.013 valuable u4 ### 3) 0.780 0.000 -0.009 removable u5 ### 4) 0.775 -0.005 -0.007 marginal

信号很清晰： Core rules 和 ### 2) 是真有用的； ### 1) （2890 字符的大块）删掉反而 涨 1 分 ——这就是旧粒度发现不了的：整节 Learned Rules 消融时， ### 1) 的负贡献会被 ### 2) 的正贡献抵消掉。

### ③ Shrinker 决策

gpt-5.2 收到上面的表 + 约束（ min\_chars = 14243×(1-0.10) ≈ 12819 ，trial 必须更小，保护块逐字保留），它的 reasoning 是：
“Core rules removal hurt (-0.025 hard), so keep but tighten . Subsection 1 had low value (+0.010 hard), so compress heavily …”
注意它没机械执行“删 u2、留其他”——而是： u2 重度压缩 （2890c 的负资产内容压到几十行）、 u0 收紧措辞保留 、u3/u4/u5 保留。产出 trial： 7977 字符 。

### ④ 三重门控

trial rollout： hard=0.7950, soft=0.8779 （比基线双双上涨）

- Gate 1 结构：还有 ## 节、保护块在 → 过
- Gate 2 压缩上限：压缩率 44% > 上限 10% → 本该拒……但触发了 证据豁免 ：hard 和 soft 都严格优于收缩前基线（0.780→0.795, 0.859→0.878），“压这么多反而更好”就是放行证据 → 过
- Gate 3 验证地板：高于基线 → 过
  → ACCEPT ，cur\_skill 更新为 7977 字符版。

## Round 1（失败的轮，展示门控如何守住底线）

对 7977 字符版重新分解（这次 ## Core rules 3008c 和 ## Learned Rules 2094c 都不超 3000，回到 2 个单元），再审计。这次两个单元单独拿掉分数反而都涨（Δhard +0.015/+0.020）——Shrinker 于是激进砍到 5843 字符 （累计压缩 59%）。

trial 结果： hard=0.770, soft=0.8557 —— 双指标跌破基线 （0.780/0.859）。

- Gate 2：压缩 59% > 10%，申请证据豁免 → 但这次 hard 跌了 （0.780→0.770），豁免不成立
- Gate 3：hard 跌幅 0.010 虽在 tolerance 0.05 内，但没有豁免资格 → REJECT
  → 首败即终止（单遍有限终止）， 最终结果定格在 Round 0 的 7977 字符版 。

## 一句话总结这个过程 LOO 审计回答“ 哪些内容在贡献分数 ”（u2 是负资产、Core rules 是支柱），Shrinker 决定“ 怎么处理 ”（负资产狠压、支柱收紧保留），三重门控回答“ 这次收缩值不值 ”（44% 压缩 + 涨分 = 放行；59% 压缩 + 掉分 = 打回）。

最后 test 集（1400 题）验证：7977 字符版 hard=0.8086 vs 原版 0.8236—— 省 44% token 成本，性能在噪声带内持平 。

## 1. 几轮 Round？

上限 3 轮 （config prox\_max\_trials: 3 ），但 首次失败立即终止 （单遍有限终止，不重试）。

实际运行轨迹：

所以本次实际跑了 2 轮 就停了。提前终止的触发条件还有两种：skill 没有可移除单元、Shrinker 返回空/与当前相同。

## 2. 三重门控机制

实现在 gate.py#L522-L606 ， 顺序检查，一票否决 ：

### Gate 1 — 结构门（形式合法性）

检查 拒绝条件 非空 trial 为空 保留章节结构 原 skill 有 ## 节而 trial 一个都没有（skill 被砍成光杆） 保护块完整 SLOW\_UPDATE\_START/END 、 APPENDIX\_START/END 任一标记的 出现次数 与原 skill 不等（防 Shrinker 改写/丢失慢更新机制块）

### Gate 2 — 严格收缩 + 压缩软上限（防止砍太少或砍太狠）

两步：

① 必须严格变小 ： len(trial) >= len(prev) 直接拒（防“改写但不收缩”）

② 累计压缩率 vs 软上限 （这是关键设计）：

- 默认上限 10% 是保守值，防“渐进式蚕食”式过度收缩
- 证据豁免 ：LOO 审计若证明某单元是负资产，删它压缩 44% 也合理——所以留了“涨分即可越线”的逃生口
- 本次 Round 0 正是走豁免通过的（44% > 10%，但 hard 0.780→0.795、soft 0.859→0.878 双涨）

### Gate 3 — 验证地板（性能底线）

锚定 pre-shrink baseline （0.7800 / 0.8591），不是上一轮的分数：

```
trial_hard < base_hard - hard_tolerance(0.05)  → 拒
trial_soft < base_soft - soft_tolerance(0.03)  → 拒
```

锚基线而非当前轮是有意为之：若锚当前轮，多轮累积后每轮跌 0.04 也能一路通过（温水煮青蛙）。锚基线则保证 无论收缩多少轮，最终分数不会比训练结束时的水平低超过 tolerance 。

<br />

<br />

### Prox 收缩过程 —— 从头到尾只用验证集，一次都没碰测试集

run\_prox\_shrink 里所有 \_rollout\_scores(...) 调用的 split 参数全部是 "valid\_seen" （ prox\_shrink.py ）：

| 步骤            | 用的集 | 题数    | 作用                                           |
| :------------ | :-- | :---- | :------------------------------------------- |
| ① Baseline 评估 | val | 200   | 定下 Gate 2/3 的地板（0.7800/0.8591）和压缩率分母（14243c） |
| ② LOO 参考分     | val | 200   | 当前 skill 的参照分数                               |
| ③ LOO 消融 ×5   | val | 200×5 | 每个单元的效用 Δ                                    |
| ④ Trial 评估 ×2 | val | 200×2 | 三重门控的输入（round 0: 0.795；round 1: 0.770）       |

val 上累计消耗：约 1800 题 rollout 。

### 测试集 —— 只在一切尘埃落定后出现一次

test 1400 题在整个流程里 只在最后一步 使用：trainer 的 test\_eval\_final （ trainer.py#L2688 ），即训练结束 + prox 收缩完成、最终 skill 冻结之后的一次性汇报评估。我们昨天手动跑的 eval\_only --split test 也是同一性质的事后验证。

### 为什么必须这样分

Prox 的每一步都在做 选择 ：删哪个单元、接受哪个 trial。做选择就要看分数，看分数的集就会被“过拟合”——LOO 表上 5 个 Δ 值、门控的 2 次 pass/reject 决策，全是基于这 200 道 val 题的信号。所以：

- val 分数是“决策依据” ——可以反复用，但会被选择偏差污染（这就是为什么收缩后 val 涨 1.5pt，test 上却持平：val 的涨幅里有一部分是“在这 200 题上做了选择”带来的乐观偏差）
- test 分数是“最终考核” ——任何决策环节都不许看，只用于一次性的、无偏的效果汇报
  前面观察到的现象正好印证这一点：收缩后 val 0.780→0.795（+1.5pt），test 0.8236→0.8086（-1.5pt）。val 的改善没有完全泛化，其中一部分是对 val 本身的适配。如果当初让 LOO 或门控直接在 test 上跑，test 分数会被这些决策“吃掉”，汇报出来的数字就虚高且无法反映真实泛化能力。

<br />

<br />

<br />

<br />

<br />

我觉得prox的分块机制还需要修改一下，之前是按照 ### 分。但我认为不管是按照## 分还是按照 ### 分都很粗暴，而且我觉得是不是粒度需要到段落级？你是专家，请你回答这个问题

## 直接回答：不建议把默认粒度降到段落级，但你指出的问题是真的——正确解法是“自适应下钻”，而不是“全局细化”

### 为什么段落级是陷阱

1. 测量噪声是硬约束，粒度先于信噪比失效

LOO 效用的公式是 utility = ref - loo ，在 200 题 val 上，配对差分的噪声 σ≈1.5\~2pt。这意味着：

- 可检测效应 ≥ 3pt（2σ）才可信
- 一个 ### 节（2700c）的效应量级是 1\~2.5pt（本次实测 u2 才 +1.0pt，已在噪声边缘）
- 一个段落（200 400c）的真实效应典型是 **0.1 0.5pt**——完全淹没在噪声里
  粒度越细，测出来的 Δ 越是噪声而非信号。段落级 LOO 表会变成一张 随机数表 ，Shrinker 拿到的 40 个 Δ 值里大半不可信，反而误导压缩决策。这不是工程问题，是统计问题： 200 题的 val 根本供养不起段落级归因 。要供养，val 得扩到 2000+ 题，成本又平方级上涨。

1. 段落不是语义独立单元

## / ### 是作者（或生成 LLM）显式选择的语义边界。段落边界只是排版换行。典型结构：

LOO 是一次一个的消融，测不出交互（A、B 单删都有害，合删无害；或反之）。段落级把交互问题放大一个数量级。刚才 audit 里 u2 的 -2890c 效应为正，正是因为它作为整体是负资产——拆成段落后，每段的 LOO 可能都是“删了掉分”，你会得到一个完全相反的结论。

1. 成本模型

LOO 成本 = 单元数 × val题数 。本次 5 单元 × 200 = 1000 次 rollout（约 40 分钟）。段落级 40 单元 × 200 = 8000 次。SpreadsheetBench 是多轮沙箱执行环境，单题成本是 SearchQA 的好几倍——8000 次 rollout 完全不现实。

1. 最关键的：这是分工问题，审计根本不需要做段落级手术

回看 Round 0 实际发生了什么：LOO 表只告诉 Shrinker“u2 这个 区域 是冷的”，然后 Shrinker 自己完成了段落实级的手术——2890c 压到几十行，保留了有价值的部分。 LLM 天然擅长段落级编辑，它读了全文 。效用表的职责是分诊（哪个区域冷），不是切片（哪段该留）。让审计做段落级归因，是用昂贵的统计工具做 LLM 免费就能做的事。

### 但你的不满有合理内核：现在的下钻是“一刀切”

当前逻辑是“超 3000c 就整个 drill 到 ###”，这确实粗暴——它对 所有 大节无差别细化，包括那些 LOO 一测就明确的节。正确设计应该是 噪声感知的自适应下钻 ：

```
第一轮：在 ##（或现有 ###）粒度做 LOO
   │
   ├─ Δ 明显为正 (> +2pt)  → 有价值，保留，不下钻      ← 省钱
   ├─ Δ 明显为负 (< -2pt)  → 负资产，直接删/压，不下钻  ← 省钱
   └─ |Δ| < 噪声门 (~2pt)   → 信号不明 → 只对这些节
                                下钻一层，对子单元重测   ← 钱花在刀刃上
```

这就是二分搜索式归因： 只在“测不清”的地方加分辨率 。成本是 前沿单元数 × val ，而不是 全部段落 × val 。附带好处：缓解多重比较偏差（40 个单元一起测，总有几个纯噪声地冒出 ±2pt，自适应门控天然过滤）。

如果真需要全量段落级归因（比如做分析而非做决策），正确工具不是逐段 LOO，而是 Shapley 式分组消融 ：随机分组删减 + 截断蒙特卡洛估计每段边际贡献，用 \~10×val 的成本逼近 40×val 的信息量。但那是分析工具，不是收缩流程需要的。

### 建议

1. 保持 ##/### 为骨架 （语义边界 + 重建可靠性——段落级重建还要处理列表/表格跨段的烂摊子）
2. 把 drilldown\_chars 一刀切阈值改成噪声门控的自适应下钻 ：LOO 测不清（|Δhard|、|Δsoft| 都在 \~2pt 内）的节才递归下钻一层
3. 如果担心 val 噪声，优先加 prox\_loo\_env\_num 或对模糊单元用不同 seed 复测一次，而不是细化粒度
   要不要我把自适应下钻（方案 2）实现了？改动集中在 prox\_shrink.py 的 LOO 循环（两阶段）+ gate.py 的分解函数（支持对指定单元二次分解），预计不影响现有 42 个测试的语义。

<br />

<br />

<br />

## 噪声底 = “重复测量同一件事，测量值自己会抖动的幅度”

用一个具体场景定义它，不需要任何抽象概念：
把 完全相同的 skill 在 val 上测两遍（题一样、skill 一样，只有模型采样随机性不同）。
第一遍测出 hard=0.780，第二遍测出 hard=0.795。
这 +1.5pt 不是 skill 变好了 ——skill 一个字没动。它就是噪声。
噪声底就是回答： 这种“什么都没变但分数变了”的抖动，典型有多大？

## 能算，而且公式很简单

情况 1：单次测量的噪声（不需要任何配对）

hard 准确率本质是“200 题里答对几题”的比例。答对题数 \~ 二项分布，标准差：

代入的就是我们的真实数字：p=0.78，n=200。意思是： 真实水平是 78% 的 skill，单次测 200 题，测出来的值有 68% 概率落在 75.1%\~80.9% 之间 。这是高中统计，不是估计——只要知道 p 和 n 就能算。

情况 2：LOO 效用的噪声（配对差分，更小）

utility = ref − loo ，两次测量在 同一批题 上。大多数题两次结果相同（要么都对要么都错），只有少数“翻转题”贡献差值。设翻转题比例 \~4%（200 题里 8 题翻转）：

这就是我说的 2pt 的出处（1.4 2pt，取决于翻转率）。 它也能从数据里直接数出来 ： loo\_r0\_u4/ 和 baseline\_eval/ 的 results.jsonl 都存了每题的对错，逐题对比数一下翻转了几题，就得到经验值——不需要信我的公式，数据里有答案。

## 三个量的关系：一条流水线

```
【测量层】噪声底 σ ≈ 1.4~2pt
   "我的尺子最细能刻到多细"
   来源：val 只有 200 题（n 越大 σ 越小，与代码无关）
        │
        ▼
【标注层】verdict 分档 0.02
   "测出的效用 < 噪声 → 标为 marginal，告诉 Shrinker 别当真"
   为什么是 0.02：故意设在 ≈σ 处。
   测出 Δ=+0.01 时，真实值可能是 -0.01 也可能是 +0.03——
   统计上和 0 无法区分，所以只配"low value"标签
        │
        ▼
【决策层】tolerance 0.05
   "trial 比 baseline 跌超过 5pt → 拒绝"
   为什么是 0.05：≈ 2.5~3σ。数学含义：
   若一个 trial 真实零退化，纯噪声把它推过 -5pt 的概率 <1%
   → 门控拒绝时，有 >99% 把握是真的退化，不是冤枉它
```

一句话串起来 ：σ 是尺子的刻度精度（物理属性），0.02 是“读数小于刻度就不报数”（读数规则），0.05 是“判死刑需要远超刻度级的证据”（判案标准）。后两者都是 根据第一者的大小选的 ——所以 tolerance(0.05) > 分档(0.02) > σ(≈0.014\~0.02) 不是巧合，是必然的层次关系。

## 验证它确实存在：我们手里已有的证据

本次 run 里 \[final skill == best skill] 复用的那次 0.78 baseline，和 training 早期同 skill 的测量就有零点几 pt 的漂移；更直接的是 round 1 的 LOO：u0/u1 单独删除都“涨分”(+1.5/+2.0pt)，但把两个都删了（Round 1 trial）反而跌 1pt——如果那 +1.5/+2.0 是真效应，组合删除不该反向。它们就是噪声底之上的采样抖动。

想把经验噪声底真正算出来的话，我可以写个 10 行脚本对比 baseline\_eval 和某个 loo\_\* 目录的逐题结果，数出实际翻转题数——要吗？
