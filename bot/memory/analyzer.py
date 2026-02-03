"""Memory analyzer - post-processing analysis for missed memories"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from .manager import MemoryManager
from .models import Memory

logger = logging.getLogger(__name__)

# Prompt for memory extraction
MEMORY_EXTRACTION_PROMPT = """你是一个记忆提取助手。分析以下对话，提取值得记住的用户信息。

## 已记录的记忆 (本次对话中已保存)
{existing_memories}

## 对话内容
{conversation}

## 你的任务
找出对话中**遗漏的**、值得记住的信息。不要重复已记录的内容。

## 应该提取的信息类型
- 个人信息（姓名、年龄、位置等）
- 职业信息（工作、公司、角色）
- 兴趣爱好
- 目标和项目
- 偏好和习惯
- 人际关系
- 情绪线索
- 重要背景信息

## 不应提取的信息
- 临时性信息（如"今天想吃什么"）
- 敏感数据（密码、身份证号等）
- 琐碎细节

## 输出格式
如果有遗漏的信息，用以下JSON格式输出（每条一行）：
{{"content": "...", "category": "career|interests|goals|personal|preferences|relationships|emotions|context", "visibility": "public|private", "confidence": 0.8, "tags": ["tag1", "tag2"]}}

如果没有遗漏的信息，输出：
NO_NEW_MEMORIES

注意：
- 只输出JSON或NO_NEW_MEMORIES，不要其他文字
- confidence: 1.0=用户明确说的, 0.8=强推断, 0.6=弱推断
- visibility: 职业/兴趣/目标默认public，个人/偏好/情绪默认private
"""


class MemoryAnalyzer:
    """Analyzes conversations to extract missed memories"""

    def __init__(
        self,
        memory_manager: MemoryManager,
        api_config: dict,
    ):
        """
        Initialize memory analyzer

        Args:
            memory_manager: MemoryManager instance for this user
            api_config: API configuration with keys: anthropic_api_key, anthropic_base_url, claude_model
        """
        self.memory_manager = memory_manager
        self.api_config = api_config

    async def analyze_conversation(
        self,
        conversation: str,
        existing_memory_ids: list[str] = None,
    ) -> list[dict]:
        """
        Analyze a conversation and extract missed memories

        Args:
            conversation: The conversation text to analyze
            existing_memory_ids: IDs of memories already saved in this conversation

        Returns:
            List of extracted memory dicts
        """
        if not conversation or len(conversation) < 50:
            return []

        try:
            # Get existing memories for context
            existing_memories = ""
            if existing_memory_ids:
                for mem_id in existing_memory_ids:
                    memories = self.memory_manager.search_memories(query=mem_id, limit=1)
                    for m in memories:
                        if m.id == mem_id:
                            existing_memories += f"- {m.content} ({m.category})\n"

            if not existing_memories:
                existing_memories = "(无)"

            # Build prompt
            prompt = MEMORY_EXTRACTION_PROMPT.format(
                existing_memories=existing_memories,
                conversation=conversation[:8000],  # Limit conversation length
            )

            # Call Claude API
            import anthropic

            client = anthropic.AsyncAnthropic(
                api_key=self.api_config.get("anthropic_api_key"),
                base_url=self.api_config.get("anthropic_base_url"),
            )

            response = await client.messages.create(
                model=self.api_config.get("claude_model", "claude-sonnet-4-5-20250929"),
                max_tokens=2000,
                messages=[
                    {"role": "user", "content": prompt}
                ],
            )

            # Parse response
            response_text = response.content[0].text.strip()

            if response_text == "NO_NEW_MEMORIES":
                return []

            # Parse JSON lines
            import json
            extracted = []
            for line in response_text.split("\n"):
                line = line.strip()
                if line.startswith("{"):
                    try:
                        memory_data = json.loads(line)
                        extracted.append(memory_data)
                    except json.JSONDecodeError:
                        continue

            return extracted

        except Exception as e:
            logger.error(f"Memory analysis failed: {e}")
            return []

    async def save_extracted_memories(
        self,
        extracted: list[dict],
    ) -> tuple[list[Memory], str]:
        """
        Save extracted memories and generate notification

        Args:
            extracted: List of extracted memory dicts

        Returns:
            Tuple of (saved memories, notification message)
        """
        saved = []
        for mem_data in extracted:
            try:
                memory, _ = self.memory_manager.save_memory(
                    content=mem_data.get("content", ""),
                    category=mem_data.get("category", "context"),
                    source_type="inferred",
                    confidence=mem_data.get("confidence", 0.7),
                    tags=mem_data.get("tags", []),
                    visibility=mem_data.get("visibility"),
                )
                saved.append(memory)
            except Exception as e:
                logger.error(f"Failed to save extracted memory: {e}")

        # Generate batch notification
        if saved:
            notification = self.memory_manager.format_memories_summary(saved)
            return saved, notification

        return [], ""


async def run_memory_analysis(
    user_id: int,
    user_data_dir: Path,
    conversation: str,
    api_config: dict,
    existing_memory_ids: list[str] = None,
) -> tuple[list[Memory], str]:
    """
    Convenience function to run memory analysis for a user

    Args:
        user_id: User ID
        user_data_dir: Path to user's data directory
        conversation: Conversation text to analyze
        api_config: API configuration
        existing_memory_ids: IDs of memories already saved

    Returns:
        Tuple of (saved memories, notification message)
    """
    try:
        manager = MemoryManager(user_data_dir)
        analyzer = MemoryAnalyzer(manager, api_config)

        extracted = await analyzer.analyze_conversation(
            conversation=conversation,
            existing_memory_ids=existing_memory_ids,
        )

        if extracted:
            return await analyzer.save_extracted_memories(extracted)

        return [], ""

    except Exception as e:
        logger.error(f"Memory analysis failed for user {user_id}: {e}")
        return [], ""
