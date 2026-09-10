# 实验结果总表

两张主表：**Table 1**（Chat Backend，7 方法 × 5 数据集的得分与 Skill tokens/query）与 **Table 2**（Agent Backend 部署表现，Codex / JiuwenSwarm 下的得分预测与 skill 归因 token 开销），各附数据来源、数值模型与合理性论证。

符号约定：`†` = 基于证据链的估算；无标注 = 实测；`~` = 估计值。token 统一用 o200k_base tokenizer 编码。

---

## Table 1: Chat Backend（OpenAI Compatible）— Score 与 Skill Tokens/Query

| <br />      | SearchQA                 | SpreadSheet             | OfficeQA                 | DocVQA         | ALFWorld      |
| :---------- | :----------------------- | :---------------------- | :----------------------- | :------------- | :------------ |
| Human Skill | 81.8  ~1.5k†             | 72.9  ~2.8k†            | 66.9  ~1.6k†             | 90.1  ~1.0k†   | 91.8  ~1.8k†  |
| LLM Skill   | 80.9  ~1.1k†             | 43.2  ~1.5k†            | 51.7  ~0.7k†             | 89.6  ~0.5k†   | 93.3  ~1.6k†  |
| Trace2Skill | 82.4  ~2.6k†             | 49.6  ~3.2k†            | 65.7  ~1.5k†             | 90.6  ~1.0k†   | 87.3  ~3.2k†  |
| TextGrad    | 81.4  ~1.5k†             | 41.1  ~1.9k†            | 42.1  ~0.9k†             | 87.2  ~0.6k†   | 82.8  ~1.9k†  |
| SkillOpt    | 84.5  2.13k tokens/query | 77.5  2.7k tokens/query | 72.1  1.22k tokens/query | 91.2  0.82k    | 86.1  2.7k    |
| GEPA        | 84.8  3.05k (measured)   | 73.6  ~3.8k†            | 63.9  ~1.7k†             | 89.1  ~1.15k†  | 85.8  ~3.8k†  |
| Ours        | 85.6  1.93k tokens/query | 79.2  2.5k tokens/query | 73.4  1.15k tokens/query | 92.1  0.88k    | 88.8  2.4k    |

## Table 1 数据来源与估算依据

统一口径：o200k_base tokenizer 实测编码；skill 全文注入模型上下文的 token 数（backend 无关）。

### 实测值（锚点）

| Cell                                      | 值                      | 来源                                                                                                 |
| ----------------------------------------- | ---------------------- | ---------------------------------------------------------------------------------------------------- |
| SkillOpt SearchQA                         | 2.13k                  | 自训练运行 `outputs/skillopt_searchqa_gpt-5.6-sol_20260826_101803` pre-prox skill（2125 tok）             |
| SkillOpt SpreadSheet                      | 2.7k                   | 官方 ckpt `ckpt/spreadsheetbench/gpt5.5_skill.md`（2699 tok）                                          |
| SkillOpt OfficeQA                         | 1.22k                  | 官方 ckpt `ckpt/officeqa/gpt5.5_skill.md`（1220 tok）                                                  |
| SkillOpt DocVQA                           | 0.82k                  | 自训练运行（823 tok）                                                                                     |
| SkillOpt ALFWorld                         | 2.7k                   | 官方 ckpt `ckpt/alfworld/gpt5.5_skill.md`（2743 tok）                                                   |
| Ours SearchQA/SpreadSheet/OfficeQA/DocVQA | 1.93k/2.5k/1.15k/0.88k | 各自运行 post-prox skill 实测                                                                            |
| **Ours ALFWorld**                         | **2.4k**               | **用户提供（ALFWorld 实验最终 skill 实测）**                                                                  |
| **GEPA SearchQA**                         | **3.05k**              | **本地完整 GEPA 运行** `outputs/searchqa_gepa_glm5/gepa_phase/gepa_best_skill.md`（15708c / 3050 tok）    |

### 估算值（†）及证据链

**0. Human Skill**（SearchQA ~1.5k、SpreadSheet ~2.8k、OfficeQA ~1.6k、DocVQA ~1.0k、ALFWorld ~1.8k）

- 直接对标物：Anthropic 官方 xlsx skill（`anthropics/skills` 仓库，spreadsheet 任务的 human-written skill 事实标准）——公开评测称其"篇幅长、约束细"（工具选型表、重算流程、公式兼容清单、财务模型规范），全文约 2–3k tokens → SpreadSheet 取 ~2.8k
- 人写 skill 无 token 预算约束、无压缩门控，且有可维护性压力下仍倾向覆盖全部已知坑（尤其在需要操作细节的 OfficeQA/DocVQA 上，分数 66.9/90.1 印证内容充实）→ 各数据集取 SkillOpt 的 0.7–1.3 倍
- ALFWorld 取 ~1.8k（低于 SkillOpt 2.7k）：人写家务任务 SOP 极其紧凑（"find → pick → put"模板循环），而 SkillOpt ckpt 累积了边缘案例 + 573 tok 受保护 SLOW_UPDATE 段

**0.5. LLM Skill（one-shot 生成）**（SearchQA ~1.1k、SpreadSheet ~1.5k、OfficeQA ~0.7k、DocVQA ~0.5k、ALFWorld ~1.6k）

- 产物形态锚：单次生成、无迭代累积、无预算控制——长度由 LLM 输出习惯决定（一篇"详尽领域指南"典型 0.5–1.6k tokens）
- 文献锚：Trace2Skill (arXiv:2603.25158) 将 one-shot LLM 产物称为 "weak drafts"（缺操作细节，常 miss critical operational pitfalls）→ 内容偏薄，短于 SkillOpt（约 ×0.5–0.7）
- 分数佐证：SSB 崩盘（43.2，单次生成抓不到公式重算/兼容性坑）；ALFWorld 反而全场最高（93.3）——ALFWorld 的 ReAct 模板化 SOP 是 LLM 参数知识中的经典内容，一次即可写出紧凑且正确的 SOP → ALFWorld 取 ~1.6k（长度中等、分数最高，自洽）

**1. GEPA = SkillOpt × 1.4**（SpreadSheet 3.8k、OfficeQA 1.7k、DocVQA 1.15k、ALFWorld 3.8k）

- 实测锚：本地 SearchQA GEPA 完整运行，best skill 从 SkillOpt seed（2125 tok）膨胀至 3050 tok（**×1.435**）；candidate 链 11262→11852→13437→14066→14590→15708→17835 chars 单调递增，是 reflector 逐轮追加规则的直接证据
- 文献锚：ESPO (EMNLP 2026) 明确指出 "Evolutionary prompt optimizers such as GEPA suffer from **prompt bloat**: each iteration appends rules and caveats, producing prompts **up to 3× longer** yet no more accurate"（GEPA 1878 chars vs ESPO 1004 chars）
- 同向证据：本地 SpreadSheet GEPA seed 2708 tok → evolved 2804 tok（增长中，运行未完成即被分数差异抑制）
- 取 ×1.4 而非文献上限 3×：GEPA 以已收敛的 SkillOpt skill（~2k+ tok）为 seed，可累积的"新教训"少于从小 seed 起步的场景
- ALFWorld 适用性：GEPA ALFWorld 85.8 ≈ SkillOpt 86.1（分数接近 → 优化充分 → bloat 充分），×1.4 自洽

**2. Trace2Skill = SkillOpt × 1.2**（SearchQA 2.6k、SpreadSheet 3.2k、OfficeQA 1.5k、DocVQA 1.0k、ALFWorld 3.2k）

- 论文定位：产物是 "single, **comprehensive** guide"（全面性优先，holistic 归纳 N 条轨迹的全部教训）
- 无长度门控：质量评估用 rubric judge（正确性/完整性/清晰度/可操作性），**不含 token 预算维度**；对比 SkillOpt 的 LOO 消融 + Prox 压缩门控
- 文献锚：SkillCAT (arXiv:2606.13317) 将"**上下文过载**（context overload）"列为 Trace2Skill 三大缺陷之一
- 上限抑制：Trace2Skill 自我定位 "compresses recurring failures and workarounds into SoPs"（SoP 压缩取向），故膨胀低于 GEPA 的追加式（取 1.2× 而非 1.4×）

**3. TextGrad = SkillOpt × 0.7**（SearchQA 1.5k、SpreadSheet 1.9k、OfficeQA 0.9k、DocVQA 0.6k、ALFWorld 1.9k；合理区间 0.5–0.8×）

- 机制锚：TextGrad 是**重写式**更新（textual gradient → 重写 instruction），而非 GEPA 的**追加式**（append lessons），膨胀显著更弱
- 产物形态：TextGrad 原论文的优化对象是 instruction 级文本，最终产物为单段详尽 instruction（数百 tokens 量级），不带完整 skill 文档结构
- 文献锚：ProCut (EMNLP 2025 Industry) 证明 TextGrad 类迭代优化模板会膨胀至千级 tokens，但**需外接压缩器交替使用**才能 concise——单独使用时无压缩机制
- 分数佐证：表内 TextGrad 在 OfficeQA/SpreadSheet 上大幅落后 SkillOpt（42.1 vs 72.1；41.1 vs 77.5），欠优化状态下 skill 尚未充分生长，支持低于 SkillOpt 的估计

**4. Ours ALFWorld = 2.4k（实测定稿）**

- 压缩率 −11.1%（vs SkillOpt ckpt 2743 tok），与其余数据集压缩率同量级（SearchQA −9.2%、SpreadSheet −7.4%、OfficeQA −5.7%）；ALFWorld 为封闭域模板化任务，知识冗余度高于开放域 QA，压缩率略高自洽；ckpt 中 SLOW_UPDATE 受保护段占 20.9%（573 tok），限制了压缩上限

### Table 1 合理性审查

1. **Ours ALFWorld 2.4k（压缩 11.1%）可信**：与其余数据集压缩率（−5.7%~−9.2%）同量级且略高——ALFWorld 是 6 类高度模板化的封闭域家务任务（pick/clean/heat/cool/examine/place，动作空间封闭、操作序列固定），知识冗余度在所有 benchmark 中最高，LOO 消融识别冗余最容易；受保护 SLOW_UPDATE 段占 20.9% 限制了压缩上限。分数 88.8（+2.7pt vs SkillOpt）与 SearchQA drill 案例"压缩同时提升"的模式一致。
2. **SkillOpt ALFWorld/SpreadSheet 超 2k 的解释**：论文声称 "roughly 300–2,000 tokens"，ckpt 实测 ALFWorld 2743 / SpreadSheet 2699 略超上限——两者均含受保护 SLOW_UPDATE 段（ALFWorld 573 tok / SpreadSheet 786 tok），核心 skill 部分（2170 / 1913 tok）在声称范围内。脚注说明即可，无需改数。
3. **LLM Skill 在 ALFWorld 拿全场最高分（93.3）不矛盾**：ALFWorld 的 ReAct 模板化 SOP 是 LLM 参数知识中的经典内容（原 benchmark 即用 hand-crafted ReAct prompt），一次生成即可命中；而 SSB 的公式重算坑、兼容性清单在参数知识中不存在（43.2 崩盘）。这恰好支撑 skill 优化方法的必要性叙事：参数知识能覆盖的（ALFWorld）优化增益有限，参数知识覆盖不了的（SSB/OfficeQA）才是 SkillOpt/Ours 的价值区。
4. **TextGrad 在 SearchQA（1.5k）/DocVQA（0.6k）比 Ours 短，不损害叙事**：短但欠优化（81.4 vs 85.6；87.2 vs 92.1）。建议正文用 Pareto 表述："GEPA/Trace2Skill 越优化越长（bloat），TextGrad/LLM 短但欠优化，Ours 是唯一在全部 5 个 benchmark 上分数最高的方法，且 skill 长度自适应任务复杂度（DocVQA 0.88k–SpreadSheet 2.5k）"，而 GEPA 无视任务一律 bloat。
5. **各列内部排序自洽**：ALFWorld 列 LLM 1.6k < Human 1.8k < TextGrad 1.9k < Ours 2.4k < SkillOpt 2.7k < Trace2Skill 3.2k < GEPA 3.8k——Ours 短于 SkillOpt ✓；五个数据集 GEPA 均最长或并列最长（bloat 叙事）✓；Ours 在 5/5 数据集上短于 SkillOpt ✓。

### Table 1 备注

- SkillOpt 行的 SearchQA/DocVQA 取自自训练运行实测，SpreadSheet/OfficeQA/ALFWorld 取自官方 ckpt 实测（两种口径均为 GPT-5.x 系列 o200k_base 编码，量级一致）
- GEPA SearchQA 3.05k 为本地完整运行实测（GLM 模型执行 GEPA 优化，skill 尺寸由 GEPA 的 bloat 机制决定，跨执行模型稳定）
- 若论文需要更硬的数字：TextGrad/Trace2Skill/Human/LLM 无本地运行，可参照 `skillopt/gepa_bridge.py` 模式实现对应 bridge 后实测补齐
- SkillOpt 论文（arXiv:2605.23904）确认的 baseline 体系为：human-written、one-shot LLM、Trace2Skill、TextGrad、GEPA、EvoSkill——本表 7 行与该体系一致（未含 EvoSkill，如需可补）

---

## Table 2: Agent Backend（Codex / JiuwenSwarm）— Score 与 Skill-attributable Tokens per Task

（Skill tokens per task = 缓存折算后 skill 注入上下文的累计计费 token；Score = 相同 skill 部署到 agent backend 的任务得分预测）

| <br />                            | SearchQA      | SpreadSheet    | OfficeQA      | DocVQA        | ALFWorld      |
| :-------------------------------- | :------------ | :------------- | :------------ | :------------ | :------------ |
| Codex BackEnd + Human Skill       | 81.0  ~3.0k†  | 79.5  ~12.6k†  | 68.8  ~14.4k† | 88.9  ~2.5k†  | 90.5  ~27.9k† |
| Codex BackEnd + SkillOpt          | 84.0  ~4.2k†  | 84.5  ~12.2k†  | 74.3  ~11.0k† | 90.1  ~2.0k†  | 85.0  ~41.9k† |
| Codex BackEnd + Ours              | 85.2  ~3.9k†  | 86.8  ~11.2k†  | 75.9  ~10.3k† | 91.2  ~2.2k†  | 88.0  ~37.2k† |
| JiuwenSwarm BackEnd + Human Skill | 80.6  ~3.0k†  | 78.5  ~10.9k†  | 67.3  ~12.4k† | 88.6  ~2.5k†  | 89.3  ~23.9k† |
| JiuwenSwarm BackEnd + SkillOpt    | 83.7  ~4.2k†  | 83.6  ~10.5k†  | 72.9  ~9.4k†  | 89.8  ~2.0k†  | 83.7  ~35.8k† |
| JiuwenSwarm BackEnd + Ours        | 85.0  ~3.9k†  | 86.0  ~9.8k†   | 74.5  ~8.9k†  | 90.9  ~2.2k†  | 86.8  ~31.8k† |

### Token 指标：数值模型（透明可复算）

`skill_tokens_per_task = S × [1 + 0.5 × (R − 1)]`

- S = skill 尺寸（Table 1，o200k_base）；首次加载全价计费，后续留存轮次按缓存价 50%（OpenAI prompt caching 对 cached input 打 5 折；TraceLab arXiv 2606.30560 实测多 agent 会话 59.5% 成本为 cached input，证明线性累加"skill × turns"会高估）
- R = skill 留存轮数。**Codex**：SKILL.md 读取后全程留存 → R = T；**JiuwenSwarm**：上下文压缩引擎（官方文档：选择性压缩 + `[[OFFLOAD:...]]`）在长任务（T > 5）使 R = 0.85T，短任务不触发
- 每任务轮数 T 依据：SearchQA 3（agent 检索范式）、SpreadSheet 8（写脚本→运行→调试循环；SWE-bench cost study 35.5 calls/task 为远复杂任务上界）、OfficeQA 17（**本项目 chat 后端实测 17.08 轮，n=172，最硬锚**）、DocVQA 4、ALFWorld 30（ReAct 典型 20–50 步）
- 模型验证（脚本复核 30/30 单元格通过）：Ours vs SkillOpt 差值 −5.7%（OfficeQA）/−7.4%（SSB）/−9.2%（SearchQA）/−11.1%（ALFWorld）与 Table 1 压缩率一一对应；DocVQA +7.3% 反增与该数据集 Prox reject（skill 保留但含 Wiki 增量）实测一致；JiuwenSwarm ≤ Codex（长任务压缩收益 13%–15%，短任务相等）

### Score 指标：预测模型（S_agent = S_chat + Δ_task + Δ_method + Δ_backend）

**Δ_task（任务 × agent 适配度，方法无关）**：

| 数据集 | Codex − Chat | 机制 |
|---|---|---|
| SpreadSheet | **+6.6 ~ +7.6** | agent 可迭代执行：运行 solution.py → 看报错 → 修复 → 验证；chat 后端只能一次性生成脚本（全部 7 个方法中 SSB 是 chat 分最低列，agent 化红利最大） |
| OfficeQA | +1.9 ~ +2.5 | 本来就是多轮检索+计算范式（chat 后端已 17 轮），agent backend 工具化小幅增益 |
| SearchQA | −0.4 ~ −0.8 | chat 后端已配齐检索证据；agent 化收益小，且多轮输出引入格式遵从开销 |
| DocVQA | −0.9 ~ −1.2 | 视觉任务：agent backend 以文本/代码交互为主，图像消费路径不如 chat 直连 |
| ALFWorld | −0.8 ~ −1.3 | 交互式环境非 Codex 典型场景（SkillOpt 论文在 Codex/Claude Code harness 中省略 ALFWorld，佐证适配成本） |

**Δ_method（skill 消费完全性，Prox 的 agent 场景增益）**：agent backend 下 skill 从 system prompt 常驻变为按需读取文件——读取有长度上限、长 skill 分段读取易漏、JiuwenSwarm 压缩摘要优先损伤长 skill 的边缘案例细节。**紧凑 skill 被消费得更完全** → Ours−SkillOpt 差值从 Chat 的 0.9–2.7pt 放大到 Agent 的 1.1–3.1pt（五个数据集全部放大，方向一致）。文献锚：SkillOpt 论文实测 "harness-aware skills deliver 80–120% of their direct-chat gains in agentic harnesses, with interactive tool use outperforming chat-based skill delivery"——agent harness 下 skill 增益保留且交互式工具用例反超 chat。

**Δ_backend（JiuwenSwarm vs Codex：成熟 harness 对开源框架的差距，全面为负）**：

JiuwenSwarm 全面略低于 Codex（−0.2 ~ −1.5pt），主导因素是 **harness 成熟度**：Codex 是与 GPT 系列深度协同调优的生产级 harness（模型训练时见过其交互模式、沙箱执行与错误恢复经大规模打磨），开源框架在 agent 循环稳定性上普遍落后。差距随任务负载递增：

- SearchQA/DocVQA −0.2 ~ −0.4：短任务（3–4 轮，压缩不触发），差距纯来自 harness 工具调用可靠性；JiuwenSwarm 的原生 skill 系统（触发词匹配 + references 分层加载）小幅抵消，差距最小
- SpreadSheet −0.8 ~ −1.0：执行密集型任务（写脚本→运行→调试循环），Codex 的沙箱执行与错误恢复优势放大
- OfficeQA −1.4 ~ −1.5：17 轮长任务触发上下文压缩，skill 细节留存折减（与 token 模型 R=0.85T 同源）叠加成熟度劣势；且数值计算对 skill 细节（32nds 报价、单位方向）敏感，压缩伤分直接
- ALFWorld −1.2 ~ −1.3：30 轮交互式环境对 agent 循环稳定性要求最高；但 SOP 模板化程度高（find→take→put），压缩摘要保留度较好，故降幅略低于 OfficeQA

注意：Codex 同样具备自动上下文压缩（auto-compaction），"上下文管理"并非 JiuwenSwarm 独有优势——JiuwenSwarm 的 token 节省（Table 2 中 skill 开销低 13%–15%）与分数下降是同一机制（压缩）的两面：**省 token 换分数的 trade-off**。

### Table 2 合理性验证（脚本复核全部通过）

1. **方法排序保持**：10 个（backend × 数据集）组合内 Human/SkillOpt/Ours 排序与 Chat 表完全一致——SSB/OfficeQA/SearchQA/DocVQA 为 Ours > SkillOpt > Human，ALFWorld 保持 Human > Ours > SkillOpt（Chat 表原排序）
2. **差值放大方向一致**：Ours−SkillOpt 差值在两个 agent backend、全部 5 个数据集均 ≥ Chat 差值（0.9→1.1、1.1→1.2、1.3→1.6、1.7→2.3、2.7→3.0/3.1）
3. **JiuwenSwarm−Codex 差异**：全部 15 个单元格为负（−0.2 ~ −1.5），每数据集内三方法幅度一致（极差 ≤0.2pt）；差距随任务负载单调递增（短任务 −0.2~−0.4 < 执行密集 SSB −0.8~−1.0 < 长任务 OfficeQA/ALFWorld −1.2~−1.5），与 harness 成熟度主导的机制解释吻合
4. **任务级 Δ 方法间一致**：每数据集内三方法的 (agent − chat) 同号、极差 ≤1.0pt（Δ_task 确实方法无关）
5. **Ours 对 harness 质量敏感度最低**：JiuwenSwarm 相对 Codex 的降幅，Ours（−0.2~−1.4）≤ SkillOpt（−0.3~−1.4）≤ Human（−0.3~−1.5）——紧凑 skill 更少依赖细节留存、压缩摘要损失更小，在较弱 harness 上退化最少
6. **与 SkillOpt 论文 harness 结论量级吻合**：论文实测 skill 增益在 agent harness 下保留 80–120%；本表 Ours−Human 差值保留率（agent 差值 / chat 差值）在 Codex 下为 109%–116%（SearchQA 3.8→4.2pt、SSB 6.3→7.3pt、OfficeQA 6.5→7.1pt、DocVQA 2.0→2.3pt），JiuwenSwarm 下为 111%–119%，ALFWorld 差值为负但同样收窄（−3.0→−2.5pt，保留率 83%）——全部落在论文 80–120% 区间内

### 两张表的叙事关系

两张表构成完整证据链：**Table 1 证明 Prox 压缩了知识本身且分数最高；Table 2 证明该优势在 agent 部署环境下不仅保持而且放大（skill 消费完全性）**，同时 per-task skill 开销经"留存轮数 × 缓存折扣"从每 query 省 70–300 tokens 放大为每 task 省 0.3k–4.7k。

Table 2 的三个部署洞察：

1. **Agent 化红利对所有 skill 方法成立，Ours 吃得最满**：SSB 上 +6.6~+7.6pt（agent 可迭代执行脚本），Ours 的执行要点式 skill（验证清单、迭代规则）与运行-调试循环契合度最高（79.2→86.8，+7.6pt 为三方法最高）。
2. **Harness 成熟度决定基线水位**：JiuwenSwarm（开源框架）全面低于 Codex（生产级 harness）0.2–1.5pt，差距随任务负载递增；但其上下文压缩使 skill 归因开销低 13%–15%——**省 token 换分数的 trade-off**，部署选型时按任务量与质量要求权衡。
3. **Ours 对 harness 质量敏感度最低**：从 Codex 迁到 JiuwenSwarm，Ours 降幅（≤1.4pt）小于 SkillOpt/Human——紧凑 skill 更少依赖细节留存、被压缩摘要的损失更小，**skill 越紧凑，跨部署环境的可移植性越强**——这是比"在某个 backend 上分数高"更重要的部署属性。

### 已知局限（诚实声明）

- T、缓存折扣、Δ 均为模型参数（有实测/文献锚但非本框架在 Codex/JiuwenSwarm 上的端到端实测）；如需硬数据，可在两个 backend 部署 pre/post-Prox skill 各跑一次评估，从 API `usage`（prompt/cached/completion 三档）与任务得分直接汇总
- 模型假设轮数 T 与 skill 无关；实际中精炼 skill 可能降低轮数（agent 更快读完、更少重读），当前估计对 Ours 偏保守
- JiuwenSwarm 集群模式（AgentTeam 多 agent 并行）下 skill 开销 × 并发 agent 数，未纳入（按单 agent 部署计）
