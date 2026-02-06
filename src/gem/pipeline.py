"""数据合成主工作流"""

import logging
from dataclasses import dataclass
from typing import Any

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

    def run(self, raw_text: str) -> PipelineResult | PipelineFailure:
        """执行完整流水线

        Args:
            raw_text: 原始纯文本输入

        Returns:
            成功: PipelineResult（含 final_trajectory 与全部中间结果）
            失败: PipelineFailure（含 stage，用于 checkpoint failed_stages）
        """
        logger.info("=" * 60)
        logger.info("Starting synthesis pipeline")
        logger.info("=" * 60)

        # Step 1: 标签标注（<multi_step> 非 True 则不执行后续步骤）
        logger.info("Step 1: Tag annotation")
        annotation = self.tag_annotation_step.execute(raw_text)
        self._log_step_output("tag_annotation", annotation)
        if annotation is None:
            logger.info("Pipeline aborted at tag annotation step")
            return PipelineFailure(stage="tag_annotation")
        if not annotation.multi_step:
            logger.info(
                "Pipeline aborted: <multi_step> is not True, skip remaining steps"
            )
            return PipelineFailure(stage="tag_annotation")

        # Step 2: 工作流发现
        logger.info("Step 2: Workflow discovery")
        workflows = self.workflow_discovery_step.execute_with_text(raw_text)
        self._log_step_output("workflow_discovery", workflows)
        if not workflows:
            logger.info("Pipeline aborted at workflow discovery step")
            return PipelineFailure(stage="workflow_discovery")
        # 仅保留 actions 与 tools 均非空的工作流，否则不执行后续步骤
        workflows = [w for w in workflows if w.actions and w.tools]
        if not workflows:
            logger.info("Pipeline aborted: all workflows have empty actions or tools")
            return PipelineFailure(stage="workflow_discovery")

        # 处理每个工作流，记录最远失败阶段
        last_failure_stage = "trajectory_generation"
        for i, workflow in enumerate(workflows):
            logger.info(f"Processing workflow {i + 1}/{len(workflows)}")

            # Step 3: 轨迹生成
            logger.info("  Step 3: Trajectory generation")
            dialogue = self.trajectory_generation_step.execute((workflow, i))
            self._log_step_output("trajectory_generation", dialogue)
            if dialogue is None:
                logger.warning(f"  Workflow {i + 1}: Failed at trajectory generation")
                last_failure_stage = "trajectory_generation"
                continue

            # Step 4: 轨迹优化
            logger.info("  Step 4: Trajectory refinement")
            trajectory = self.trajectory_refinement_step.execute((workflow, dialogue))
            self._log_step_output("trajectory_refinement", trajectory)
            if trajectory is None:
                logger.warning(f"  Workflow {i + 1}: Failed at trajectory refinement")
                last_failure_stage = "trajectory_refinement"
                continue

            # Step 5: 幻觉检测
            logger.info("  Step 5: Hallucination detection")
            final_trajectory = self.hallucination_detection_step.execute(trajectory)
            self._log_step_output("hallucination_detection", final_trajectory)
            if final_trajectory is None:
                logger.warning(f"  Workflow {i + 1}: Failed hallucination check")
                last_failure_stage = "hallucination_detection"
                continue

            # 成功完成一个工作流，返回最终轨迹与全部中间结果
            logger.info(f"  Workflow {i + 1}: Successfully completed!")
            return PipelineResult(
                final_trajectory=final_trajectory,
                tag_annotation=annotation,
                workflows=workflows,
                workflow_index=i,
                dialogue=dialogue,
            )

        logger.info("All workflows failed, pipeline returned None")
        return PipelineFailure(stage=last_failure_stage)

    def run_all_workflows(self, raw_text: str) -> list[PipelineResult]:
        """执行完整流水线，返回所有成功的工作流结果（含中间结果）

        Args:
            raw_text: 原始纯文本输入

        Returns:
            成功的 PipelineResult 列表（可能为空）
        """
        logger.info("=" * 60)
        logger.info("Starting synthesis pipeline (all workflows)")
        logger.info("=" * 60)

        results = []

        # Step 1: 标签标注（<multi_step> 非 True 则不执行后续步骤）
        annotation = self.tag_annotation_step.execute(raw_text)
        self._log_step_output("tag_annotation", annotation)
        if annotation is None:
            return results
        if not annotation.multi_step:
            logger.info(
                "Pipeline aborted: <multi_step> is not True, skip remaining steps"
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
            logger.info("Pipeline aborted: all workflows have empty actions or tools")
            return results

        # 处理每个工作流
        for i, workflow in enumerate(workflows):
            logger.info(f"Processing workflow {i + 1}/{len(workflows)}")

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
                logger.info(f"  Workflow {i + 1}: Successfully completed!")

        logger.info(
            f"Pipeline completed: {len(results)}/{len(workflows)} workflows succeeded"
        )
        return results
