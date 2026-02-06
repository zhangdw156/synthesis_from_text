"""标签标注解析器"""

import re
from typing import Optional
from gem.models.annotation import TagAnnotation


class TagAnnotationParser:
    """解析标签标注结果"""
    
    def parse(self, response: str) -> Optional[TagAnnotation]:
        """从 LLM 输出解析标签标注
        
        Args:
            response: LLM 原始输出
            
        Returns:
            成功: TagAnnotation 实例
            失败: None
        """
        try:
            # 匹配 multi_step
            multi_step_match = re.search(r'<multi_step>(.*?)</multi_step>', response, re.DOTALL)
            if not multi_step_match:
                return None
            
            multi_step_str = multi_step_match.group(1).strip()
            multi_step = multi_step_str.lower() == 'true'
            
            # 如果非多步任务，直接返回（其他字段为空）
            if not multi_step:
                return TagAnnotation(
                    multi_step=False,
                    summary="",
                    domain="",
                    platform="",
                    task=""
                )
            
            # 匹配其他字段
            summary = self._extract_tag(response, "summary", "")
            domain = self._extract_tag(response, "domain", "")
            platform = self._extract_tag(response, "platform", "")
            task = self._extract_tag(response, "task", "")
            
            return TagAnnotation(
                multi_step=True,
                summary=summary,
                domain=domain,
                platform=platform,
                task=task
            )
            
        except Exception as e:
            return None
    
    def _extract_tag(self, text: str, tag: str, default: str = "") -> str:
        """提取 XML 标签内容"""
        pattern = re.compile(rf'<{tag}>(.*?)</{tag}>', re.DOTALL)
        match = pattern.search(text)
        return match.group(1).strip() if match else default