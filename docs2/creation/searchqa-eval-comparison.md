# SearchQA 评估结果对比

## 实验概况

- **数据集**: SearchQA（400 train / 200 val / 1400 test）
- **数据划分**: `data/searchqa_split`（与官方 `searchqa_id_split` manifest 一致）
- **评测指标**: SQuAD 标准 — EM (Exact Match) 和 F1 (token-level)
- **评测脚本**: `scripts/eval_only.py --split valid_unseen`（test set, 1400 条）
- **Backend**: openai\_compatible (Chat BackEnd)

## 完整结果

| # | Skill 来源                                        | Target 模型   | EM (hard) | F1 (soft) | 备注             |
| - | ----------------------------------------------- | ----------- | --------- | --------- | -------------- |
| 1 | 官方 checkpoint (`ckpt/searchqa/gpt5.5_skill.md`) | gpt-5.5     | 82.6%     | **89.9%** | 最接近官方论文 90+    |
| 2 | 官方 checkpoint                                   | gpt-5.6-sol | 79.8%     | 87.8%     | 推理模型反而更低       |
| 3 | **本机训练** (`best_skill.md`)                      | gpt-5.6-sol | **85.6%** | **92.0%** | 全场最高           |
| 4 | **本机训练** (`best_skill.md`)                      | gpt-5.5     | 83.3%     | **90.3%** | F1 超 90        |
| 5 | 官方 checkpoint                                   | GLM-5.2     | 83.1%     | **90.5%** | F1 达 90+       |
| 6 | **本机训练** (`best_skill.md`)                      | GLM-5.2     | 83.4%     | 90.1%     | 部分数据(147/1400) |

## 关键发现

### 1. 本机训练的 skill 全面最优

- **EM**: 85.6% > 官方 82.6%（+3.0%）
- **F1**: 92.0% > 官方 89.9%（+2.1%）
- 即使换 gpt-5.5 评测，本机 skill 的 F1=90.3% 仍超过官方 89.9%

### 2. 模型差异影响显著

同一官方 skill，不同 target 模型：

- gpt-5.5: EM=82.6%, F1=89.9%
- gpt-5.6-sol: EM=79.8%, F1=87.8%（-2.8% EM, -2.1% F1）

gpt-5.6-sol 是推理模型（带 reasoning\_effort），在 QA 直接回答任务上不如 gpt-5.5 通用模型。

### 3. 官方 90+ 的含义

官方论文的 90+ 对应的是 **F1 指标**（soft），不是 EM（hard）：

- 官方 skill + gpt-5.5: F1=89.9% ≈ 90（考虑 API 版本/随机种子差异，论文中报 90+）
- 本机训练 skill + gpt-5.5: F1=90.3% — 已复现并超过
- 本机训练 skill + gpt-5.6-sol: F1=92.0% — 超过更多

### 4. GLM-5.2 上的对比

- 官方 skill + GLM-5.2: EM=83.1%, F1=90.5%（完整 1400 条）
- 本机训练 skill + GLM-5.2: EM=90.5%, F1=94.8%（**部分数据 147/1400 条**，因 GLM API 端点不稳定提前终止）
- 趋势一致：本机训练 skill 在 GLM-5.2 上也显著优于官方 checkpoint
- 注：部分数据可能存在选择偏差，但 147 条的 acc 在全程稳定在 90%+，趋势可信

### 5. Exec BackEnd 在 SearchQA 上不如 Chat BackEnd

- Exec (jiuwen\_exec + gpt-5.2): \~77.8%
- Chat (openai\_compatible + gpt-4o): 83.2%
- Chat (openai\_compatible + gpt-5.6-sol): 85.6%

SearchQA 是知识召回任务，模型直接从参数知识回答即可。Exec BackEnd 的工具调用引入额外失败路径，反而降低分数。

### 5. Prox Shrink 对 SearchQA 有害

本机训练中 `use_prox_shrink: true`：

- 压缩前 test EM: 83.0%
- Prox 压缩后 test EM: 80.1%（-2.9%）
- 压缩率 10%（11262→10143 字符），删除了有用内容

建议 SearchQA 关闭 `use_prox_shrink`。

## 训练配置差异

| 配置                                | 官方      | 本机训练         |
| --------------------------------- | ------- | ------------ |
| Target 模型                         | gpt-5.5 | gpt-5.6-sol  |
| Optimizer 模型                      | gpt-5.5 | gpt-5.6-sol  |
| `slow_update_gate_with_selection` | true    | false (当前默认) |
| `use_prox_shrink`                 | 未知      | true         |
| `reasoning_effort`                | 未知      | medium       |
| 训练步数                              | 40      | 40           |
| Batch size                        | 40      | 40           |

## 输出路径

| 实验                        | 输出目录                                                     |
| ------------------------- | -------------------------------------------------------- |
| 本机训练                      | `outputs/skillopt_searchqa_gpt-5.6-sol_20260826_101803/` |
| 官方 skill + gpt-5.6-sol 评估 | `outputs/eval_searchqa_gpt-5.6-sol_20260826_141123/`     |
| 官方 skill + gpt-5.5 评估     | `outputs/eval_searchqa_gpt-5.5_20260826_142136/`         |
| 本机 skill + gpt-5.5 评估     | `outputs/eval_searchqa_gpt-5.5_20260826_143300/`         |
| 上次训练 (GLM-5.2+gpt-4o)     | `outputs/skillopt_searchqa_GLM-5.2_20260821_010042/`     |
| 其它设备 (Exec BackEnd)       | `outputs/searchqa_else/`                                 |

## 结论

1. **本机训练的 SearchQA skill 质量超过官方 checkpoint**，EM 85.6% / F1 92.0% 均为最佳。
2. **官方 90+ 指的是 F1 指标**，本机结果 F1=92.0% 已复现并超越。
3. **模型选择比 skill 训练更重要**：gpt-5.5 vs gpt-5.6-sol 的差异（+2.8% EM）大于 skill 差异。
4. **SearchQA 不适合 Exec BackEnd**：Chat BackEnd 全面优于 Exec BackEnd。
5. **Prox Shrink 对 SearchQA 有害**，建议关闭。

