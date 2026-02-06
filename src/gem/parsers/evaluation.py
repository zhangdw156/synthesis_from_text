"""评估解析器"""

import re
import json
from typing import Optional
from gem.models.evaluation import EvaluationResult


class EvaluationParser:
    """解析幻觉检测结果"""
    
    def parse(self, response: str) -> Optional[EvaluationResult]:
        """从 LLM 输出解析评估结果
        
        Args:
            response: LLM 原始输出
            
        Returns:
            成功: EvaluationResult 实例
            失败: None
        """
        try:
            # 尝试寻找 JSON 对象
            json_pattern = re.compile(r'(\{.*?\})', re.DOTALL)
            match = json_pattern.search(response)
            
            if not match:
                return None
            
            # 清理并解析 JSON
            clean_json_str = re.sub(r'[\x00-\x1F\x7F]', '', match.group(1).strip())
            data = json.loads(clean_json_str)
            
            # 验证必需字段
            if not all(k in data for k in ['R1', 'R2', 'R3']):
                return None
            
            return EvaluationResult.model_validate(data)
            
        except (json.JSONDecodeError, ValueError) as e:
            return None