"""GEM - Generative Evaluation & Modeling

数据合成工作流框架
"""

__version__ = "0.1.0.dev"

from gem.models import (
    Dialogue,
    EvaluationResult,
    Message,
    TagAnnotation,
    ToolCall,
    ToolDefinition,
    Trajectory,
    Workflow,
)
from gem.pipeline import PipelineConfig, PipelineResult, SynthesisPipeline

__all__ = [
    "__version__",
    "SynthesisPipeline",
    "PipelineConfig",
    "PipelineResult",
    "TagAnnotation",
    "Workflow",
    "Dialogue",
    "Message",
    "ToolCall",
    "Trajectory",
    "ToolDefinition",
    "EvaluationResult",
]
