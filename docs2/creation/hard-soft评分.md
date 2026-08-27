# 我觉得你之前跑的DocVQA的结果不尽人意，SkillOpt官方跑出来的结果是90+！！！！！、

结果其实是达标的！你看到的是 hard accuracy（精确匹配） ，而官方的 90+ 是 ANLS（软匹配） 

| 指标                 | Baseline (初始skill) | Final (训练后, step 2) | 提升     |
| :----------------- | :----------------- | :------------------ | :----- |
| ANLS (soft)        | 0.8552 (85.5%)     | 0.9261 (92.6%) ✅    | +7.1%  |
| Exact Match (hard) | 0.7273 (72.7%)     | 0.8422 (84.2%)      | +11.5% |

## 完整结果

Selection set (53 val items):

- best step 2: hard= 94.3% , soft(ANLS)= 97.6%
  DocVQA 官方标准指标是 ANLS ，test set 上 92.6% 已达到 90+ 目标。summary.json 里只显示 hard\_acc ，所以你看到 84.2% 以为没达标，实际 ANLS 已经 92.6%。

训练在 step 2 就达到了最佳分数，后续 10 步都没能超越，说明 107 条数据的信号在 step 2 基本用尽。

## 这个soft是怎么计算的？

## Soft (ANLS) 的计算在 evaluator.py 中，是标准 DocVQA ANLS 指标。计算过程：

### 5. hard vs soft 的关系（rollout.py:241-242）

```
result["hard"] = int(anls >= 0.999)  # 精确匹配：ANLS≈1才算对
result["soft"] = anls                 # ANLS连续分：部分匹配也有分
```

###

##

## 为什么 test\_eval\_final 比 test\_eval 好

### 数据对比

| <br />           | Step 2 (best)         | Step 12 (final) |
| ---------------- | --------------------- | --------------- |
| Val (53条) hard   | **0.9434** ← 被选为 best | 0.8868 ← 被拒绝    |
| Val (53条) soft   | 0.9760                | 0.9300          |
| Test (374条) hard | 0.8209                | **0.8422** ← 反超 |
| Test (374条) soft | 0.9221                | **0.9261** ← 反超 |

### 三个原因

1. **Val set 太小（53条）**：1 条 = 1.9% 的差异。Step 2 恰好在 val 上多答对 3 题（50/53 vs 47/53），但在 374 条 test 上这个偶然优势消失了。
2. **Gate 用的是 hard（精确匹配）**：binary 0/1，比 soft（ANLS 连续分）噪声大得多。如果看 val soft：step 2 = 0.9760，step 10 = 0.9610，差距远小于 hard 的差距。
3. **Slow update 积累了跨 epoch 的知识**：Final skill 的 origin 是 `slow_update_epoch_03`，它融合了 4 个 epoch 的 slow update 信号。虽然每步单独在 val 上没超过 step 2，但累积的编辑在更大的 test set 上泛化更好。

这说明 slow\_update 机制在起作用——即使 per-step gate 拒绝了候选，跨 epoch 的知识沉淀仍然提升了 test 表现。

## 修改的文件清单

| 文件                                   | 改动                                           |
| ------------------------------------ | -------------------------------------------- |
| `skillopt/envs/docvqa/dataloader.py` | 修复 `_parse_answers`：用正则替代 `ast.literal_eval` |
| `skillopt/engine/trainer.py`         | 5 处 `summary.json` 写入添加 `soft_acc` 字段        |
| `configs/docvqa/default.yaml`        | `split_dir` 改为 `data/docvqa/splits_10pct`    |
| `scripts/materialize_docvqa.py`      | 新建：从 manifest 物化 10% 子集                      |

