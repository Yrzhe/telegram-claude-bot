"""Review Agent - Lightweight agent for evaluating Sub Agent task results quality"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


@dataclass
class ReviewResult:
    """Result of a review evaluation"""
    passed: bool
    feedback: str


class ReviewAgent:
    """
    Lightweight agent for evaluating the quality of Sub Agent task results.

    Uses Claude API to assess whether a result meets the specified criteria.
    """

    def __init__(
        self,
        api_key: str,
        base_url: str | None = None,
        model: str = "claude-sonnet-4-20250514"
    ):
        """
        Initialize ReviewAgent.

        Args:
            api_key: Anthropic API key
            base_url: Optional custom API base URL
            model: Claude model to use for reviews
        """
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    async def evaluate(
        self,
        task_description: str,
        result: str,
        criteria: str,
        attempt_number: int
    ) -> ReviewResult:
        """
        Evaluate whether a task result meets the quality criteria.

        Args:
            task_description: Description of the task
            result: The result to evaluate
            criteria: Quality criteria to check against
            attempt_number: Current attempt number (for context)

        Returns:
            ReviewResult with passed status and feedback
        """
        import anthropic

        # Truncate result if too long
        max_result_chars = 8000
        result_text = result if len(result) <= max_result_chars else result[:max_result_chars] + "\n\n...[内容已截断]"

        # Build the review prompt
        review_prompt = f"""你是一个任务质量审核员。请评估以下任务结果是否符合质量标准。

## 任务描述
{task_description}

## 质量标准
{criteria}

## 当前结果（第 {attempt_number} 次尝试）
{result_text}

## 评估要求
请根据质量标准严格评估结果：
1. 如果结果完全符合标准，返回 PASS
2. 如果结果不符合标准，返回 REJECT 并详细说明问题和改进建议

## 输出格式
请严格按以下格式输出：

VERDICT: [PASS 或 REJECT]
FEEDBACK: [如果 REJECT，说明具体问题和改进建议；如果 PASS，简短说明为何通过]"""

        def _call_api() -> Tuple[bool, str]:
            """Synchronous API call (runs in thread pool)"""
            client_args = {"api_key": self.api_key}
            if self.base_url:
                client_args["base_url"] = self.base_url

            client = anthropic.Anthropic(**client_args)

            try:
                response = client.messages.create(
                    model=self.model,
                    max_tokens=500,
                    messages=[{
                        "role": "user",
                        "content": review_prompt
                    }]
                )

                response_text = response.content[0].text

                # Parse the response
                if "VERDICT: PASS" in response_text or "VERDICT:PASS" in response_text:
                    # Extract feedback
                    feedback = ""
                    if "FEEDBACK:" in response_text:
                        feedback = response_text.split("FEEDBACK:")[-1].strip()
                    return True, feedback

                elif "VERDICT: REJECT" in response_text or "VERDICT:REJECT" in response_text:
                    # Extract feedback
                    feedback = ""
                    if "FEEDBACK:" in response_text:
                        feedback = response_text.split("FEEDBACK:")[-1].strip()
                    return False, feedback or "结果不符合质量标准"

                else:
                    # Unclear response - default to pass to avoid infinite loops
                    logger.warning(f"Unclear review response: {response_text[:200]}")
                    return True, "审核结果不明确，默认通过"

            except Exception as e:
                logger.error(f"Review API call failed: {e}")
                # On error, default to pass to avoid infinite loops
                return True, f"审核过程出错: {str(e)}"

        try:
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            passed, feedback = await loop.run_in_executor(None, _call_api)
            return ReviewResult(passed=passed, feedback=feedback)

        except Exception as e:
            logger.error(f"Review evaluation failed: {e}")
            # On error, default to pass to avoid infinite loops
            return ReviewResult(passed=True, feedback=f"审核过程出错: {str(e)}")


async def create_review_callback(
    api_key: str,
    base_url: str | None = None,
    model: str = "claude-sonnet-4-20250514"
):
    """
    Create a review callback function for use with TaskManager.create_review_task.

    Args:
        api_key: Anthropic API key
        base_url: Optional custom API base URL
        model: Claude model to use for reviews

    Returns:
        Async callback function matching the signature expected by create_review_task
    """
    review_agent = ReviewAgent(api_key, base_url, model)

    async def review_callback(
        task_id: str,
        description: str,
        result: str,
        criteria: str,
        attempt: int
    ) -> Tuple[bool, str]:
        """
        Review callback for TaskManager.

        Args:
            task_id: Task ID (for logging)
            description: Task description
            result: Task result to evaluate
            criteria: Quality criteria
            attempt: Current attempt number

        Returns:
            Tuple of (passed, feedback)
        """
        review_result = await review_agent.evaluate(
            task_description=description,
            result=result,
            criteria=criteria,
            attempt_number=attempt
        )

        logger.info(
            f"Task {task_id} review (attempt {attempt}): "
            f"{'PASS' if review_result.passed else 'REJECT'}"
        )

        return review_result.passed, review_result.feedback

    return review_callback
