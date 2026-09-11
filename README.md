# Eval 驱动的 Skill 自迭代飞轮

> 深度学习范式下的 Skill 自演技熔炉 —— 借鉴深度学习训练纪律，以**模式沉淀**积经验、以**文本消融**去冗余、以**进化记忆**传策略、以**抗遗忘**守能力，四算子协同驱动 Skill 自演进。

本项目把「技能文档（Markdown）」当作一个被冻结 Agent 的可训练参数来优化：用与深度学习相同的纪律（epoch、minibatch、学习率、验证集门控）反复做 rollout → reflect → aggregate → select → update → gate，但**不修改模型权重**。最终产物是一个紧凑的 `best_skill.md`（通常 300–2000 token），部署时零额外推理开销。

***

## 核心痛点

1. **轨迹经验随用随弃**：每次推理产生大量轨迹，其中蕴含反复出现的错误模式与有效策略，但分析完即被丢弃，无法持久化积累。
2. **技能膨胀与规则矛盾**：重复指令、冲突补丁、错误泛化的解题思路持续堆砌，导致 Skill 无限膨胀与规则互相矛盾。
3. **优化器短视与跨代灾难性遗忘**：反思优化器每次从零开始诊断，缺少跨轮优化策略记忆；同时技能在多轮迭代中容易遗忘已有能力、发生退化，缺少纵向对比纠偏机制。

## 关键技术

| 技术                      | 解决的问题         | 核心模块                                              | 配置开关                                                                      |
| ----------------------- | ------------- | ------------------------------------------------- | ------------------------------------------------------------------------- |
| **轨迹模式沉淀**              | 经验随用随弃        | `skillopt/optimizer/wiki_maintainer.py`           | `optimizer.use_wiki`、`wiki_react_proposer`                                |
| **文本消融算子（Prox Shrink）** | 技能膨胀 / 规则矛盾   | `skillopt/optimizer/prox_shrink.py`               | `optimizer.use_prox_shrink`                                               |
| **进化记忆 + 抗遗忘算子**        | 优化器短视 / 灾难性遗忘 | `slow_update.py`、`meta_skill.py`、`skill_aware.py` | `optimizer.use_slow_update`、`use_meta_skill`、`use_skill_aware_reflection` |
| **过程驱动反思（GEPA）**        | 结果驱动反思的上限     | `skillopt/gepa_bridge.py`                         | `optimizer.use_gepa`                                                      |

1. **轨迹模式沉淀**：采样失败/成功轨迹做根因分析，沉淀为结构化模式，形成「轨迹 / 模式 / 技能」三重架构；模式持久化，skill 回滚时知识仍保留。
2. **文本消融算子**：逐单元量化边际效用（leave-one-out），删除负效用单元并经**验证集门控**，消除多编辑堆砌带来的规则矛盾与技能膨胀。
3. **进化记忆与抗遗忘算子**：从多版本技能、轨迹对比中蒸馏优化器新知识，注入并更新反思 Agent；同时通过 Markov 式邻代对比，提炼纵向指导写入技能文档。
4. **GEPA（过程驱动反思）**：读取完整执行轨迹做步骤级因果分析，在 SkillOpt 训练（Phase 1）后、Prox Shrink（Phase 3）前运行。

## 多执行端

作为目标 Agent（target）可通过多种执行端运行：

| 执行端             | 后端名                             | 说明                                                      |
| --------------- | ------------------------------- | ------------------------------------------------------- |
| **Jiuwen**      | `jiuwen_exec`                   | Jiuwen 执行端，支持Jiuwen-core-rust框架的执行端和Jiuwen Swarm |
| **Codex**       | `codex_exec`                    | Codex CLI 执行端                                           |
| **Claude Code** | `claude_code_exec`              | Claude Code CLI 执行端                                     |
| Cursor          | `cursor_exec`                   | Cursor 执行端                                              |
| Copilot         | `copilot_chat` / `copilot_exec` | GitHub Copilot 后端                                       |

## 支持的基准（环境）

| 环境                     | 配置                                            |
| ---------------------- | --------------------------------------------- |
| ALFWorld               | `configs/alfworld/default.yaml`               |
| DocVQA                 | `configs/docvqa/default.yaml`                 |
| gbrain                 | `configs/gbrain/default.yaml`                 |
| LiveMathematicianBench | `configs/livemathematicianbench/default.yaml` |
| OfficeQA               | `configs/officeqa/default.yaml`               |
| SearchQA               | `configs/searchqa/default.yaml`               |
| SpreadsheetBench       | `configs/spreadsheetbench/default.yaml`       |

***

## 如何运行

### 1. 安装依赖

环境要求：**Python 3.10+**

```powershell
git clone https://github.com/darliroon/SkillOpt.git
cd SkillOpt

# 核心依赖
python -m pip install -r requirements.txt

# WebUI 额外依赖
python -m pip install -e ".[webui]"

# 其它可选 extra（按需）
# python -m pip install -e ".[searchqa]"   # SearchQA 数据物化
# python -m pip install -e ".[alfworld]"   # ALFWorld 基准依赖
```

### 2. 配置环境变量

复制示例文件并填写（WebUI 会自动加载 `.env`）：

```powershell
Copy-Item .env.example .env
```

默认后端为 **OpenAI 兼容接口**（`model.backend: openai_compatible`），核心变量：

```powershell
$env:OPENAI_COMPATIBLE_BASE_URL = "http://your-endpoint/v1"
$env:OPENAI_COMPATIBLE_API_KEY  = "sk-..."
$env:OPENAI_COMPATIBLE_MODEL    = "your-model"
```

> 也可以在 YAML 中直接配置：`model.openai_compatible_base_url` / `openai_compatible_api_key`，并在 `model.optimizer` / `model.target` 里指定优化器与目标模型。二者为空时由泛化后端按默认模型补全。

其它后端环境变量（可选，按所用执行端/模型填写 `.env`）：

- **Azure OpenAI**：`AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_API_KEY` / `AZURE_OPENAI_AUTH_MODE`
- **Claude Code**：安装并登录 `claude` CLI；`ANTHROPIC_API_KEY` 或 CLI 登录态
- **Qwen（vLLM）**：`QWEN_CHAT_BASE_URL` / `QWEN_CHAT_MODEL`
- **MiniMax**：`MINIMAX_BASE_URL` / `MINIMAX_API_KEY`
- **Jiuwen 执行端**：`JIUWEN_MODEL_PROVIDER` / `JIUWEN_API_KEY` / `JIUWEN_API_BASE`（也可在 YAML `env.jiuwen_exec_*` 下配置）

### 3. 运行主程序

**训练**（入口：`scripts/train.py`，必填 `--config`）：

```powershell
python scripts/train.py --config configs/searchqa/default.yaml
```

通过 `--cfg-options` 覆盖任意配置项（`section.key=value`），例如：

```powershell
python scripts/train.py --config configs/searchqa/default.yaml `
  --cfg-options train.batch_size=40 optimizer.learning_rate=4 optimizer.use_wiki=true optimizer.use_prox_shrink=true
```

查看全部参数：

```powershell
python scripts/train.py --help
```

**仅评估**（入口：`scripts/eval_only.py`，不训练，直接对单个 skill 打分）：

```powershell
python scripts/eval_only.py `
  --config configs/searchqa/default.yaml `
  --skill skillopt/envs/searchqa/skills/initial.md `
  --split_dir data/searchqa_id_split `
  --out_root outputs/eval_skill0
```

**单阶段脚本**（可独立运行 Phase 2 / Phase 3）：

```powershell
python scripts/run_gepa_standalone.py   # GEPA（过程驱动反思）
python scripts/run_prox_standalone.py   # Prox Shrink（文本消融收缩）
```

### 4. Web 端

启动浏览器监控/配置面板：

```powershell
python -m pip install -e ".[webui]"
python -m skillopt_webui.app --host 127.0.0.1 --port 7860
```

然后浏览器打开 `http://127.0.0.1:7860`。

| 参数        | 默认值       | 说明                      |
| --------- | --------- | ----------------------- |
| `--port`  | `7860`    | 服务端口                    |
| `--host`  | `0.0.0.0` | 监听地址；仅本机访问用 `127.0.0.1` |
| `--share` | 关闭        | 生成 Gradio 公网分享链接        |

### 5. 其它

- **控制台命令**：`pip install -e .` 后会提供 `skillopt-train` / `skillopt-eval` / `skillopt-sleep` 三个命令。
- **关键技术开关**（`optimizer.*`）：`use_wiki`、`wiki_react_proposer`（轨迹模式沉淀）、`use_prox_shrink`（文本消融）、`use_slow_update` / `use_meta_skill` / `use_skill_aware_reflection`（进化记忆与抗遗忘）、`use_gepa`（过程驱动反思）。
- **门控与评估**（`evaluation.*`）：`gate_metric` 支持 `hard` / `soft` / `mixed`，`use_gate` 控制验证集门控。

## 目录结构（核心）

```
configs/            # 各环境 YAML 配置（继承 _base_/default.yaml）
data/               # 预切分的 train/val/test 数据
skillopt/           # 核心包
  envs/             # 各基准环境（含 gbrain 等）
  optimizer/        # 学习率调度、技能更新、wiki、prox shrink、meta skill 等
  model/            # 多后端（openai_compatible/azure/claude/qwen/minimax/codex/jiuwen/...）
  engine/           # 训练器
scripts/            # train.py / eval_only.py / 单阶段脚本
skillopt_webui/     # Gradio 面板
plugins/            # Codex / Claude Code / Copilot / Cursor / Devin / OpenClaw 集成
```

