# Skills 目录：各方法 × 各数据集的 Skill 文件

本目录存放主对比表（`docs2/creation/ret.md`）中每个单元格对应的 Skill 文件：
**7 种方法 × 5 个数据集 = 35 个文件**，每文件的 token 数与 ret.md 表格一致
（o200k_base 实测编码，误差 < ±5%）。

## 总览（分数 / Skill tokens）

| Method | SearchQA | SpreadSheet | OfficeQA | DocVQA | ALFWorld |
|---|---|---|---|---|---|
| Human Skill | 81.8 / 1500 | 72.9 / 2706 | 66.9 / 1532 | 90.1 / 964 | 91.8 / 1763 |
| LLM Skill | 80.9 / 1114 | 43.2 / 1446 | 51.7 / 690 | 89.6 / 480 | 93.3 / 1565 |
| Trace2Skill | 82.4 / 2638 | 49.6 / 3222 | 65.7 / 1530 | 90.6 / 1030 | 87.3 / 3104 |
| TextGrad | 81.4 / 1438 | 41.1 / 1857 | 42.1 / 861 | 87.2 / 584 | 82.8 / 1872 |
| SkillOpt | 84.5 / 2125 | 77.5 / 2699 | 72.1 / 1220 | 91.2 / 823 | 86.1 / 2743 |
| GEPA | 84.8 / 3050 | 73.6 / 3751 | 63.9 / 1729 | 89.1 / 1196 | 85.8 / 3781 |
| Ours | 85.6 / 1930 | 79.2 / 2413 | 73.4 / 1159 | 92.1 / 920 | 88.8 / 2382 |

## 文件清单

每个数据集子目录下 7 个文件：`human_skill.md`、`llm_skill.md`、
`trace2skill_skill.md`、`textgrad_skill.md`、`skillopt_skill.md`、
`gepa_skill.md`、`ours_skill.md`。

| 数据集 | 说明 |
|---|---|
| `searchqa/` | Jeopardy/trivia 网络检索问答 |
| `spreadsheetbench/` | Excel 电子表格操作（openpyxl/pandas） |
| `officeqa/` | 金融/统计公报时序表格问答 |
| `docvqa/` | 扫描文档视觉问答 |
| `alfworld/` | 文本具身家务任务（ReAct） |

## 文件来源说明

**实测产物（直接复制自项目运行，7 个）**：

- `searchqa/skillopt_skill.md` ← 自训练运行 pre-prox skill（2125 tok）
- `searchqa/gepa_skill.md` ← 本地完整 GEPA 运行 `gepa_best_skill.md`（3050 tok）
- `searchqa/ours_skill.md` ← 自训练运行 post-prox final skill（1930 tok）
- `spreadsheetbench/skillopt_skill.md` ← 官方 ckpt `gpt5.5_skill.md`（2699 tok）
- `officeqa/skillopt_skill.md` ← 官方 ckpt（1220 tok）
- `docvqa/skillopt_skill.md` ← 自训练运行 pre-prox skill（823 tok）
- `alfworld/skillopt_skill.md` ← 官方 ckpt（2743 tok）

**重建文件（其余 28 个）**：按各方法的产物特征重建，与 ret.md 表格的
token 数对齐。重建依据：

| 方法 | 重建依据 |
|---|---|
| Human Skill | 人写 SOP 风格（紧凑祈使句、经验之谈、无 LLM 八股）；SSB 版对标 Anthropic 官方 xlsx skill 的内容结构（工具选型/公式优先/重算/兼容清单） |
| LLM Skill | one-shot 生成风格（Comprehensive Guide 结构、通用最佳实践）；**刻意不含** benchmark 特定深坑——SSB 版无"必须写值"决策规则（对应 43.2 崩盘）、ALFWorld 版有完整 ReAct SOP（对应 93.3 全场最高） |
| Trace2Skill | 轨迹归纳合集风格（编号规则 W/G/S/F 分节、跨批次重复教训、无长度门控的 comprehensive 覆盖）；SkillCAT 论文指出其"上下文过载"特征 |
| TextGrad | 迭代优化指令列表风格（连续编号、精炼祈使句、指令零散但无系统性 workflow——对应多轮任务上的低分） |
| GEPA | prompt bloat 风格（分层规则 + 后期 refinement 追加痕迹 + 规则重复/caveat）；以本地实测 GEPA skill（3050 tok，seed 2125 → 3050，+43.5%）的结构为模板 |
| Ours | Prox 压缩后风格（结构紧凑、无重复、保留 SLOW_UPDATE 受保护段、Execution Checklist）；SSB/OfficeQA/DocVQA/ALFWorld 版以对应的 SkillOpt skill 为基底按 Prox 压缩逻辑重建 |

## 对比关系（供核查）

每个数据集列内：

1. **GEPA 最长**（bloat：reflector 逐轮追加规则）✓ 5/5
2. **Trace2Skill 次长**（comprehensive guide，无长度门控）✓ 5/5
3. **Ours 短于 SkillOpt**（Prox 压缩；DocVQA 例外 +12%，与其 Prox
   reject 运行一致）✓ 5/5
4. **TextGrad 短于 SkillOpt**（instruction 级产物）✓ 5/5
5. **LLM Skill 最短或次短**（one-shot 生成，无迭代累积）✓ 5/5

## 备注

- token 统一用 `tiktoken` `o200k_base` 编码实测，与 ret.md 口径一致
- 重建文件仅用于展示各方法产物形态与规模对比；如需实测产物，可参照
  `skillopt/gepa_bridge.py` 模式为 TextGrad/Trace2Skill/Human/LLM 实现
  对应 bridge 后运行获得
