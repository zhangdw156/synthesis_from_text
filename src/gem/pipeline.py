"""数据合成主工作流"""

from typing import Optional, List
import logging
from dataclasses import dataclass

from gem.llm.client import LLMClient
from gem.models.annotation import TagAnnotation
from gem.models.workflow import Workflow
from gem.models.dialogue import Dialogue
from gem.models.trajectory import Trajectory
from gem.steps.tag_annotation import TagAnnotationStep
from gem.steps.workflow_discovery import WorkflowDiscoveryStep
from gem.steps.trajectory_generation import TrajectoryGenerationStep
from gem.steps.trajectory_refinement import TrajectoryRefinementStep
from gem.steps.hallucination_detection import HallucinationDetectionStep

logger = logging.getLogger(__name__)


@dataclass
class PipelineConfig:
    """流水线配置"""
    llm_client: LLMClient
    # 各步骤的 prompt 路径（可选，使用默认值）
    tag_annotation_prompt: Optional[str] = None
    workflow_discovery_prompt: Optional[str] = None
    trajectory_generation_prompt: Optional[str] = None
    trajectory_refinement_prompt: Optional[str] = None
    hallucination_detection_prompt: Optional[str] = None


class SynthesisPipeline:
    """数据合成主流水线
    
    完整的5步骤处理流程：
    1. 标签标注（过滤非多步任务）
    2. 工作流发现
    3. 轨迹生成
    4. 轨迹优化
    5. 幻觉检测
    
    任一步骤失败都返回 None
    """
    
    def __init__(self, config: PipelineConfig):
        self.config = config
        
        # 初始化各步骤
        self.tag_annotation_step = TagAnnotationStep(
            config.llm_client,
            config.tag_annotation_prompt or "src/gem/prompts/tag_annotation.md"
        )
        self.workflow_discovery_step = WorkflowDiscoveryStep(
            config.llm_client,
            config.workflow_discovery_prompt or "src/gem/prompts/workflow_and_tool_discovery.md"
        )
        self.trajectory_generation_step = TrajectoryGenerationStep(
            config.llm_client,
            config.trajectory_generation_prompt or "src/gem/prompts/trajectory_generation.md"
        )
        self.trajectory_refinement_step = TrajectoryRefinementStep(
            config.llm_client,
            config.trajectory_refinement_prompt or "src/gem/prompts/trajectory_refinement.md"
        )
        self.hallucination_detection_step = HallucinationDetectionStep(
            config.llm_client,
            config.hallucination_detection_prompt or "src/gem/prompts/hallucination_detection.md"
        )
    
    def run(self, raw_text: str) -> Optional[Trajectory]:
        """执行完整流水线
        
        Args:
            raw_text: 原始纯文本输入
            
        Returns:
            成功: 最终 Trajectory 对象
            失败: None（任一步骤出错或 Step1 判定为 False）
        """
        logger.info("=" * 60)
        logger.info("Starting synthesis pipeline")
        logger.info("=" * 60)
        
        # Step 1: 标签标注
        logger.info("Step 1: Tag annotation")
        annotation = self.tag_annotation_step.execute(raw_text)
        if annotation is None:
            logger.info("Pipeline aborted at tag annotation step")
            return None
        
        # Step 2: 工作流发现
        logger.info("Step 2: Workflow discovery")
        workflows = self.workflow_discovery_step.execute_with_text(raw_text)
        if not workflows:
            logger.info("Pipeline aborted at workflow discovery step")
            return None
        
        # 处理每个工作流
        for i, workflow in enumerate(workflows):
            logger.info(f"Processing workflow {i+1}/{len(workflows)}")
            
            # Step 3: 轨迹生成
            logger.info(f"  Step 3: Trajectory generation")
            dialogue = self.trajectory_generation_step.execute((workflow, i))
            if dialogue is None:
                logger.warning(f"  Workflow {i+1}: Failed at trajectory generation")
                continue
            
            # Step 4: 轨迹优化
            logger.info(f"  Step 4: Trajectory refinement")
            trajectory = self.trajectory_refinement_step.execute((workflow, dialogue))
            if trajectory is None:
                logger.warning(f"  Workflow {i+1}: Failed at trajectory refinement")
                continue
            
            # Step 5: 幻觉检测
            logger.info(f"  Step 5: Hallucination detection")
            final_trajectory = self.hallucination_detection_step.execute(trajectory)
            if final_trajectory is None:
                logger.warning(f"  Workflow {i+1}: Failed hallucination check")
                continue
            
            # 成功完成一个工作流
            logger.info(f"  Workflow {i+1}: Successfully completed!")
            return final_trajectory
        
        logger.info("All workflows failed, pipeline returned None")
        return None
    
    def run_all_workflows(self, raw_text: str) -> List[Trajectory]:
        """执行完整流水线，返回所有成功的工作流轨迹
        
        Args:
            raw_text: 原始纯文本输入
            
        Returns:
            成功的工作流轨迹列表（可能为空）
        """
        logger.info("=" * 60)
        logger.info("Starting synthesis pipeline (all workflows)")
        logger.info("=" * 60)
        
        results = []
        
        # Step 1: 标签标注
        annotation = self.tag_annotation_step.execute(raw_text)
        if annotation is None:
            return results
        
        # Step 2: 工作流发现
        workflows = self.workflow_discovery_step.execute_with_text(raw_text)
        if not workflows:
            return results
        
        # 处理每个工作流
        for i, workflow in enumerate(workflows):
            logger.info(f"Processing workflow {i+1}/{len(workflows)}")
            
            # Step 3: 轨迹生成
            dialogue = self.trajectory_generation_step.execute((workflow, i))
            if dialogue is None:
                continue
            
            # Step 4: 轨迹优化
            trajectory = self.trajectory_refinement_step.execute((workflow, dialogue))
            if trajectory is None:
                continue
            
            # Step 5: 幻觉检测
            final_trajectory = self.hallucination_detection_step.execute(trajectory)
            if final_trajectory is not None:
                results.append(final_trajectory)
                logger.info(f"  Workflow {i+1}: Successfully completed!")
        
        logger.info(f"Pipeline completed: {len(results)}/{len(workflows)} workflows succeeded")
        return results