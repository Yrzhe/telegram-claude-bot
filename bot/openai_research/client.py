"""OpenAI Research Client - Wraps OpenAI API for deep research tasks"""

import logging
import json
from dataclasses import dataclass, field
from typing import Optional
from openai import OpenAI

logger = logging.getLogger(__name__)


@dataclass
class ResearchResult:
    """Result from OpenAI research"""
    content: str
    search_results: list[dict] = field(default_factory=list)
    model_used: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    is_error: bool = False
    error_message: Optional[str] = None


class OpenAIResearchClient:
    """
    OpenAI Research Client for deep research tasks.

    Architecture:
    1. Search phase: gpt-4o + web_search (o3 doesn't support web search)
    2. Analysis phase: o3/o3-mini for deep reasoning
    3. Output phase: optional formatting with gpt-4o-mini
    """

    def __init__(self, api_key: str):
        """Initialize with OpenAI API key"""
        self.client = OpenAI(api_key=api_key)
        self.api_key = api_key

    def web_search(
        self,
        query: str,
        max_results: int = 10,
        model: str = "gpt-4o"
    ) -> ResearchResult:
        """
        Perform web search using OpenAI's web search tool.

        Args:
            query: Search query
            max_results: Maximum number of results to return
            model: Model to use (must support web_search, e.g., gpt-4o)

        Returns:
            ResearchResult with search results and summary
        """
        try:
            logger.info(f"OpenAI web search: {query[:100]}...")

            response = self.client.responses.create(
                model=model,
                tools=[{"type": "web_search_preview"}],
                input=f"""Search the web for: {query}

Return the search results in a structured format. For each result include:
- Title
- URL
- Brief summary of content

Focus on finding authoritative and recent sources. Return up to {max_results} most relevant results."""
            )

            # Extract content and search results
            content = ""
            search_results = []

            for item in response.output:
                if item.type == "message":
                    for block in item.content:
                        if hasattr(block, 'text'):
                            content = block.text
                elif item.type == "web_search_call":
                    # Extract search results if available
                    pass

            return ResearchResult(
                content=content,
                search_results=search_results,
                model_used=model,
                input_tokens=response.usage.input_tokens if response.usage else 0,
                output_tokens=response.usage.output_tokens if response.usage else 0
            )

        except Exception as e:
            logger.error(f"OpenAI web search failed: {e}")
            return ResearchResult(
                content="",
                is_error=True,
                error_message=str(e)
            )

    def deep_analyze(
        self,
        content: str,
        analysis_prompt: str,
        model: str = "o3",
        reasoning_effort: str = "high"
    ) -> ResearchResult:
        """
        Perform deep analysis using o3 model.

        Args:
            content: Content to analyze (e.g., search results)
            analysis_prompt: Instructions for analysis
            model: Model to use (o3, o3-mini, o1, o1-mini)
            reasoning_effort: Reasoning effort level (low, medium, high) - only for o3/o3-mini

        Returns:
            ResearchResult with analysis
        """
        try:
            logger.info(f"OpenAI deep analysis with {model}, effort={reasoning_effort}")

            full_prompt = f"""{analysis_prompt}

Content to analyze:
---
{content}
---

Provide a thorough, well-structured analysis. Include:
1. Key findings and insights
2. Supporting evidence from the content
3. Critical evaluation and potential gaps
4. Conclusions and recommendations"""

            # Build request params
            params = {
                "model": model,
                "input": full_prompt
            }

            # Add reasoning effort for o3 models
            if model.startswith("o3"):
                params["reasoning"] = {"effort": reasoning_effort}

            response = self.client.responses.create(**params)

            # Extract content
            content_result = ""
            for item in response.output:
                if item.type == "message":
                    for block in item.content:
                        if hasattr(block, 'text'):
                            content_result = block.text

            return ResearchResult(
                content=content_result,
                model_used=model,
                input_tokens=response.usage.input_tokens if response.usage else 0,
                output_tokens=response.usage.output_tokens if response.usage else 0
            )

        except Exception as e:
            logger.error(f"OpenAI deep analysis failed: {e}")
            return ResearchResult(
                content="",
                is_error=True,
                error_message=str(e)
            )

    def research(
        self,
        topic: str,
        search_queries: list[str] | None = None,
        analysis_prompt: str | None = None,
        search_model: str = "gpt-4o",
        analysis_model: str = "o3",
        reasoning_effort: str = "high"
    ) -> ResearchResult:
        """
        Complete research pipeline: search + analyze.

        Args:
            topic: Research topic
            search_queries: Custom search queries (auto-generated if None)
            analysis_prompt: Custom analysis prompt (auto-generated if None)
            search_model: Model for search phase
            analysis_model: Model for analysis phase
            reasoning_effort: Reasoning effort for o3 models

        Returns:
            ResearchResult with complete research
        """
        try:
            logger.info(f"Starting research on: {topic[:100]}...")

            # Phase 1: Generate search queries if not provided
            if not search_queries:
                search_queries = [topic]

                # Use gpt-4o to generate additional search queries
                try:
                    query_response = self.client.responses.create(
                        model="gpt-4o-mini",
                        input=f"""Generate 3-5 specific search queries to thoroughly research this topic: {topic}

Return only the queries, one per line, no numbering or explanations."""
                    )

                    for item in query_response.output:
                        if item.type == "message":
                            for block in item.content:
                                if hasattr(block, 'text'):
                                    queries = block.text.strip().split('\n')
                                    search_queries.extend([q.strip() for q in queries if q.strip()])
                except Exception as e:
                    logger.warning(f"Failed to generate search queries: {e}")

            # Phase 2: Perform searches
            all_search_content = []
            total_input_tokens = 0
            total_output_tokens = 0

            for query in search_queries[:5]:  # Limit to 5 queries
                result = self.web_search(query, model=search_model)
                if not result.is_error and result.content:
                    all_search_content.append(f"### Search: {query}\n\n{result.content}")
                    total_input_tokens += result.input_tokens
                    total_output_tokens += result.output_tokens

            if not all_search_content:
                return ResearchResult(
                    content="No search results found.",
                    is_error=True,
                    error_message="All searches failed or returned empty results"
                )

            combined_search = "\n\n---\n\n".join(all_search_content)

            # Phase 3: Deep analysis with o3
            if not analysis_prompt:
                analysis_prompt = f"""You are a research analyst. Analyze the following search results about: {topic}

Provide a comprehensive research report that includes:
1. Executive Summary
2. Key Findings (with source citations)
3. In-depth Analysis
4. Different Perspectives
5. Limitations and Gaps
6. Conclusions and Recommendations"""

            analysis_result = self.deep_analyze(
                content=combined_search,
                analysis_prompt=analysis_prompt,
                model=analysis_model,
                reasoning_effort=reasoning_effort
            )

            if analysis_result.is_error:
                return analysis_result

            total_input_tokens += analysis_result.input_tokens
            total_output_tokens += analysis_result.output_tokens

            return ResearchResult(
                content=analysis_result.content,
                model_used=f"{search_model}+{analysis_model}",
                input_tokens=total_input_tokens,
                output_tokens=total_output_tokens
            )

        except Exception as e:
            logger.error(f"Research pipeline failed: {e}")
            return ResearchResult(
                content="",
                is_error=True,
                error_message=str(e)
            )

    def chat(
        self,
        message: str,
        model: str = "gpt-4o",
        system_prompt: str | None = None
    ) -> ResearchResult:
        """
        Simple chat completion (no web search, no deep reasoning).

        Args:
            message: User message
            model: Model to use
            system_prompt: Optional system prompt

        Returns:
            ResearchResult with response
        """
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": message})

            response = self.client.chat.completions.create(
                model=model,
                messages=messages
            )

            content = response.choices[0].message.content or ""

            return ResearchResult(
                content=content,
                model_used=model,
                input_tokens=response.usage.prompt_tokens if response.usage else 0,
                output_tokens=response.usage.completion_tokens if response.usage else 0
            )

        except Exception as e:
            logger.error(f"OpenAI chat failed: {e}")
            return ResearchResult(
                content="",
                is_error=True,
                error_message=str(e)
            )
