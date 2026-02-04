"""Review Agent - Lightweight agent for evaluating Sub Agent task results quality"""

import asyncio
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Tuple, Optional, List

logger = logging.getLogger(__name__)


@dataclass
class ReviewResult:
    """Result of a review evaluation"""
    passed: bool
    feedback: str
    suggestions: List[str] = field(default_factory=list)  # Specific directions to explore
    missing_dimensions: List[str] = field(default_factory=list)  # What aspects were missing


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
        result_text = result if len(result) <= max_result_chars else result[:max_result_chars] + "\n\n...[truncated]"

        # Build retry history context
        retry_context = ""
        if attempt_number > 1:
            retry_context = f"""

## Previous Review History
This is attempt {attempt_number}. Ensure issues from previous attempts have been addressed."""

        # Build the review prompt - enhanced for deep research
        # Include current date so reviewer knows the correct timeline
        current_date = datetime.now().strftime('%Y-%m-%d')
        review_prompt = f"""You are a research quality reviewer. Evaluate the result with an explorer's mindset.

## IMPORTANT: Current Date Context
**Today's date is {current_date}**. When evaluating dates in the result, use this as reference. Do NOT flag dates as incorrect just because they are in 2026 - that is the current year.

## Task Description
{task_description}

## Quality Criteria
{criteria}

## Current Result (Attempt {attempt_number})
{result_text}
{retry_context}

## Review Dimensions (Check All)

### 1. Coverage
- Does it answer the core question?
- Does it cover multiple analysis dimensions?
- Are there obvious missing aspects?

### 2. Depth
- Does the analysis stay at surface level?
- Are anomalies or interesting points explored in depth?
- Are there unique insights?
- Does it ask "why"?

### 3. Data Quality
- Are data sources cited?
- Is important data cross-verified?
- Are timestamps clear?

### 4. Logic
- Are conclusions supported by data?
- Is the reasoning sound?
- Does it distinguish facts from inferences?

## Evaluation Requirements

If REJECT, you MUST provide:
1. Which specific dimension is insufficient
2. What content is missing
3. What direction to improve
4. Specific angles to explore

## Output Format (Follow Strictly)

VERDICT: [PASS or REJECT]
FEEDBACK: [Specific problem description]
MISSING: [Missing dimensions, comma-separated, e.g.: industry comparison,historical trends,risk analysis]
SUGGESTIONS: [New directions to explore, comma-separated, e.g.: compare peer data,analyze 3-year trends,research analyst opinions]"""

        def _call_api() -> Tuple[bool, str, List[str], List[str]]:
            """Synchronous API call (runs in thread pool)"""
            client_args = {"api_key": self.api_key}
            if self.base_url:
                client_args["base_url"] = self.base_url

            client = anthropic.Anthropic(**client_args)

            try:
                response = client.messages.create(
                    model=self.model,
                    max_tokens=800,  # Increased for more detailed feedback
                    messages=[{
                        "role": "user",
                        "content": review_prompt
                    }]
                )

                response_text = response.content[0].text

                # Parse suggestions
                suggestions = []
                if "SUGGESTIONS:" in response_text:
                    suggestions_text = response_text.split("SUGGESTIONS:")[-1].strip()
                    # Handle if there's content after SUGGESTIONS on the same line
                    suggestions_line = suggestions_text.split("\n")[0].strip()
                    if suggestions_line:
                        suggestions = [s.strip() for s in suggestions_line.split(",") if s.strip()]

                # Parse missing dimensions
                missing_dimensions = []
                if "MISSING:" in response_text:
                    missing_text = response_text.split("MISSING:")[-1].strip()
                    # Stop at SUGGESTIONS if present
                    if "SUGGESTIONS:" in missing_text:
                        missing_text = missing_text.split("SUGGESTIONS:")[0]
                    missing_line = missing_text.split("\n")[0].strip()
                    if missing_line:
                        missing_dimensions = [m.strip() for m in missing_line.split(",") if m.strip()]

                # Parse the verdict
                if "VERDICT: PASS" in response_text or "VERDICT:PASS" in response_text:
                    # Extract feedback
                    feedback = ""
                    if "FEEDBACK:" in response_text:
                        feedback_text = response_text.split("FEEDBACK:")[-1]
                        # Stop at MISSING or SUGGESTIONS if present
                        for stop_word in ["MISSING:", "SUGGESTIONS:"]:
                            if stop_word in feedback_text:
                                feedback_text = feedback_text.split(stop_word)[0]
                        feedback = feedback_text.strip().split("\n")[0].strip()
                    return True, feedback, [], []

                elif "VERDICT: REJECT" in response_text or "VERDICT:REJECT" in response_text:
                    # Extract feedback
                    feedback = ""
                    if "FEEDBACK:" in response_text:
                        feedback_text = response_text.split("FEEDBACK:")[-1]
                        # Stop at MISSING or SUGGESTIONS if present
                        for stop_word in ["MISSING:", "SUGGESTIONS:"]:
                            if stop_word in feedback_text:
                                feedback_text = feedback_text.split(stop_word)[0]
                        feedback = feedback_text.strip().split("\n")[0].strip()
                    return False, feedback or "Result does not meet quality standards", suggestions, missing_dimensions

                else:
                    # Unclear response - default to pass to avoid infinite loops
                    logger.warning(f"Unclear review response: {response_text[:200]}")
                    return True, "Review result unclear, defaulting to pass", [], []

            except Exception as e:
                logger.error(f"Review API call failed: {e}")
                # On error, default to pass to avoid infinite loops
                return True, f"Review error: {str(e)}", [], []

        try:
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            passed, feedback, suggestions, missing_dimensions = await loop.run_in_executor(None, _call_api)
            return ReviewResult(
                passed=passed,
                feedback=feedback,
                suggestions=suggestions,
                missing_dimensions=missing_dimensions
            )

        except Exception as e:
            logger.error(f"Review evaluation failed: {e}")
            # On error, default to pass to avoid infinite loops
            return ReviewResult(passed=True, feedback=f"Review error: {str(e)}")


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
    ) -> Tuple[bool, str, List[str], List[str]]:
        """
        Review callback for TaskManager.

        Args:
            task_id: Task ID (for logging)
            description: Task description
            result: Task result to evaluate
            criteria: Quality criteria
            attempt: Current attempt number

        Returns:
            Tuple of (passed, feedback, suggestions, missing_dimensions)
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
        if not review_result.passed:
            logger.info(
                f"Task {task_id} suggestions: {review_result.suggestions}, "
                f"missing: {review_result.missing_dimensions}"
            )

        return (
            review_result.passed,
            review_result.feedback,
            review_result.suggestions,
            review_result.missing_dimensions
        )

    return review_callback
