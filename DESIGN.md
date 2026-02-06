# GEM 数据合成工作流设计方案

## 目标
将实验代码从 Jupyter Notebook 重构为模块化的 Python 包，实现：
- **清晰的实体类定义**（Pydantic 模型）
- **可复用的步骤组件**
- **统一的错误处理**（任一步骤失败返回空）
- **可配置的工作流**（支持 Hydra）

---

## 目录结构

```
src/gem/
├── __init__.py
├── models/                    # 实体类集中管理
│   ├── __init__.py
│   ├── annotation.py          # TagAnnotation
│   ├── workflow.py            # Workflow
│   ├── dialogue.py            # Dialogue, Message, ToolCall
│   ├── trajectory.py          # Trajectory
│   └── evaluation.py          # EvaluationResult
├── prompts/                   # 已有（保持不变）
├── llm/                       # LLM客户端封装
│   ├── __init__.py
│   └── client.py
├── parsers/                   # 解析函数
│   ├── __init__.py
│   ├── tag_annotation.py
│   ├── workflow.py
│   ├── dialogue.py
│   ├── trajectory.py
│   └── evaluation.py
├── steps/                     # 五个步骤
│   ├── __init__.py
│   ├── base.py                # 抽象基类
│   ├── tag_annotation.py      # Step 1
│   ├── workflow_discovery.py  # Step 2
│   ├── trajectory_generation.py # Step 3
│   ├── trajectory_refinement.py # Step 4
│   └── hallucination_detection.py # Step 5
├── pipeline.py                # 主工作流
└── config/                    # Hydra配置
    ├── __init__.py
    ├── config.yaml
    └── steps/
        ├── tag_annotation.yaml
        └── ...
```

---

## 核心设计

### 1. 步骤基类 (steps/base.py)

```python
from abc import ABC, abstractmethod
from typing import TypeVar, Generic, Optional
from pydantic import BaseModel

T = TypeVar('T', bound=BaseModel)

class PipelineStep(ABC, Generic[T]):
    """所有步骤的抽象基类"""
    
    @abstractmethod
    def execute(self, input_data: any) -> Optional[T]:
        """
        执行步骤
        成功: 返回解析后的模型实例
        失败: 返回 None
        """
        pass
    
    @property
    @abstractmethod
    def step_name(self) -> str:
        pass
```

### 2. 步骤实现示例 (steps/tag_annotation.py)

```python
class TagAnnotationStep(PipelineStep[TagAnnotation]):
    step_name = "tag_annotation"
    
    def __init__(self, llm_client, prompt_path: str):
        self.llm = llm_client
        self.prompt = load_prompt(prompt_path)
        self.parser = TagAnnotationParser()
    
    def execute(self, text: str) -> Optional[TagAnnotation]:
        # 1. 填充 prompt
        prompt = self.prompt.replace("{text}", text)
        
        # 2. 调用 LLM
        response = self.llm.call(prompt)
        if not response:
            return None
        
        # 3. 解析结果
        result = self.parser.parse(response)
        
        # 4. 关键: 如果 multi_step=False，返回 None（中止流水线）
        if result and not result.multi_step:
            return None
        return result
```

### 3. 主工作流 (pipeline.py)

```python
class SynthesisPipeline:
    """数据合成主流水线"""
    
    def __init__(self, config):
        self.steps = [
            TagAnnotationStep(...),      # Step 1
            WorkflowDiscoveryStep(...),   # Step 2
            TrajectoryGenerationStep(...), # Step 3
            TrajectoryRefinementStep(...), # Step 4
            HallucinationDetectionStep(...), # Step 5
        ]
    
    def run(self, raw_text: str) -> Optional[Trajectory]:
        """
        执行完整流水线
        
        Args:
            raw_text: 原始纯文本输入
            
        Returns:
            成功: 最终 Trajectory 对象
            失败: None（任一步骤出错或 Step1 判定为 False）
        """
        data = raw_text
        
        for step in self.steps:
            result = step.execute(data)
            if result is None:
                logger.info(f"Step '{step.step_name}' returned None, aborting pipeline")
                return None
            data = result  # 传递给下一步
        
        return data  # 最终 Trajectory
```

### 4. 使用方式

```python
from gem import SynthesisPipeline
from hydra import compose, initialize

# 初始化配置
with initialize(config_path="src/gem/config"):
    cfg = compose(config_name="config")
    
    # 创建流水线
    pipeline = SynthesisPipeline(cfg)
    
    # 运行
    result = pipeline.run("用户提供的原始文本")
    
    if result:
        print(f"成功: {result.model_dump_json()}")
    else:
        print("处理失败或被过滤")
```

---

## 关键设计决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 步骤间数据传递 | 直接传递模型实例 | 类型安全，IDE支持 |
| 错误处理 | 返回 `None` | 简单直观，上游判断是否继续 |
| Prompt 加载 | 文件读取 + 缓存 | 避免重复IO |
| 配置管理 | Hydra | 支持多环境、覆盖配置 |
| 日志 | Rich + logging | 美观且实用 |

---

## 重构后的文件清单

需要新建的 Python 文件：
1. `models/` 下的 5 个模型文件
2. `llm/client.py` - LLM 封装
3. `parsers/` 下的 5 个解析器
4. `steps/base.py` - 抽象基类
5. `steps/` 下的 5 个步骤实现
6. `pipeline.py` - 主工作流
7. `config/` 下的配置文件

---

## 待确认问题

1. **错误处理**：是否需要更详细的错误信息（如返回失败原因），而不仅是 `None`？
2. **中间结果**：是否需要保留中间步骤的结果用于调试？
3. **并行处理**：未来是否需要支持批量处理？
4. **其他**：任何修改建议？