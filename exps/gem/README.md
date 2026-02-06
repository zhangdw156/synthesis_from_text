# GEM 实验

使用 GEM 框架批量处理数据，生成高质量的 Agent 训练轨迹。

## 功能特点

- **并行处理**：支持多线程并行处理数据
- **断点续传**：支持从上次中断处继续处理
- **完整追溯**：每条数据有唯一 ID，记录完整处理链路
- **进度显示**：使用 tqdm 显示实时进度和处理时间
- **结果保存**：JSONL 格式，便于后续处理

## 目录结构

```
exps/gem/
├── conf/
│   ├── config.yaml          # 实验配置（数据、并行数等）
│   └── gem_config.yaml      # GEM 流水线配置
├── process_data.py          # 主处理脚本
└── README.md                # 本文件
```

## 使用方法

### 1. 基本使用

```bash
cd exps/gem
python process_data.py
```

### 2. 修改采样数量

```bash
python process_data.py data.sample_size=50
```

### 3. 修改并行线程数

```bash
python process_data.py processing.max_workers=8
```

### 4. 指定其他数据文件

```bash
python process_data.py data.input_path="../../data/other.parquet"
```

### 5. 断点续传

如果处理中断，会自动从 checkpoint 继续：

```bash
python process_data.py  # 自动检测并续传
```

## 配置说明

### conf/config.yaml

```yaml
data:
  input_path: "../../data/ultrafineweb-en-part-0036-of-2048.parquet"
  sample_size: 100          # 采样数量
  random_seed: 42           # 随机种子

output:
  output_dir: "./outputs"
  batch_size: 10            # 批量保存大小
  save_trajectory_jsonl: true   # 保存最终轨迹
  save_intermediate_jsonl: true # 保存中间结果

processing:
  max_workers: 4            # 并行线程数
  request_timeout: 300      # 请求超时时间
```

## 输出文件

处理完成后在 `outputs/` 目录生成：

- **final_trajectories.jsonl** - 成功生成的轨迹数据
- **failed.jsonl** - 处理失败的数据及原因
- **checkpoint.jsonl** - 检查点（用于断点续传）
- **report.json** - 统计报告

### 成功数据格式

```json
{
  "data_id": "a1b2c3d4",
  "original_text": "原始文本...",
  "timestamp": "2024-01-01T12:00:00",
  "success": true,
  "processing_time": 5.2,
  "final_trajectory": {
    "toolsets": [...],
    "system_prompt": "...",
    "conversation": [...]
  },
  "stats": {
    "num_messages": 10,
    "num_tools": 5
  }
}
```

### 失败数据格式

```json
{
  "data_id": "e5f6g7h8",
  "original_text": "原始文本...",
  "success": false,
  "error_step": "pipeline",
  "error_message": "Pipeline returned None"
}
```

## 统计报告

`report.json` 包含：

- 处理总数
- 成功/失败数量
- 成功率
- 总耗时
- 平均处理时间

## 注意事项

1. **VLLM 服务**：确保本地 VLLM 服务已启动（默认端口 8000）
2. **内存使用**：并行处理会占用较多内存，根据机器配置调整 `max_workers`
3. **数据路径**：默认从 `../../data/` 读取数据文件

## 示例输出

```
============================================================
GEM Data Processing Experiment
============================================================
Processing with 4 workers...
Processing: 100%|████████████| 100/100 [05:23<00:00, success=45, failed=55, avg_time=3.2s]
============================================================
Processing Complete!
============================================================
Total records: 100
Success: 45
Failed: 55
Success rate: 45.0%
Total time: 323.4s
Average time per item: 3.2s
Output files:
  - Success: outputs/final_trajectories.jsonl
  - Failed: outputs/failed.jsonl
  - Checkpoint: outputs/checkpoint.jsonl
  - Report: outputs/report.json