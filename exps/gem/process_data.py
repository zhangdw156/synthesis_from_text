"""GEM 实验数据处理脚本

按「目标成功条数」持续处理，只保存最终成功轨迹；
断点记录：成功/失败/未处理的原始数据标号；
每累计一定数量成功即写盘一次。
"""

import json
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

import hydra
import pandas as pd
from omegaconf import DictConfig, OmegaConf
from tqdm import tqdm

# Add project root so gem is importable when running as script; when run with uv run, gem is the installed package.
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from gem import PipelineConfig, SynthesisPipeline, register_hydra_preset, setup_logging

# Register Hydra preset so defaults: - hydra: gem_preset apply (no timestamped output dir).
register_hydra_preset()

logger = logging.getLogger(__name__)

CHECKPOINT_FILENAME = "checkpoint.json"
TRAJECTORIES_FILENAME = "final_trajectories.jsonl"


def load_checkpoint(checkpoint_path: Path) -> tuple[set[str], set[str]]:
    """加载断点：成功 id 集合、失败 id 集合"""
    success_ids: set[str] = set()
    failed_ids: set[str] = set()
    if checkpoint_path.exists():
        try:
            with open(checkpoint_path, encoding="utf-8") as f:
                data = json.load(f)
            success_ids = set(data.get("success_ids", []))
            failed_ids = set(data.get("failed_ids", []))
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Could not load checkpoint: %s", e)
    return success_ids, failed_ids


def save_checkpoint(
    checkpoint_path: Path,
    success_ids: set[str],
    failed_ids: set[str],
) -> None:
    """保存断点"""
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    with open(checkpoint_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "success_ids": sorted(success_ids),
                "failed_ids": sorted(failed_ids),
            },
            f,
            ensure_ascii=False,
            indent=0,
        )


def load_data(cfg: DictConfig) -> pd.DataFrame:
    """加载数据并分配稳定 data_id（用于断点续跑）"""
    logger.info("Loading data from: %s", cfg.data.input_path)
    df = pd.read_parquet(cfg.data.input_path)
    if getattr(cfg.data, "max_rows", None) is not None:
        df = df.head(int(cfg.data.max_rows))
    logger.info("Total rows: %d", len(df))

    id_col = getattr(cfg.data, "data_id_column", None)
    if id_col and id_col in df.columns:
        df = df.rename(columns={id_col: "data_id"})
        df["data_id"] = df["data_id"].astype(str)
    else:
        df["data_id"] = df.index.astype(str)
    return df


def process_single_item(
    data_id: str,
    text: str,
    pipeline: SynthesisPipeline,
) -> dict[str, Any]:
    """处理单条数据，仅返回是否成功及成功时的最终轨迹（无中间结果）"""
    start_time = time.time()
    result: dict[str, Any] = {
        "data_id": data_id,
        "success": False,
        "final_trajectory": None,
    }
    try:
        pipeline_result = pipeline.run(text)
        if pipeline_result is None:
            return result
        result["success"] = True
        result["final_trajectory"] = pipeline_result.final_trajectory.model_dump()
    except Exception as e:
        logger.error("Error processing %s: %s", data_id, e)
    result["processing_time"] = time.time() - start_time
    return result


def append_success_record(output_path: Path, data_id: str, trajectory: dict) -> None:
    """向 JSONL 追加一条成功记录（仅 data_id + trajectory）"""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {"data_id": data_id, "trajectory": trajectory}, ensure_ascii=False
            )
            + "\n"
        )


@hydra.main(config_path="conf", config_name="config", version_base=None)
def main(cfg: DictConfig) -> None:
    """主函数：只保存成功轨迹，断点记录成功/失败/未处理，按成功数定期保存"""
    log_cfg = getattr(cfg, "logging", None) or {}
    setup_logging(
        level=getattr(log_cfg, "level", "INFO"),
        log_file=getattr(log_cfg, "file", None),
        format=getattr(log_cfg, "format", None),
    )

    logger.info("=" * 60)
    logger.info("GEM Data Processing (target success count, checkpoint resume)")
    logger.info("=" * 60)
    logger.info("Config:\n%s", OmegaConf.to_yaml(cfg))

    output_dir = Path(cfg.output.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint_path = output_dir / CHECKPOINT_FILENAME
    final_output = output_dir / TRAJECTORIES_FILENAME

    # target_success_count missing or < 0: process all data in parquet; otherwise stop when count reached
    raw = getattr(cfg.output, "target_success_count", None)
    if raw is None or (isinstance(raw, (int, float)) and int(raw) < 0):
        target_success = None  # no limit: process until parquet exhausted
    else:
        target_success = int(raw)

    save_every_n = int(cfg.output.save_every_n_success)

    # 断点：已成功、已失败
    success_ids, failed_ids = load_checkpoint(checkpoint_path)
    current_success = len(success_ids)
    logger.info(
        "Checkpoint: %d success, %d failed (resume)", current_success, len(failed_ids)
    )

    if target_success is not None and current_success >= target_success:
        logger.info("Already reached target success count %d, exit.", target_success)
        return

    df = load_data(cfg)
    content_col = cfg.data.content_column
    if content_col not in df.columns:
        raise ValueError(f"Content column {content_col!r} not in dataframe")

    # 待处理：未在成功集也未在失败集
    processed = success_ids | failed_ids
    pending = df[~df["data_id"].isin(processed)].copy()
    pending = list(zip(pending["data_id"].tolist(), pending[content_col].tolist()))
    logger.info("Pending items: %d", len(pending))

    if not pending:
        logger.info(
            "No pending items; target may already be reached or data exhausted."
        )
        return

    llm_steps = None
    if hasattr(cfg, "llm_steps") and getattr(cfg, "llm_steps", None):
        llm_steps = {name: dict(sc) for name, sc in cfg.llm_steps.items()}
    pipeline_config = PipelineConfig(
        llm=dict(cfg.llm),
        steps={name: dict(sc) for name, sc in cfg.steps.items()},
        llm_steps=llm_steps,
    )
    max_workers = cfg.processing.max_workers

    # 统计
    new_success = 0
    new_failed = 0
    total_processed = 0
    start_time_total = time.time()
    next_checkpoint_at = save_every_n

    if target_success is not None:
        pbar = tqdm(total=target_success - current_success, desc="Success", unit="ok")
    else:
        pbar = tqdm(total=len(pending), desc="Processed", unit="item")
    pending_idx = 0

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures: dict = {}
        in_flight = 0

        def should_continue() -> bool:
            if target_success is None:
                return pending_idx < len(pending) or bool(futures)
            return current_success < target_success and (
                pending_idx < len(pending) or bool(futures)
            )

        def should_submit() -> bool:
            if target_success is None:
                return pending_idx < len(pending)
            return pending_idx < len(pending) and current_success < target_success

        while should_continue():
            # 尽量保持 in_flight 满载
            while in_flight < max_workers * 2 and should_submit():
                data_id, text = pending[pending_idx]
                pending_idx += 1
                pipeline = SynthesisPipeline(pipeline_config)
                fut = executor.submit(process_single_item, data_id, text, pipeline)
                futures[fut] = data_id
                in_flight += 1

            if not futures:
                break

            done_futures = []
            for future in as_completed(futures):
                data_id = futures[future]
                try:
                    res = future.result()
                except Exception as e:
                    logger.error("Task failed for %s: %s", data_id, e)
                    res = {
                        "data_id": data_id,
                        "success": False,
                        "final_trajectory": None,
                    }
                total_processed += 1

                if res["success"] and res.get("final_trajectory") is not None:
                    current_success += 1
                    new_success += 1
                    success_ids.add(data_id)
                    append_success_record(
                        final_output, data_id, res["final_trajectory"]
                    )
                    if target_success is not None:
                        pbar.update(1)
                    next_checkpoint_at -= 1
                    if next_checkpoint_at <= 0:
                        save_checkpoint(checkpoint_path, success_ids, failed_ids)
                        next_checkpoint_at = save_every_n
                else:
                    new_failed += 1
                    failed_ids.add(data_id)
                    save_checkpoint(checkpoint_path, success_ids, failed_ids)
                if target_success is None:
                    pbar.update(1)

                done_futures.append(future)
                in_flight -= 1
                pbar.set_postfix(
                    success=current_success,
                    failed=len(failed_ids),
                    pending=len(pending) - pending_idx,
                    ok=new_success,
                )
                break  # 处理一个完成后即跳出，以便再次检查是否已达标并提交新任务

            for f in done_futures:
                del futures[f]

    pbar.close()
    save_checkpoint(checkpoint_path, success_ids, failed_ids)

    total_time = time.time() - start_time_total
    logger.info("=" * 60)
    logger.info("Done.")
    logger.info(
        "  Target success: %s",
        target_success if target_success is not None else "all (no limit)",
    )
    logger.info("  Current success: %d", current_success)
    logger.info("  New success this run: %d", new_success)
    logger.info("  New failed this run: %d", new_failed)
    logger.info("  Total processed this run: %d", total_processed)
    logger.info("  Total time: %.1fs", total_time)
    if total_processed:
        logger.info("  Avg time per item: %.1fs", total_time / total_processed)
    logger.info("Output:")
    logger.info("  Trajectories: %s", final_output)
    logger.info("  Checkpoint: %s", checkpoint_path)

    report = {
        "timestamp": datetime.now().isoformat(),
        "config": OmegaConf.to_container(cfg, resolve=True),
        "statistics": {
            "target_success_count": target_success,
            "process_all_data": target_success is None,
            "current_success_count": current_success,
            "new_success_this_run": new_success,
            "new_failed_this_run": new_failed,
            "total_processed_this_run": total_processed,
            "total_success_ids": len(success_ids),
            "total_failed_ids": len(failed_ids),
            "total_time_seconds": total_time,
            "avg_time_per_item": total_time / total_processed if total_processed else 0,
        },
    }
    report_path = output_dir / "report.json"
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    logger.info("  Report: %s", report_path)


if __name__ == "__main__":
    main()
