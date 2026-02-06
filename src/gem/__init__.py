"""GEM - Generative Evaluation & Modeling

数据合成工作流框架
"""

__version__ = "0.1.0.dev"

from gem.llm.client import LLMClient
from gem.pipeline import SynthesisPipeline, PipelineConfig
from gem.models import (
    TagAnnotation,
    Workflow,
    Dialogue,
    Message,
    ToolCall,
    Trajectory,
    ToolDefinition,
    EvaluationResult,
)

__all__ = [
    "__version__",
    "LLMClient",
    "SynthesisPipeline",
    "PipelineConfig",
    "TagAnnotation",
    "Workflow",
    "Dialogue",
    "Message",
    "ToolCall",
    "Trajectory",
    "ToolDefinition",
    "EvaluationResult",
]
