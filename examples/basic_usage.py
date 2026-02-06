"""GEM 框架基本使用示例（使用 Hydra 配置）"""

import logging
import hydra
from omegaconf import DictConfig

from gem import SynthesisPipeline, PipelineConfig

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


@hydra.main(config_path="conf", config_name="config", version_base=None)
def main(cfg: DictConfig) -> None:
    """使用 Hydra 配置运行流水线"""
    
    # 转换 DictConfig 为 PipelineConfig
    config = PipelineConfig(
        llm=dict(cfg.llm),
        steps={
            name: dict(step_cfg) 
            for name, step_cfg in cfg.steps.items()
        }
    )
    
    # 创建流水线实例
    pipeline = SynthesisPipeline(config)
    
    # 示例文本
    sample_text = """
    How to Cancel an Order on Amazon
    
    Step 1: Log in to your Amazon account
    Go to www.amazon.com and sign in with your email and password.
    
    Step 2: Go to Your Orders
    Click on "Returns & Orders" at the top right of the page.
    
    Step 3: Find the order you want to cancel
    Scroll through your recent orders and locate the one you want to cancel.
    
    Step 4: Click Cancel items
    If the order hasn't shipped yet, you'll see a "Cancel items" button. Click it.
    
    Step 5: Select items and confirm
    Choose which items you want to cancel (or all), select a reason, and click "Cancel checked items".
    
    Note: Orders that have already shipped cannot be cancelled, but you can return them instead.
    """
    
    # 运行流水线
    print("=" * 60)
    print("Running synthesis pipeline...")
    print("=" * 60)
    
    result = pipeline.run(sample_text)
    
    if result:
        print("\n✅ Success! Final trajectory:")
        print(f"  - System prompt: {result.system_prompt[:100]}...")
        print(f"  - Toolsets: {len(result.toolsets)} tools")
        print(f"  - Conversation: {len(result.conversation)} messages")
        
        # 保存结果
        import json
        output_path = "output_trajectory.json"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(result.model_dump_json(indent=2))
        print(f"\n  Saved to: {output_path}")
    else:
        print("\n❌ Pipeline returned None (failed or filtered out)")


if __name__ == "__main__":
    main()