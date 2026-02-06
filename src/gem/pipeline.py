"""数据合成主工作流"""

import logging
from dataclasses import dataclass
from typing import Any, Optional

from gem.llm.client import LLMClient
from gem.models.annotation import TagAnnotation
from gem.models.dialogue import Dialogue
from gem.models.trajectory import Trajectory
from gem.models.workflow import Workflow
from gem.steps.hallucination_detection import HallucinationDetectionStep
from gem.steps.tag_annotation import TagAnnotationStep
from gem.steps.trajectory_generation import TrajectoryGenerationStep
from gem.steps.trajectory_refinement import TrajectoryRefinementStep
from gem.steps.workflow_discovery import WorkflowDiscoveryStep

logger = logging.getLogger(__name__)

# 调试时每个 step 输出的最大字符数，避免刷屏
_DEBUG_OUTPUT_MAX_CHARS = 4000


@dataclass
class PipelineResult:
    """单条流水线成功结果，包含最终轨迹与全部中间结果（当前工作流可用 workflows[workflow_index] 取得）"""

    final_trajectory: Trajectory
    tag_annotation: TagAnnotation
    workflows: list[Workflow]
    workflow_index: int
    dialogue: Dialogue


@dataclass
class PipelineFailure:
    """流水线失败结果，记录失败阶段（用于 checkpoint failed_stages）"""

    stage: str  # tag_annotation | workflow_discovery | trajectory_generation | trajectory_refinement | hallucination_detection


# 各步骤名称，用于合并 llm_steps
STEP_NAMES = (
    "tag_annotation",
    "workflow_discovery",
    "trajectory_generation",
    "trajectory_refinement",
    "hallucination_detection",
)

# 允许重试的阶段（和数据处理脚本保持一致）
RETRYABLE_STAGES = {"workflow_discovery", "trajectory_generation", "trajectory_refinement"}

# LLMClient 支持的参数
_LLM_KEYS = ("base_url", "model_name", "api_key", "temperature", "max_tokens", "top_p")


def _llm_client_from_config(
    llm_default: dict[str, Any], override: dict[str, Any] | None
) -> LLMClient:
    """用默认 llm 配置与步骤级 override 合并后构造 LLMClient。"""
    merged = dict(llm_default)
    if override:
        for k in _LLM_KEYS:
            if k in override:
                merged[k] = override[k]
    return LLMClient(
        base_url=merged.get("base_url", "http://localhost:8000/v1"),
        model_name=merged.get("model_name", "Qwen3-8B"),
        api_key=merged.get("api_key", "dummy_key"),
        temperature=merged.get("temperature", 0.7),
        max_tokens=merged.get("max_tokens", 40960),
        top_p=merged.get("top_p", 0.95),
    )


@dataclass
class PipelineConfig:
    """流水线配置（与 Hydra 配置结构对应）

    llm: 默认 LLM 配置，所有步骤共用，可被 llm_steps 覆盖。
    llm_steps: 可选，按步骤名覆盖 LLM 配置，例如 llm_steps.tag_annotation.temperature: 0.2。
    steps: 各步骤的 prompt 等配置。
    """

    llm: dict[str, Any]
    steps: dict[str, dict[str, Any]]
    llm_steps: dict[str, dict[str, Any]] | None = None


class SynthesisPipeline:
    """数据合成主流水线

    完整的5步骤处理流程：
    1. 标签标注（过滤非多步任务）
    2. 工作流发现
    3. 轨迹生成
    4. 轨迹优化
    5. 幻觉检测

    成功返回 PipelineResult，失败返回 PipelineFailure（含 stage）。
    支持从指定阶段开始执行（用于重试，默认从 tag_annotation 开始）。
    """

    def __init__(self, config: PipelineConfig):
        self.config = config
        llm_default = config.llm
        llm_steps = config.llm_steps or {}
        steps_cfg = config.steps

        # 为每个步骤创建独立的 LLM 客户端（默认配置 + 该步骤的 llm_steps 覆盖）
        def client_for(step_name: str) -> LLMClient:
            return _llm_client_from_config(llm_default, llm_steps.get(step_name))

        self.tag_annotation_step = TagAnnotationStep(
            client_for("tag_annotation"),
            self._get_prompt_path(steps_cfg, "tag_annotation"),
        )
        self.workflow_discovery_step = WorkflowDiscoveryStep(
            client_for("workflow_discovery"),
            self._get_prompt_path(steps_cfg, "workflow_discovery"),
        )
        self.trajectory_generation_step = TrajectoryGenerationStep(
            client_for("trajectory_generation"),
            self._get_prompt_path(steps_cfg, "trajectory_generation"),
        )
        self.trajectory_refinement_step = TrajectoryRefinementStep(
            client_for("trajectory_refinement"),
            self._get_prompt_path(steps_cfg, "trajectory_refinement"),
        )
        self.hallucination_detection_step = HallucinationDetectionStep(
            client_for("hallucination_detection"),
            self._get_prompt_path(steps_cfg, "hallucination_detection"),
        )

    def _get_prompt_path(self, steps_cfg: dict, step_name: str) -> str:
        """获取步骤的 prompt 路径"""
        default_paths = {
            "tag_annotation": "src/gem/prompts/tag_annotation.md",
            "workflow_discovery": "src/gem/prompts/workflow_and_tool_discovery.md",
            "trajectory_generation": "src/gem/prompts/trajectory_generation.md",
            "trajectory_refinement": "src/gem/prompts/trajectory_refinement.md",
            "hallucination_detection": "src/gem/prompts/hallucination_detection.md",
        }
        step_cfg = steps_cfg.get(step_name, {})
        return step_cfg.get("prompt_path", default_paths.get(step_name, ""))

    def _log_step_output(self, step_name: str, output: Any) -> None:
        """当日志级别为 DEBUG 时，将步骤输出打印到控制台，便于调试。"""
        if not logger.isEnabledFor(logging.DEBUG):
            return
        text = repr(output) if output is not None else "None"
        if len(text) > _DEBUG_OUTPUT_MAX_CHARS:
            text = text[:_DEBUG_OUTPUT_MAX_CHARS] + "\n... (truncated)"
        logger.debug("[%s] output:\n%s", step_name, text)

    def run(
        self, 
        raw_text: str, 
        data_id: str | None = None,
        start_stage: str = "tag_annotation"  # 重试时指定起始阶段
    ) -> PipelineResult | PipelineFailure:
        """执行完整流水线（支持从指定阶段开始）

        Args:
            raw_text: 原始纯文本输入
            data_id: 可选，当前条目的数据标识，用于日志中区分不同数据
            start_stage: 起始执行阶段（默认 tag_annotation），重试时指定为 workflow_discovery
                         可选值：tag_annotation/workflow_discovery/trajectory_generation/trajectory_refinement/hallucination_detection

        Returns:
            成功: PipelineResult（含 final_trajectory 与全部中间结果）
            失败: PipelineFailure（含 stage，用于 checkpoint failed_stages）
        """
        prefix = f"[data_id={data_id}] " if data_id else ""
        logger.info("=" * 60)
        logger.info("%sStarting synthesis pipeline (start stage: %s)", prefix, start_stage)
        logger.info("=" * 60)

        # 存储中间结果（用于跨阶段传递）
        annotation: Optional[TagAnnotation] = None
        workflows: list[Workflow] = []

        # --------------------------
        # 按起始阶段执行步骤
        # --------------------------
        # Step 1: 标签标注（仅首次执行/非重试时完整执行；重试时仅校验结果）
        if start_stage == "tag_annotation":
            logger.info("%sStep 1: Tag annotation", prefix)
            annotation = self.tag_annotation_step.execute(raw_text)
            self._log_step_output("tag_annotation", annotation)
            if annotation is None:
                logger.info("%sPipeline aborted at tag annotation step", prefix)
                return PipelineFailure(stage="tag_annotation")
            if not annotation.multi_step:
                logger.info(
                    "%sPipeline aborted: <multi_step> is not True, skip remaining steps",
                    prefix,
                )
                return PipelineFailure(stage="tag_annotation")
        else:
            # 重试时（start_stage != tag_annotation）：仅校验tag_annotation结果（确保是多步任务）
            logger.info("%sRe-validate tag annotation (retry mode)", prefix)
            annotation = self.tag_annotation_step.execute(raw_text)
            if annotation is None or not annotation.multi_step:
                logger.warning("%sRetry aborted: tag annotation failed or not multi-step", prefix)
                return PipelineFailure(stage="tag_annotation")

        # Step 2: 工作流发现（起始阶段为 workflow_discovery 或更早时执行）
        if start_stage in ["tag_annotation", "workflow_discovery"]:
            logger.info("%sStep 2: Workflow discovery", prefix)
            workflows = self.workflow_discovery_step.execute_with_text(raw_text)
            self._log_step_output("workflow_discovery", workflows)
            if not workflows:
                logger.info("%sPipeline aborted at workflow discovery step", prefix)
                return PipelineFailure(stage="workflow_discovery")
            # 仅保留 actions 与 tools 均非空的工作流
            workflows = [w for w in workflows if w.actions and w.tools]
            if not workflows:
                logger.info(
                    "%sPipeline aborted: all workflows have empty actions or tools",
                    prefix,
                )
                return PipelineFailure(stage="workflow_discovery")

        # 处理每个工作流，记录最远失败阶段
        last_failure_stage = "trajectory_generation"
        for i, workflow in enumerate(workflows):
            logger.info("%sProcessing workflow %s/%s", prefix, i + 1, len(workflows))
            dialogue: Optional[Dialogue] = None
            trajectory: Optional[Trajectory] = None

            # Step 3: 轨迹生成（起始阶段为 trajectory_generation 或更早时执行）
            if start_stage in ["tag_annotation", "workflow_discovery", "trajectory_generation"]:
                logger.info("%s  Step 3: Trajectory generation", prefix)
                dialogue = self.trajectory_generation_step.execute((workflow, i))
                self._log_step_output("trajectory_generation", dialogue)
                if dialogue is None:
                    logger.warning(
                        "%s  Workflow %s: Failed at trajectory generation",
                        prefix,
                        i + 1,
                    )
                    last_failure_stage = "trajectory_generation"
                    continue

            # Step 4: 轨迹优化（起始阶段为 trajectory_refinement 或更早时执行）
            if start_stage in ["tag_annotation", "workflow_discovery", "trajectory_generation", "trajectory_refinement"]:
                logger.info("%s  Step 4: Trajectory refinement", prefix)
                trajectory = self.trajectory_refinement_step.execute((workflow, dialogue))
                self._log_step_output("trajectory_refinement", trajectory)
                if trajectory is None:
                    logger.warning(
                        "%s  Workflow %s: Failed at trajectory refinement",
                        prefix,
                        i + 1,
                    )
                    last_failure_stage = "trajectory_refinement"
                    continue

            # Step 5: 幻觉检测（始终执行，只要前面步骤成功）
            logger.info("%s  Step 5: Hallucination detection", prefix)
            final_trajectory = self.hallucination_detection_step.execute(trajectory)
            self._log_step_output("hallucination_detection", final_trajectory)
            if final_trajectory is None:
                logger.warning(
                    "%s  Workflow %s: Failed hallucination check", prefix, i + 1
                )
                last_failure_stage = "hallucination_detection"
                continue

            # 成功完成一个工作流，返回最终结果
            logger.info("%s  Workflow %s: Successfully completed!", prefix, i + 1)
            return PipelineResult(
                final_trajectory=final_trajectory,
                tag_annotation=annotation,
                workflows=workflows,
                workflow_index=i,
                dialogue=dialogue,
            )

        logger.info("%sAll workflows failed, pipeline returned None", prefix)
        return PipelineFailure(stage=last_failure_stage)

    def run_all_workflows(
        self, raw_text: str, data_id: str | None = None
    ) -> list[PipelineResult]:
        """执行完整流水线，返回所有成功的工作流结果（含中间结果）

        Args:
            raw_text: 原始纯文本输入
            data_id: 可选，当前条目的数据标识，用于日志中区分不同数据

        Returns:
            成功的 PipelineResult 列表（可能为空）
        """
        prefix = f"[data_id={data_id}] " if data_id else ""
        logger.info("=" * 60)
        logger.info("%sStarting synthesis pipeline (all workflows)", prefix)
        logger.info("=" * 60)

        results = []

        # Step 1: 标签标注（<multi_step> 非 True 则不执行后续步骤）
        annotation = self.tag_annotation_step.execute(raw_text)
        self._log_step_output("tag_annotation", annotation)
        if annotation is None:
            return results
        if not annotation.multi_step:
            logger.info(
                "%sPipeline aborted: <multi_step> is not True, skip remaining steps",
                prefix,
            )
            return results

        # Step 2: 工作流发现
        workflows = self.workflow_discovery_step.execute_with_text(raw_text)
        self._log_step_output("workflow_discovery", workflows)
        if not workflows:
            return results
        # 仅保留 actions 与 tools 均非空的工作流，否则不执行后续步骤
        workflows = [w for w in workflows if w.actions and w.tools]
        if not workflows:
            logger.info(
                "%sPipeline aborted: all workflows have empty actions or tools",
                prefix,
            )
            return results

        # 处理每个工作流
        for i, workflow in enumerate(workflows):
            logger.info("%sProcessing workflow %s/%s", prefix, i + 1, len(workflows))

            # Step 3: 轨迹生成
            dialogue = self.trajectory_generation_step.execute((workflow, i))
            self._log_step_output("trajectory_generation", dialogue)
            if dialogue is None:
                continue

            # Step 4: 轨迹优化
            trajectory = self.trajectory_refinement_step.execute((workflow, dialogue))
            self._log_step_output("trajectory_refinement", trajectory)
            if trajectory is None:
                continue

            # Step 5: 幻觉检测
            final_trajectory = self.hallucination_detection_step.execute(trajectory)
            self._log_step_output("hallucination_detection", final_trajectory)
            if final_trajectory is not None:
                results.append(
                    PipelineResult(
                        final_trajectory=final_trajectory,
                        tag_annotation=annotation,
                        workflows=workflows,
                        workflow_index=i,
                        dialogue=dialogue,
                    )
                )
                logger.info("%s  Workflow %s: Successfully completed!", prefix, i + 1)

        logger.info(
            "%sPipeline completed: %s/%s workflows succeeded",
            prefix,
            len(results),
            len(workflows),
        )
        return results