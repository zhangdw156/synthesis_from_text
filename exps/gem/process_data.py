"""GEM 实验数据处理脚本

并行处理数据，保存中间结果，生成可追溯的轨迹数据。
"""

import json
import logging
import os
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import hydra
import pandas as pd
from omegaconf import DictConfig, OmegaConf
from tqdm import tqdm

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gem import PipelineConfig, SynthesisPipeline
from gem.models import Trajectory

logger = logging.getLogger(__name__)


def setup_logging(log_level: str = "INFO"):
    """配置日志"""
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
        ]
    )


def load_and_sample_data(cfg: DictConfig) -> pd.DataFrame:
    """加载并采样数据"""
    logger.info(f"Loading data from: {cfg.data.input_path}")
    
    # 读取 parquet
    df = pd.read_parquet(cfg.data.input_path)
    logger.info(f"Total records: {len(df)}")
    
    # 采样
    sample_size = min(cfg.data.sample_size, len(df))
    if sample_size < len(df):
        df = df.sample(n=sample_size, random_state=cfg.data.random_seed)
        logger.info(f"Sampled {sample_size} records")
    
    # 添加唯一ID
    df['data_id'] = [str(uuid.uuid4())[:8] for _ in range(len(df))]
    
    return df


def process_single_item(
    data_id: str,
    text: str,
    pipeline: SynthesisPipeline,
    cfg: DictConfig
) -> Dict[str, Any]:
    """处理单条数据
    
    返回包含完整处理链路的结果字典
    """
    start_time = time.time()
    result = {
        "data_id": data_id,
        "original_text": text,
        "timestamp": datetime.now().isoformat(),
        "success": False,
        "processing_time": 0,
        "error_step": None,
        "error_message": None,
        # 中间结果
        "intermediate": {
            "tag_annotation": None,
            "workflows": None,
            "dialogue": None,
            "trajectory_before_refine": None,
        },
        # 最终结果
        "final_trajectory": None,
        "stats": {
            "num_messages": 0,
            "num_tools": 0,
        }
    }
    
    try:
        # 执行流水线
        trajectory = pipeline.run(text)
        
        if trajectory is None:
            result["error_step"] = "pipeline"
            result["error_message"] = "Pipeline returned None"
            return result
        
        # 记录成功
        result["success"] = True
        result["final_trajectory"] = trajectory.model_dump()
        result["stats"]["num_messages"] = len(trajectory.conversation)
        result["stats"]["num_tools"] = len(trajectory.toolsets)
        
    except Exception as e:
        result["error_step"] = "exception"
        result["error_message"] = str(e)
        logger.error(f"Error processing {data_id}: {e}")
    
    result["processing_time"] = time.time() - start_time
    return result


def save_jsonl(results: List[Dict], output_path: Path):
    """保存结果为 JSONL 格式"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'a', encoding='utf-8') as f:
        for result in results:
            f.write(json.dumps(result, ensure_ascii=False) + '\n')


def load_checkpoint(checkpoint_path: Path) -> set:
    """加载已处理的 ID"""
    processed_ids = set()
    if checkpoint_path.exists():
        with open(checkpoint_path, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    data = json.loads(line.strip())
                    processed_ids.add(data['data_id'])
                except:
                    pass
    return processed_ids


@hydra.main(config_path="conf", config_name="config", version_base=None)
def main(cfg: DictConfig) -> None:
    """主函数"""
    # 设置日志
    setup_logging(cfg.logging.level if hasattr(cfg, 'logging') else "INFO")
    
    logger.info("=" * 60)
    logger.info("GEM Data Processing Experiment")
    logger.info("=" * 60)
    logger.info(f"Config:\n{OmegaConf.to_yaml(cfg)}")
    
    # 创建输出目录
    output_dir = Path(cfg.output.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 输出文件路径
    final_output = output_dir / "final_trajectories.jsonl"
    failed_output = output_dir / "failed.jsonl"
    checkpoint_path = output_dir / "checkpoint.jsonl"
    
    # 加载数据
    df = load_and_sample_data(cfg)
    
    # 检查断点续传
    processed_ids = load_checkpoint(checkpoint_path)
    if processed_ids:
        logger.info(f"Resuming from checkpoint: {len(processed_ids)} already processed")
        df = df[~df['data_id'].isin(processed_ids)]
        logger.info(f"Remaining: {len(df)} records")
    
    if len(df) == 0:
        logger.info("All data already processed!")
        return
    
    # 创建流水线配置
    pipeline_config = PipelineConfig(
        llm=dict(cfg.llm),
        steps={
            name: dict(step_cfg) 
            for name, step_cfg in cfg.steps.items()
        }
    )
    
    # 创建流水线（每个线程一个实例避免竞争）
    # 实际上我们在每个任务中创建
    
    # 准备处理参数
    items = list(zip(df['data_id'], df[cfg.data.content_column]))
    
    # 统计
    stats = {
        "total": len(items),
        "success": 0,
        "failed": 0,
        "total_time": 0,
    }
    
    # 批量收集结果
    batch_results = []
    batch_failed = []
    
    # 并行处理
    max_workers = cfg.processing.max_workers
    logger.info(f"Processing with {max_workers} workers...")
    
    start_time_total = time.time()
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # 提交所有任务
        future_to_id = {}
        for data_id, text in items:
            pipeline = SynthesisPipeline(pipeline_config)
            future = executor.submit(
                process_single_item,
                data_id,
                text,
                pipeline,
                cfg
            )
            future_to_id[future] = data_id
        
        # 使用 tqdm 显示进度
        with tqdm(total=len(items), desc="Processing") as pbar:
            for future in as_completed(future_to_id):
                result = future.result()
                data_id = result['data_id']
                
                # 更新统计
                if result['success']:
                    stats['success'] += 1
                    batch_results.append(result)
                else:
                    stats['failed'] += 1
                    batch_failed.append(result)
                
                stats['total_time'] += result['processing_time']
                
                # 更新进度条
                pbar.update(1)
                avg_time = stats['total_time'] / (stats['success'] + stats['failed'])
                pbar.set_postfix({
                    'success': stats['success'],
                    'failed': stats['failed'],
                    'avg_time': f"{avg_time:.1f}s"
                })
                
                # 批量保存
                batch_size = cfg.output.batch_size
                if len(batch_results) >= batch_size:
                    save_jsonl(batch_results, final_output)
                    save_jsonl(batch_failed, failed_output)
                    save_jsonl(batch_results + batch_failed, checkpoint_path)
                    batch_results = []
                    batch_failed = []
    
    # 保存剩余结果
    if batch_results:
        save_jsonl(batch_results, final_output)
    if batch_failed:
        save_jsonl(batch_failed, failed_output)
    if batch_results or batch_failed:
        save_jsonl(batch_results + batch_failed, checkpoint_path)
    
    # 最终统计
    total_time = time.time() - start_time_total
    logger.info("=" * 60)
    logger.info("Processing Complete!")
    logger.info("=" * 60)
    logger.info(f"Total records: {stats['total']}")
    logger.info(f"Success: {stats['success']}")
    logger.info(f"Failed: {stats['failed']}")
    logger.info(f"Success rate: {stats['success']/stats['total']*100:.1f}%")
    logger.info(f"Total time: {total_time:.1f}s")
    logger.info(f"Average time per item: {total_time/stats['total']:.1f}s")
    logger.info(f"Output files:")
    logger.info(f"  - Success: {final_output}")
    logger.info(f"  - Failed: {failed_output}")
    logger.info(f"  - Checkpoint: {checkpoint_path}")
    
    # 保存统计报告
    report = {
        "timestamp": datetime.now().isoformat(),
        "config": OmegaConf.to_container(cfg, resolve=True),
        "statistics": {
            "total": stats['total'],
            "success": stats['success'],
            "failed": stats['failed'],
            "success_rate": stats['success']/stats['total']*100,
            "total_time": total_time,
            "avg_time_per_item": total_time/stats['total'],
        }
    }
    
    report_path = output_dir / "report.json"
    with open(report_path, 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    logger.info(f"  - Report: {report_path}")


if __name__ == "__main__":
    main()