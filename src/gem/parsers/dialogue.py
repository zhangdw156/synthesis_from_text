"""对话解析器"""

import re
import json
from typing import Optional, List
from gem.models.dialogue import Dialogue, Message, ToolCall


class DialogueParser:
    """解析对话轨迹"""
    
    def parse(self, response: str) -> Optional[Dialogue]:
        """从 LLM 输出解析对话
        
        Args:
            response: LLM 原始输出
            
        Returns:
            成功: Dialogue 实例
            失败: None
        """
        try:
            # 提取 system prompt
            system_match = re.search(r'<system>(.*?)</system>', response, re.DOTALL)
            system_prompt = system_match.group(1).strip() if system_match else ""
            
            # 提取所有对话轮次
            tags_pattern = re.compile(r'<(user|assistant|tool)>(.*?)</\1>', re.DOTALL)
            all_turns = tags_pattern.findall(response)
            
            conversation = []
            for role, content in all_turns:
                content = content.strip()
                tool_calls = None
                
                # 解析 assistant 中的工具调用
                if role == 'assistant':
                    tool_calls = self._extract_tool_calls(content)
                    # 移除 content 中的 func 标签
                    content = re.sub(r'<func>.*?</func>', '', content, flags=re.DOTALL).strip()
                
                conversation.append(Message(
                    role=role,
                    content=content,
                    tool_calls=tool_calls
                ))
            
            return Dialogue(
                system_prompt=system_prompt,
                conversation=conversation
            )
            
        except Exception as e:
            return None
    
    def _extract_tool_calls(self, content: str) -> Optional[List[ToolCall]]:
        """提取工具调用"""
        tool_calls = []
        func_pattern = re.compile(r'<func>(.*?)</func>', re.DOTALL)
        funcs = func_pattern.findall(content)
        
        for f_json in funcs:
            try:
                # 清洗 JSON 字符串
                clean_json = re.sub(r'[\x00-\x1F\x7F]', '', f_json.strip())
                f_data = json.loads(clean_json)
                tool_calls.append(ToolCall(
                    name=f_data.get("name", ""),
                    arguments=f_data.get("arguments", {})
                ))
            except json.JSONDecodeError:
                continue
        
        return tool_calls if tool_calls else None