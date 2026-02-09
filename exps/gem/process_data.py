"""GEM 实验数据处理脚本

按「目标成功条数」持续处理，只保存最终成功轨迹；
断点记录：成功/失败/未处理的原始数据标号；
每累计一定数量成功即写盘一次；
限制失败数据的最大重试次数，避免无限重试；
仅允许第2、3、4阶段失败的数据重试，且重试从第2阶段开始。
"""

import json
import logging
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Set

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

# 允许重试的阶段列表
RETRYABLE_STAGES = {"workflow_discovery", "trajectory_generation", "trajectory_refinement"}
# 重试时的起始阶段
RETRY_START_STAGE = "workflow_discovery"


def load_checkpoint(
    checkpoint_path: Path,
) -> tuple[Set[str], Dict[str, Dict[str, Any]]]:
    """加载断点：
    - success_ids: 成功 id 集合
    - failed_info: 失败信息字典，结构 {data_id: {"stage": 失败阶段, "retry_count": 重试次数}}
    兼容旧版 checkpoint（仅 success_ids + failed_stages）
    """
    success_ids: Set[str] = set()
    failed_info: Dict[str, Dict[str, Any]] = {}
    
    if checkpoint_path.exists():
        try:
            with open(checkpoint_path, encoding="utf-8") as f:
                data = json.load(f)
            success_ids = set(data.get("success_ids", []))
            
            # 兼容旧版 checkpoint（仅 failed_stages 或 failed_ids）
            if "failed_info" in data:
                failed_info = data["failed_info"]
            else:
                # 从旧版 failed_stages 迁移
                failed_stages = dict(data.get("failed_stages", {}))
                if not failed_stages and data.get("failed_ids"):
                    failed_stages = {k: "unknown" for k in data["failed_ids"]}
                # 初始化重试次数为 0
                failed_info = {
                    data_id: {"stage": stage, "retry_count": 0}
                    for data_id, stage in failed_stages.items()
                }
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Could not load checkpoint: %s", e)
    return success_ids, failed_info


def save_checkpoint(
    checkpoint_path: Path,
    success_ids: Set[str],
    failed_info: Dict[str, Dict[str, Any]],
) -> None:
    """保存断点（包含重试次数）"""
    # TODO: 可以考虑改为向关系型表里插入数据，这样就不用每次都完整写入
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
    # 按 data_id 排序，保证 checkpoint 文件内容稳定
    sorted_failed = dict(sorted(failed_info.items()))
    with open(checkpoint_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "success_ids": sorted(success_ids),
                "failed_info": sorted_failed,
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
    retry_count: int,  # 传入当前重试次数，用于日志
    failure_stage: str | None = None,  # 上次失败阶段，用于判断是否从指定阶段重试
) -> dict[str, Any]:
    """处理单条数据，返回是否成功、成功时的最终轨迹、或失败时的 failure_stage
    重试时若失败阶段在允许列表中，直接从第2阶段（workflow_discovery）开始执行
    """
    start_time = time.time()
    # 打印重试次数日志
    logger.info(f"[data_id={data_id}] Processing (retry count: {retry_count})")
    result: dict[str, Any] = {
        "data_id": data_id,
        "success": False,
        "final_trajectory": None,
        "failure_stage": None,
    }
    
    # 确定起始阶段：首次执行用默认（tag_annotation），重试且阶段允许则从第2阶段开始
    start_stage = "tag_annotation"
    if retry_count > 0 and failure_stage in RETRYABLE_STAGES:
        start_stage = RETRY_START_STAGE
        logger.info(f"[data_id={data_id}] Retry from stage: {start_stage} (previous failure: {failure_stage})")
    
    try:
        out = pipeline.run(text, data_id=data_id, start_stage=start_stage)
        if isinstance(out, PipelineFailure):
            result["failure_stage"] = out.stage
            result["processing_time"] = time.time() - start_time
            return result
        result["success"] = True
        result["final_trajectory"] = out.final_trajectory.model_dump()
    except Exception as e:
        logger.error(f"[data_id={data_id}] Error processing (retry {retry_count}): %s", e)
        result["failure_stage"] = "unknown"
    result["processing_time"] = time.time() - start_time
    return result


def append_success_record(output_path: Path, data_id: str, trajectory: dict) -> None:
    """向 JSONL 追加一条成功记录（仅 data_id + trajectory）。

    写入内容即为传入的 trajectory 字典，无二次修改。若发现文件里轨迹为空，
    可开 DEBUG 日志查看写前的 n_conversation/n_toolsets 以确认是上游为空还是写丢。
    """
    conv = trajectory.get("conversation") or []
    tools = trajectory.get("toolsets") or []
    logger.debug(
        "append_success_record data_id=%s n_conversation=%s n_toolsets=%s",
        data_id,
        len(conv),
        len(tools),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"data_id": data_id, "trajectory": trajectory}
    with open(output_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")


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
    logger.info(f"Retryable stages: {RETRYABLE_STAGES}")
    logger.info(f"Retry start stage: {RETRY_START_STAGE}")
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

    # 读取最大重试次数配置（默认 3 次）
    max_retry_times = int(getattr(cfg.processing, "max_retry_times", 3))
    logger.info(f"Max retry times for failed items: {max_retry_times}")
    save_every_n = int(cfg.output.save_every_n_success)

    # 断点：已成功、失败信息（包含重试次数）
    success_ids, failed_info = load_checkpoint(checkpoint_path)
    current_success = len(success_ids)
    logger.info(
        "Checkpoint: %d success, %d failed (resume)",
        current_success,
        len(failed_info),
    )

    if target_success is not None and current_success >= target_success:
        logger.info("Already reached target success count %d, exit.", target_success)
        return

    df = load_data(cfg)
    content_col = cfg.data.content_column
    if content_col not in df.columns:
        raise ValueError(f"Content column {content_col!r} not in dataframe")

    # 待处理数据筛选逻辑：
    # 1. 成功数据：排除
    # 2. 失败数据：
    #    - 失败阶段不在重试列表：排除
    #    - 失败阶段在重试列表但重试次数达上限：排除
    #    - 其他：加入待处理
    processed_success = set(success_ids)
    # 筛选出不允许重试的失败数据（阶段不在重试列表 或 重试次数达上限）
    processed_failed_non_retryable = set()
    processed_failed_retry_limit = set()
    
    for data_id, info in failed_info.items():
        stage = info["stage"]
        retry_count = info["retry_count"]
        
        # 阶段不在重试列表 → 不允许重试
        if stage not in RETRYABLE_STAGES:
            processed_failed_non_retryable.add(data_id)
            logger.debug(f"[data_id={data_id}] Non-retryable failure stage: {stage}")
        # 阶段在重试列表但次数达上限 → 不允许重试
        elif retry_count >= max_retry_times:
            processed_failed_retry_limit.add(data_id)
            logger.debug(f"[data_id={data_id}] Reached max retry times: {retry_count}/{max_retry_times}")

    # 最终待处理 = 所有数据 - 成功数据 - 不允许重试的失败数据 - 重试次数达上限的失败数据
    processed = processed_success | processed_failed_non_retryable | processed_failed_retry_limit
    pending = df[~df["data_id"].isin(processed)].copy()
    pending = list(zip(pending["data_id"].tolist(), pending[content_col].tolist()))
    
    logger.info(f"Pending items: {len(pending)}")
    logger.info(f"  - Excluded non-retryable failed items: {len(processed_failed_non_retryable)}")
    logger.info(f"  - Excluded retry limit reached items: {len(processed_failed_retry_limit)}")

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
                # 获取当前数据的重试次数和上次失败阶段
                current_retry = failed_info.get(data_id, {}).get("retry_count", 0)
                failure_stage = failed_info.get(data_id, {}).get("stage", None)
                pipeline = SynthesisPipeline(pipeline_config)
                # 传入重试次数和上次失败阶段
                fut = executor.submit(process_single_item, data_id, text, pipeline, current_retry, failure_stage)
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

                # 仅当成功且轨迹非空（有 conversation）才写入并计为成功
                traj = res.get("final_trajectory")
                if traj is not None and logger.isEnabledFor(logging.DEBUG):
                    conv = traj.get("conversation") or []
                    logger.debug(
                        "result data_id=%s success=%s len(conversation)=%s",
                        data_id,
                        res.get("success"),
                        len(conv),
                    )
                trajectory_valid = (
                    traj is not None
                    and isinstance(traj.get("conversation"), list)
                    and len(traj.get("conversation", [])) > 0
                )
                if res["success"] and trajectory_valid:
                    current_success += 1
                    new_success += 1
                    success_ids.add(data_id)
                    # 成功后从失败信息中移除
                    if data_id in failed_info:
                        del failed_info[data_id]
                    append_success_record(final_output, data_id, traj)
                    if target_success is not None:
                        pbar.update(1)
                    next_checkpoint_at -= 1
                    if next_checkpoint_at <= 0:
                        save_checkpoint(checkpoint_path, success_ids, failed_info)
                        next_checkpoint_at = save_every_n
                else:
                    new_failed += 1
                    # 更新失败信息（累加重试次数）
                    failure_stage = (
                        "empty_trajectory"
                        if (res.get("success") and not trajectory_valid)
                        else (res.get("failure_stage") or "unknown")
                    )
                    # 只有允许重试的阶段才累加重试次数
                    if failure_stage in RETRYABLE_STAGES:
                        current_retry = failed_info.get(data_id, {}).get("retry_count", 0) + 1
                    else:
                        current_retry = failed_info.get(data_id, {}).get("retry_count", 0)
                    
                    failed_info[data_id] = {
                        "stage": failure_stage,
                        "retry_count": current_retry
                    }
                    # 打印重试次数日志
                    retry_msg = f"{current_retry}/{max_retry_times}" if failure_stage in RETRYABLE_STAGES else "non-retryable"
                    logger.warning(
                        f"[data_id={data_id}] Failed (stage: {failure_stage}, retry count: {retry_msg})"
                    )
                    save_checkpoint(checkpoint_path, success_ids, failed_info)
                if target_success is None:
                    pbar.update(1)

                done_futures.append(future)
                in_flight -= 1
                pbar.set_postfix(
                    success=current_success,
                    failed=len(failed_info),
                    pending=len(pending) - pending_idx,
                )
                break  # 处理一个完成后即跳出，以便再次检查是否已达标并提交新任务

            for f in done_futures:
                del futures[f]

    pbar.close()
    save_checkpoint(checkpoint_path, success_ids, failed_info)

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
    # 统计失败次数分布
    failure_stage_counts = Counter([info["stage"] for info in failed_info.values()])
    failure_retry_counts = Counter([info["retry_count"] for info in failed_info.values()])

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
            "total_failed_ids": len(failed_info),
            "failed_stages_summary": dict(failure_stage_counts),
            "failed_retry_counts_summary": dict(failure_retry_counts),  # 重试次数统计
            "retryable_stages": list(RETRYABLE_STAGES),
            "retry_start_stage": RETRY_START_STAGE,
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