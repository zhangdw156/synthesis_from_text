# GEM 实验

使用 GEM 框架批量处理数据，生成高质量的 Agent 训练轨迹。

## 功能特点

- **并行处理**：支持多线程并行处理数据
- **断点续传**：支持从上次中断处继续处理（checkpoint 记录成功 id 与失败 id 及失败阶段）
- **完整追溯**：每条数据有唯一 data_id，便于续跑与排查
- **进度显示**：使用 tqdm 显示实时进度
- **结果保存**：仅保存最终成功轨迹为 JSONL，按 `save_every_n_success` 定期写盘

## 目录结构

```
exps/gem/
├── conf/
│   ├── config.yaml          # 实验主配置（数据、输出、并行、hydra.searchpath）
│   └── gem_config.yaml      # GEM 流水线配置（llm、steps、logging）
├── process_data.py          # 主处理脚本
└── README.md                # 本文件
```

## 使用方法

### 1. 基本使用

建议在项目根目录运行（便于 .env、数据路径等）：

```bash
uv run python exps/gem/process_data.py
```

或在 exps/gem 下：

```bash
cd exps/gem
python process_data.py
```

### 2. 限制处理行数（测试用）

```bash
python process_data.py data.max_rows=10
```

### 3. 修改并行线程数

```bash
python process_data.py processing.max_workers=8
```

### 4. 指定数据文件与输出目录

```bash
python process_data.py data.input_path="data/other.parquet" output.output_dir="syn_data_other"
```

### 5. 目标成功条数

`target_success_count` 为 -1 或 null 表示处理完 parquet 全部数据；设为正整数则达到该成功条数后结束：

```bash
python process_data.py output.target_success_count=100
```

### 6. 断点续传

中断后再次运行即可从 checkpoint 续跑（会跳过已成功与已失败的 data_id）：

```bash
python process_data.py
```

## 配置说明

### conf/config.yaml（主配置）

- **data**：`input_path`（parquet）、`content_column`（文本列）、`data_id_column`（可选）、`max_rows`（可选，限制行数）
- **output**：`output_dir`、`target_success_count`（-1 表示不限制）、`save_every_n_success`（每累计多少条成功写一次盘）
- **processing**：`max_workers`、`request_timeout`
- **hydra.searchpath**：`pkg://gem.configs`，用于从 gem 包加载预设（如 `hydra: gem_preset`）

### conf/gem_config.yaml（流水线配置）

- **llm**：全局 LLM 配置（base_url、api_key、model_name 从环境变量或 .env 读取，见下）
- **llm_steps**：各步骤可覆盖的 LLM 参数
- **steps**：各阶段开关与 prompt 路径
- **logging**：level、format、file

## 输出文件

在 `output.output_dir`（默认 `syn_data`）下：

- **checkpoint.db** — 断点（SQLite）：表 `success_ids`、`failed_info`（data_id, stage, retry_count）
- **final_trajectories.jsonl** — 仅成功轨迹，每行一条：`{"data_id": "...", "trajectory": {...}}`

不单独保存失败列表或中间结果；失败信息在 checkpoint.db 的 `failed_info` 中。

## 使用第三方/服务商模型

`base_url`、`api_key` 等敏感信息**不要写在仓库内的配置文件**中，避免提交到 GitHub。推荐两种方式：

1. **项目根目录 .env（推荐，本地开发）**
   - 在项目根目录执行：`cp .env.example .env`
   - 编辑 `.env`，填写 `GEM_LLM_BASE_URL`、`GEM_LLM_API_KEY`、`GEM_LLM_MODEL_NAME`（可选）
   - `.env` 已加入 `.gitignore`，不会提交。脚本会在 Hydra 解析配置前自动加载项目根目录的 `.env`

2. **环境变量（CI/容器/单次命令）**
   - 使用 `GEM_LLM_BASE_URL`、`GEM_LLM_API_KEY`、`GEM_LLM_MODEL_NAME`
   - 示例：`GEM_LLM_BASE_URL="https://api.xxx.com/v1" GEM_LLM_API_KEY="sk-..." GEM_LLM_MODEL_NAME="gpt-4" python exps/gem/process_data.py`

## 注意事项

1. **LLM 服务**：本地 vLLM 默认 `http://localhost:8000/v1`；使用第三方时通过 .env 或环境变量配置。
2. **内存与并发**：根据机器配置调整 `processing.max_workers`。
3. **数据路径**：默认 `data/ultrafineweb-en-part-0036-of-2048.parquet`，相对项目根或当前工作目录，可按需覆盖。
