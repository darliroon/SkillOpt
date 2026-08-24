现在slow update的原理就是随机选择20个轨迹？然后一起塞给LLM进行反思？
是的，但有一个细节要补全——不是直接塞 20 条轨迹，而是 20 道题 × 2 个技能 = 最多 40 条轨迹 。

## 完整流程（trainer.py:2170-2250）

## 你的描述校准

你说的 实际 随机选择 20 个轨迹 随机抽 20 道题 ，每题 2 条轨迹（prev + curr），最多 40 条 一起塞给 LLM 反思 对，一次 LLM 调用，40 条轨迹全量拼进 prompt，按类别分组排版

| 你的观点        | 实际                                       |
| :---------- | :--------------------------------------- |
| 随机选择 20 个轨迹 | 随机抽 20 道题 ，每题 2 条轨迹（prev + curr），最多 40 条 |
| 一起塞给 LLM 反思 | 对，一次 LLM 调用，40 条轨迹全量拼进 prompt，按类别分组排版    |

## 为什么 officeqa 会炸

officeqa 单条轨迹可达 66k 字符（24 轮 × 4 工具的 read/grep 输出原样进 prompt）。20 道题里只要混进几道长题：

- 4 道长题 × 2 = 8 条 × 66k ≈ 528k 字符 ≈ 132k tokens
- 加上其余 16 道题（中位 10k 字符 × 32 条 ≈ 320k 字符 ≈ 80k tokens）
- 总计 ≈ 212k tokens ，逼近 272k 上限
- 碰到一道 90k+ 字符的超长题就直接超限崩溃
  源码作者设计 slow\_update\_samples: 20 时大概率假设的是短轨迹数据集（spreadsheetbench 单轮 codegen 轨迹就几百字符，20 题 × 2 = 40 条全量才几 k tokens），没料到 officeqa 这种 24 轮工具调用的长轨迹场景。

## 调小的代价

把 slow\_update\_samples 从 20 调到 8：

- token 安全 ：8 题 × 2 = 16 条轨迹，即使全是最长题也 \~132k tokens，安全
- 信息量损失 ：optimizer 反思时能看到的"对比样本"从 20 对降到 8 对，类别覆盖变稀（4 类各 2 对 vs 4 类各 5 对），反思质量可能下降
- 但这是源码预留的旋钮 ，作者知道这个 trade-off，把决策留给用户
  所以 officeqa 上调到 8 是符合源码设计意图的最小侵入解法。要我帮你把 officeqa 的 default.yaml 里 slow\_update\_samples 改成 8，然后量一下实际 token 分布吗？

<br />

<br />

<br />

我大概有一个想法，就是我们按照类别重要性会有个排序，如果超限了就逐步去除最不重要的直到成功

好思路——这就是"软上限 + 重要性驱逐"策略。开干前先把几个设计点定清楚，避免再走偏。

## 设计要点确认

### 1. 重要性排序（继承源码既有优先级）

源码 slow\_update.py:263-268 已经定了：

剔除顺序（从先到后）： stable\_success 轨迹(本就无) → improved → persistent\_fail → regressed

### 2. 类内剔除顺序

同一类里多条轨迹，删哪条？三个选项：

策略 优点 缺点 长轨迹优先删 （推荐） 每次省的 token 最多，收敛最快 长题可能恰恰是难点，被优先挤出 按信息量删（hard 差距小的先删） 保留信号最强的 hard 差距小≠信息少 随机删 简单 不可控

我倾向 长轨迹优先删 ——理由是：长轨迹在 officeqa 里通常是 read 了超大文件的题，optimizer 看这种超长 obs 也提炼不出比短题更多的"技能级"反思；而且收敛快，避免删 10 条才省出预算。

### 3. 被剔除的题怎么办

保留 metadata，省略轨迹 ：被剔除的题不直接消失，而是改成

让 optimizer 知道"这些题也存在且失败"，只是没看到详细过程。比直接删掉信息量大。

### 4. token 上限值

源码默认 optimizer\_max\_completion\_tokens 留 64000 给输出。gpt-5.2 上下文 272k。安全上限 = 272k - 64k(输出) - 系统/skill 大约 8k = \~200k tokens 。

我倾向写死 200\_000 常量，不配置化（上次教训）。如果你要调，单独说。

### 5. tokenizer

用 tiktoken （OpenAI 标准库，skillopt 已依赖）。yibuapi 中转的模型可能不是原生 OpenAI，但 cl100k\_base 估算误差 < 10%，200k 上限留 10% 余量足够。

### 6. fallback

删到每类只剩 1 条还超限（极端情况）→ 报错并打印当前 token 数，让人去调 slow\_update\_samples 。不做截断——避免重蹈覆辙。

### 7. 实现位置

只在 format\_comparison\_text 内部，不动 build\_comparison\_pairs / \_read\_trajectory / \_clip\_text 。 build\_comparison\_pairs 仍然全量生成所有 pair（保留 JSON 落盘的完整性），只是格式化成 text 时按预算裁。

## 流程伪代码

```
def format_comparison_text(pairs):
    by_cat = group(pairs)
    text_blocks = build_all_blocks(by_cat)  # 全量拼
    total = tiktoken_count(text_blocks)
    if total <= BUDGET:
        return text_blocks
    
    # 按优先级从低到高逐条剔除轨迹（保留 metadata）
    for cat in [improved, persistent_fail, regressed]:
        # 类内按轨迹长度降序排
        for entry in sorted(by_cat[cat], key=len(traj), 
        reverse=True):
            entry.omitted = True
            text_blocks = rebuild()
            total = tiktoken_count(text_blocks)
            if total <= BUDGET:
                return text_blocks
    
    raise ContextOverflow(total, BUDGET)
```

确认这几条后我就动手。重点确认： 类内剔除顺序选"长轨迹优先删" ， token 上限写死 200k 不配置化 ， 剔除后保留 metadata ——这三条对吗？
