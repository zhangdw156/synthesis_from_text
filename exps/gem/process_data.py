"""GEM 实验数据处理脚本

按「目标成功条数」持续处理，只保存最终成功轨迹；
断点记录：成功/失败/未处理的原始数据标号；
每累计一定数量成功即写盘一次。
"""

import json
import logging
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

import hydra
import pandas as pd
from dotenv import load_dotenv
from omegaconf import DictConfig, OmegaConf
from tqdm import tqdm

# Add project root so gem is importable when running as script; when run with uv run, gem is the installed package.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
# 在 Hydra 解析配置前加载项目根目录 .env，使 ${oc.env:GEM_LLM_*} 能读到
load_dotenv(_PROJECT_ROOT / ".env")

from gem import (  # noqa: E402 — 必须在 sys.path 与 load_dotenv 之后导入
    PipelineConfig,
    PipelineFailure,
    SynthesisPipeline,
    setup_logging,
)

logger = logging.getLogger(__name__)

CHECKPOINT_FILENAME = "checkpoint.json"
TRAJECTORIES_FILENAME = "final_trajectories.jsonl"


def load_checkpoint(
    checkpoint_path: Path,
) -> tuple[set[str], dict[str, str]]:
    """加载断点：成功 id 集合、失败 id -> 阶段名 映射（兼容旧版仅有 failed_ids 的 checkpoint）"""
    success_ids: set[str] = set()
    failed_stages: dict[str, str] = {}
    if checkpoint_path.exists():
        try:
            with open(checkpoint_path, encoding="utf-8") as f:
                data = json.load(f)
            success_ids = set(data.get("success_ids", []))
            failed_stages = dict(data.get("failed_stages", {}))
            # 兼容旧版：仅有 failed_ids 时视为 failed_stages[id] = "unknown"
            if not failed_stages and data.get("failed_ids"):
                failed_stages = {k: "unknown" for k in data["failed_ids"]}
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Could not load checkpoint: %s", e)
    return success_ids, failed_stages


def save_checkpoint(
    checkpoint_path: Path,
    success_ids: set[str],
    failed_stages: dict[str, str],
) -> None:
    """保存断点（success_ids + failed_stages，失败集合由 failed_stages 的 key 表示）"""
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    with open(checkpoint_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "success_ids": sorted(success_ids),
                "failed_stages": dict(sorted(failed_stages.items())),
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
    """处理单条数据，返回是否成功、成功时的最终轨迹、或失败时的 failure_stage"""
    start_time = time.time()
    result: dict[str, Any] = {
        "data_id": data_id,
        "success": False,
        "final_trajectory": None,
        "failure_stage": None,
    }
    try:
        out = pipeline.run(text)
        if isinstance(out, PipelineFailure):
            result["failure_stage"] = out.stage
            result["processing_time"] = time.time() - start_time
            return result
        result["success"] = True
        result["final_trajectory"] = out.final_trajectory.model_dump()
    except Exception as e:
        logger.error("Error processing %s: %s", data_id, e)
        result["failure_stage"] = "unknown"
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
    # 只配置控制台日志；文件日志交给 Hydra 默认 job_logging
    log_cfg = getattr(cfg, "logging", None) or {}
    setup_logging(
        level=getattr(log_cfg, "level", "INFO"),
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

    # 断点：已成功、失败及失败阶段（failed_stages）
    success_ids, failed_stages = load_checkpoint(checkpoint_path)
    current_success = len(success_ids)
    logger.info(
        "Checkpoint: %d success, %d failed (resume)",
        current_success,
        len(failed_stages),
    )

    if target_success is not None and current_success >= target_success:
        logger.info("Already reached target success count %d, exit.", target_success)
        return

    df = load_data(cfg)
    content_col = cfg.data.content_column
    if content_col not in df.columns:
        raise ValueError(f"Content column {content_col!r} not in dataframe")

    # 待处理：未在成功集也未在失败集（失败集合 = failed_stages 的 key）
    processed = success_ids | set(failed_stages.keys())
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
                        "failure_stage": "unknown",
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
                        save_checkpoint(checkpoint_path, success_ids, failed_stages)
                        next_checkpoint_at = save_every_n
                else:
                    new_failed += 1
                    failed_stages[data_id] = res.get("failure_stage") or "unknown"
                    save_checkpoint(checkpoint_path, success_ids, failed_stages)
                if target_success is None:
                    pbar.update(1)

                done_futures.append(future)
                in_flight -= 1
                pbar.set_postfix(
                    success=current_success,
                    failed=len(failed_stages),
                    pending=len(pending) - pending_idx,
                    ok=new_success,
                )
                break  # 处理一个完成后即跳出，以便再次检查是否已达标并提交新任务

            for f in done_futures:
                del futures[f]

    pbar.close()
    save_checkpoint(checkpoint_path, success_ids, failed_stages)

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

    # 按阶段统计失败数，便于分析瓶颈
    stage_counts = dict(Counter(failed_stages.values()))

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
            "total_failed_ids": len(failed_stages),
            "failed_stages_summary": stage_counts,
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
