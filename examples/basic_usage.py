"""GEM 框架基本使用示例"""

import logging
from gem import LLMClient, SynthesisPipeline, PipelineConfig

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)


def main():
    """基本使用示例"""
    
    # 1. 创建 LLM 客户端
    llm_client = LLMClient(
        base_url="http://localhost:8000/v1",
        model_name="Qwen3-8B",
        api_key="dummy_key",
    )
    
    # 2. 配置流水线
    config = PipelineConfig(llm_client=llm_client)
    
    # 3. 创建流水线实例
    pipeline = SynthesisPipeline(config)
    
    # 4. 示例文本
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
    
    # 5. 运行流水线
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
        with open("output_trajectory.json", "w", encoding="utf-8") as f:
            f.write(result.model_dump_json(indent=2))
        print("\n  Saved to: output_trajectory.json")
    else:
        print("\n❌ Pipeline returned None (failed or filtered out)")


def advanced_usage():
    """高级使用示例：处理所有工作流"""
    
    llm_client = LLMClient(
        base_url="http://localhost:8000/v1",
        model_name="Qwen3-8B",
    )
    
    config = PipelineConfig(llm_client=llm_client)
    pipeline = SynthesisPipeline(config)
    
    sample_text = """Your text here..."""
    
    # 获取所有成功的工作流轨迹
    results = pipeline.run_all_workflows(sample_text)
    
    print(f"Total successful trajectories: {len(results)}")
    
    for i, trajectory in enumerate(results):
        print(f"\nTrajectory {i+1}:")
        print(f"  - Messages: {len(trajectory.conversation)}")
        print(f"  - Tools: {len(trajectory.toolsets)}")


if __name__ == "__main__":
    main()
    # advanced_usage()