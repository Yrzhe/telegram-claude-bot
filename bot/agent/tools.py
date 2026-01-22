"""Agent custom tools - for Telegram interaction, web search, and document processing"""

import logging
import os
import re
from typing import Any, Callable, Awaitable, Optional
from pathlib import Path
from claude_agent_sdk import tool
from ..i18n import t

logger = logging.getLogger(__name__)


def clean_markdown_for_telegram(text: str) -> str:
    """
    Clean Markdown formatting that Telegram doesn't support.

    Removes:
    - **bold** and __bold__ → text
    - *italic* and _italic_ → text

    Keeps:
    - # headings
    - - bullet points
    - 1. numbered lists
    """
    # Remove bold: **text** or __text__
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)

    # Remove italic: *text* (but not **)
    # Match single * not followed/preceded by another *
    text = re.sub(r'(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)', r'\1', text)

    # Remove italic: _text_ (be careful with snake_case)
    # Only match _ at word boundaries
    text = re.sub(r'(?<![a-zA-Z0-9])_([^_]+?)_(?![a-zA-Z0-9])', r'\1', text)

    return text

# Global config storage (not accessible by Agent)
_mistral_api_key: str | None = None
_working_directory: Path | None = None
_delegate_callback: Optional[Callable[[str, str], Awaitable[Optional[str]]]] = None
_delegate_review_callback: Optional[Callable[[str, str, str], Awaitable[Optional[str]]]] = None
_max_sub_agents: int = 10
_schedule_manager: Any = None
_current_user_id: int | None = None
_task_manager: Any = None
_custom_command_manager: Any = None
_admin_user_ids: list[int] = []


def set_tool_config(
    mistral_api_key: str | None = None,
    working_directory: str | None = None,
    delegate_callback: Optional[Callable[[str, str], Awaitable[Optional[str]]]] = None,
    delegate_review_callback: Optional[Callable[[str, str, str], Awaitable[Optional[str]]]] = None,
    max_sub_agents: int = 10,
    schedule_manager: Any = None,
    user_id: int | None = None,
    task_manager: Any = None,
    custom_command_manager: Any = None,
    admin_user_ids: list[int] | None = None
):
    """Set tool config (call before creating tools)"""
    global _mistral_api_key, _working_directory, _delegate_callback, _delegate_review_callback, _max_sub_agents
    global _schedule_manager, _current_user_id, _task_manager, _custom_command_manager, _admin_user_ids
    _mistral_api_key = mistral_api_key
    if working_directory:
        _working_directory = Path(working_directory)
    _delegate_callback = delegate_callback
    _delegate_review_callback = delegate_review_callback
    _max_sub_agents = max_sub_agents
    _schedule_manager = schedule_manager
    _current_user_id = user_id
    _task_manager = task_manager
    _custom_command_manager = custom_command_manager
    _admin_user_ids = admin_user_ids or []
    logger.info(f"set_tool_config: schedule_manager={schedule_manager is not None}, task_manager={task_manager is not None}, custom_command_manager={custom_command_manager is not None}, user_id={user_id}, is_admin={user_id in _admin_user_ids}")


def is_path_within_working_dir(path: Path) -> bool:
    """
    Securely check if a path is within the working directory.

    Uses relative_to() which is more secure than startswith() string comparison.
    Handles edge cases like /app/users/123 vs /app/users/1234.
    """
    if not _working_directory:
        return False
    try:
        resolved_path = path.resolve()
        resolved_working = _working_directory.resolve()
        resolved_path.relative_to(resolved_working)
        return True
    except ValueError:
        return False


def create_telegram_tools(
    send_message_callback: Callable[[str], Awaitable[None]],
    send_file_callback: Callable[[str, str | None], Awaitable[bool]]
) -> list:
    """
    Create Telegram-related custom tools

    Args:
        send_message_callback: Callback function to send messages
        send_file_callback: Callback function to send files

    Returns:
        List of tools for create_sdk_mcp_server
    """

    @tool(
        "send_telegram_message",
        "Send message to Telegram chat. Use to report progress, results, or ask questions.",
        {"message": str}
    )
    async def send_telegram_message(args: dict[str, Any]) -> dict[str, Any]:
        """Send text message to Telegram"""
        message = args.get("message", "")
        if not message:
            return {
                "content": [{"type": "text", "text": t("ERR_EMPTY_MESSAGE")}],
                "is_error": True
            }

        try:
            # Clean markdown formatting for Telegram
            cleaned_message = clean_markdown_for_telegram(message)
            await send_message_callback(cleaned_message)
            return {
                "content": [{"type": "text", "text": t("MESSAGE_SENT", preview=message[:50])}]
            }
        except Exception as e:
            return {
                "content": [{"type": "text", "text": t("ERR_SEND_MESSAGE_FAILED", error=str(e))}],
                "is_error": True
            }

    @tool(
        "send_telegram_file",
        "Send file to Telegram chat. File must be within the working directory.",
        {"file_path": str, "caption": str}
    )
    async def send_telegram_file(args: dict[str, Any]) -> dict[str, Any]:
        """Send file to Telegram"""
        file_path = args.get("file_path", "")
        caption = args.get("caption", "")

        if not file_path:
            return {
                "content": [{"type": "text", "text": t("ERR_EMPTY_FILE_PATH")}],
                "is_error": True
            }

        try:
            success = await send_file_callback(file_path, caption)
            if success:
                return {
                    "content": [{"type": "text", "text": t("FILE_SENT", path=file_path)}]
                }
            else:
                return {
                    "content": [{"type": "text", "text": t("FILE_SEND_FAILED", path=file_path)}],
                    "is_error": True
                }
        except Exception as e:
            return {
                "content": [{"type": "text", "text": t("ERR_SEND_FILE_FAILED", error=str(e))}],
                "is_error": True
            }

    @tool(
        "web_search",
        "Search the internet for latest information. Uses DuckDuckGo search engine. Returns list of results with title, link, and summary.",
        {"query": str, "max_results": int}
    )
    async def web_search(args: dict[str, Any]) -> dict[str, Any]:
        """Search the internet using DuckDuckGo"""
        query = args.get("query", "")
        max_results = args.get("max_results", 5)

        if not query:
            return {
                "content": [{"type": "text", "text": t("ERR_EMPTY_QUERY")}],
                "is_error": True
            }

        try:
            from ddgs import DDGS

            results = []
            search_results = DDGS().text(query, max_results=min(max_results, 10))
            for r in search_results:
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", "")
                })

            if not results:
                return {
                    "content": [{"type": "text", "text": t("NO_SEARCH_RESULTS", query=query)}]
                }

            # Format results
            output = f"{t('SEARCH_RESULTS_FOR', query=query)}\n\n"
            for i, r in enumerate(results, 1):
                output += f"{i}. {r['title']}\n"
                output += f"   {t('LINK_LABEL')}: {r['url']}\n"
                output += f"   {t('SNIPPET_LABEL')}: {r['snippet']}\n\n"

            return {
                "content": [{"type": "text", "text": output}]
            }

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return {
                "content": [{"type": "text", "text": t("SEARCH_FAILED", error=str(e))}],
                "is_error": True
            }

    @tool(
        "web_fetch",
        "Fetch webpage content. Input URL, returns text content with HTML tags removed.",
        {"url": str}
    )
    async def web_fetch(args: dict[str, Any]) -> dict[str, Any]:
        """Fetch webpage content"""
        url = args.get("url", "")

        if not url:
            return {
                "content": [{"type": "text", "text": t("ERR_EMPTY_URL")}],
                "is_error": True
            }

        try:
            import urllib.request
            import re

            # Set User-Agent
            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )

            with urllib.request.urlopen(req, timeout=10) as response:
                html = response.read().decode('utf-8', errors='ignore')

            # Remove HTML tags
            # Remove script and style
            html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
            # Remove all tags
            text = re.sub(r'<[^>]+>', ' ', html)
            # Clean whitespace
            text = re.sub(r'\s+', ' ', text).strip()

            # Limit length
            if len(text) > 8000:
                text = text[:8000] + f"...\n\n{t('CONTENT_TRUNCATED')}"

            return {
                "content": [{"type": "text", "text": f"{t('WEBPAGE_CONTENT', url=url)}\n\n{text}"}]
            }

        except Exception as e:
            logger.error(f"Fetch webpage failed: {e}")
            return {
                "content": [{"type": "text", "text": t("FETCH_FAILED", error=str(e))}],
                "is_error": True
            }

    @tool(
        "pdf_to_markdown",
        "Convert PDF file to Markdown format with image extraction. Input PDF path (within user directory), outputs Markdown file and images folder.",
        {"pdf_path": str, "output_dir": str}
    )
    async def pdf_to_markdown(args: dict[str, Any]) -> dict[str, Any]:
        """Convert PDF to Markdown using Mistral OCR"""
        pdf_path = args.get("pdf_path", "")
        output_dir = args.get("output_dir", "")

        if not pdf_path:
            return {
                "content": [{"type": "text", "text": t("ERR_EMPTY_PDF_PATH")}],
                "is_error": True
            }

        if not _mistral_api_key:
            return {
                "content": [{"type": "text", "text": t("ERR_PDF_SERVICE_NOT_CONFIGURED")}],
                "is_error": True
            }

        try:
            import json
            import base64
            from mistralai import Mistral, DocumentURLChunk

            # Parse paths
            if _working_directory:
                full_pdf_path = _working_directory / pdf_path
                if not output_dir:
                    output_dir = f"documents/{Path(pdf_path).stem}"
                full_output_dir = _working_directory / output_dir
            else:
                full_pdf_path = Path(pdf_path)
                full_output_dir = Path(output_dir) if output_dir else Path(f"output/{Path(pdf_path).stem}")

            # Check if PDF exists
            if not full_pdf_path.exists():
                return {
                    "content": [{"type": "text", "text": t("ERR_PDF_NOT_EXIST", path=pdf_path)}],
                    "is_error": True
                }

            # Create output directory
            full_output_dir.mkdir(parents=True, exist_ok=True)
            images_dir = full_output_dir / "images"
            images_dir.mkdir(exist_ok=True)

            pdf_base = full_pdf_path.stem
            logger.info(f"Processing PDF: {pdf_path}")

            # Initialize Mistral client
            client = Mistral(api_key=_mistral_api_key)

            # Upload PDF
            with open(full_pdf_path, "rb") as f:
                pdf_bytes = f.read()

            uploaded_file = client.files.upload(
                file={
                    "file_name": full_pdf_path.name,
                    "content": pdf_bytes,
                },
                purpose="ocr"
            )

            # Get signed URL
            signed_url = client.files.get_signed_url(file_id=uploaded_file.id, expiry=1)

            # OCR processing
            ocr_response = client.ocr.process(
                document=DocumentURLChunk(document_url=signed_url.url),
                model="mistral-ocr-latest",
                include_image_base64=True
            )

            # Process each page
            global_counter = 1
            updated_markdown_pages = []

            for page in ocr_response.pages:
                updated_markdown = page.markdown
                for image_obj in page.images:
                    # base64 to image
                    base64_str = image_obj.image_base64
                    if base64_str.startswith("data:"):
                        base64_str = base64_str.split(",", 1)[1]
                    image_bytes = base64.b64decode(base64_str)

                    # Image extension
                    ext = Path(image_obj.id).suffix if Path(image_obj.id).suffix else ".png"
                    new_image_name = f"{pdf_base}_img_{global_counter}{ext}"
                    global_counter += 1

                    # Save image
                    image_output_path = images_dir / new_image_name
                    with open(image_output_path, "wb") as f:
                        f.write(image_bytes)

                    # Update image reference in Markdown (use relative path)
                    updated_markdown = updated_markdown.replace(
                        f"![{image_obj.id}]({image_obj.id})",
                        f"![{new_image_name}](images/{new_image_name})"
                    )
                updated_markdown_pages.append(updated_markdown)

            # Merge all pages
            final_markdown = "\n\n".join(updated_markdown_pages)
            output_markdown_path = full_output_dir / f"{pdf_base}.md"
            with open(output_markdown_path, "w", encoding="utf-8") as md_file:
                md_file.write(final_markdown)

            # Calculate relative path for return
            rel_output_dir = output_dir if output_dir else f"documents/{pdf_base}"
            rel_md_path = f"{rel_output_dir}/{pdf_base}.md"

            image_count = global_counter - 1
            result_text = f"{t('PDF_CONVERSION_DONE')}\n\n"
            result_text += f"- {t('PDF_MD_FILE')}: {rel_md_path}\n"
            result_text += f"- {t('PDF_IMAGE_COUNT')}: {image_count}\n"
            result_text += f"- {t('PDF_IMAGE_DIR')}: {rel_output_dir}/images/\n"
            result_text += f"- {t('PDF_TOTAL_PAGES')}: {len(ocr_response.pages)}"

            logger.info(f"PDF conversion done: {pdf_path} -> {rel_md_path}")

            return {
                "content": [{"type": "text", "text": result_text}]
            }

        except Exception as e:
            logger.error(f"PDF conversion failed: {e}")
            return {
                "content": [{"type": "text", "text": t("PDF_CONVERSION_FAILED", error=str(e))}],
                "is_error": True
            }

    @tool(
        "delete_file",
        "Delete specified file. Can only delete files within working directory, cannot delete directories.",
        {"file_path": str}
    )
    async def delete_file(args: dict[str, Any]) -> dict[str, Any]:
        """Delete file"""
        file_path = args.get("file_path", "")

        if not file_path:
            return {
                "content": [{"type": "text", "text": t("ERR_EMPTY_FILE_PATH")}],
                "is_error": True
            }

        if not _working_directory:
            return {
                "content": [{"type": "text", "text": t("ERR_WORKING_DIR_NOT_SET")}],
                "is_error": True
            }

        try:
            # Parse path
            if Path(file_path).is_absolute():
                full_path = Path(file_path)
            else:
                full_path = _working_directory / file_path

            # Security check: ensure path is within working directory
            if not is_path_within_working_dir(full_path):
                return {
                    "content": [{"type": "text", "text": t("ERR_ONLY_WORKING_DIR")}],
                    "is_error": True
                }

            full_path = full_path.resolve()

            # Check file exists
            if not full_path.exists():
                return {
                    "content": [{"type": "text", "text": t("ERR_FILE_NOT_EXIST", path=file_path)}],
                    "is_error": True
                }

            # Cannot delete directory
            if full_path.is_dir():
                return {
                    "content": [{"type": "text", "text": t("ERR_CANNOT_DELETE_DIR")}],
                    "is_error": True
                }

            # Delete file
            full_path.unlink()
            logger.info(f"Deleted file: {file_path}")

            return {
                "content": [{"type": "text", "text": t("FILE_DELETED", path=file_path)}]
            }

        except Exception as e:
            logger.error(f"Delete file failed: {e}")
            return {
                "content": [{"type": "text", "text": t("DELETE_FAILED", error=str(e))}],
                "is_error": True
            }

    @tool(
        "compress_folder",
        "Compress folder to ZIP archive. Must compress before sending entire folders.",
        {"folder_path": str, "output_path": str}
    )
    async def compress_folder(args: dict[str, Any]) -> dict[str, Any]:
        """Compress folder to ZIP file"""
        import zipfile
        import shutil

        folder_path = args.get("folder_path", "")
        output_path = args.get("output_path", "")

        if not folder_path:
            return {
                "content": [{"type": "text", "text": t("ERR_EMPTY_FOLDER_PATH")}],
                "is_error": True
            }

        if not _working_directory:
            return {
                "content": [{"type": "text", "text": t("ERR_WORKING_DIR_NOT_SET")}],
                "is_error": True
            }

        try:
            # Parse folder path
            if Path(folder_path).is_absolute():
                full_folder_path = Path(folder_path)
            else:
                full_folder_path = _working_directory / folder_path

            # Security check: ensure path is within working directory
            if not is_path_within_working_dir(full_folder_path):
                return {
                    "content": [{"type": "text", "text": t("ERR_ONLY_COMPRESS_WORKING_DIR")}],
                    "is_error": True
                }

            full_folder_path = full_folder_path.resolve()

            # Check folder exists
            if not full_folder_path.exists():
                return {
                    "content": [{"type": "text", "text": t("ERR_FOLDER_NOT_EXIST", path=folder_path)}],
                    "is_error": True
                }

            # Check if it's a directory
            if not full_folder_path.is_dir():
                return {
                    "content": [{"type": "text", "text": t("ERR_NOT_A_FOLDER")}],
                    "is_error": True
                }

            # Determine output path
            if not output_path:
                output_path = f"{full_folder_path.name}.zip"

            if Path(output_path).is_absolute():
                full_output_path = Path(output_path)
            else:
                full_output_path = _working_directory / output_path

            # Security check for output path
            if not is_path_within_working_dir(full_output_path):
                return {
                    "content": [{"type": "text", "text": t("ERR_OUTPUT_MUST_BE_IN_WORKING_DIR")}],
                    "is_error": True
                }

            full_output_path = full_output_path.resolve()

            # Ensure output directory exists
            full_output_path.parent.mkdir(parents=True, exist_ok=True)

            # Create ZIP file
            with zipfile.ZipFile(full_output_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                file_count = 0
                for file_path in full_folder_path.rglob('*'):
                    if file_path.is_file():
                        arcname = file_path.relative_to(full_folder_path)
                        zipf.write(file_path, arcname)
                        file_count += 1

            # Get file size
            zip_size = full_output_path.stat().st_size
            if zip_size < 1024:
                size_str = f"{zip_size} B"
            elif zip_size < 1024 * 1024:
                size_str = f"{zip_size / 1024:.1f} KB"
            else:
                size_str = f"{zip_size / (1024 * 1024):.1f} MB"

            # Return relative path
            rel_output = str(full_output_path.relative_to(_working_directory))

            logger.info(f"Compressed folder: {folder_path} -> {rel_output} ({file_count} files, {size_str})")

            return {
                "content": [{"type": "text", "text": t("COMPRESS_RESULT", path=rel_output, count=file_count, size=size_str)}]
            }

        except Exception as e:
            logger.error(f"Compress folder failed: {e}")
            return {
                "content": [{"type": "text", "text": t("COMPRESS_FAILED", error=str(e))}],
                "is_error": True
            }

    @tool(
        "delegate_task",
        "Delegate a task to a background Sub Agent. Use for research, analysis, or time-consuming tasks. The Sub Agent works independently. IMPORTANT: After delegating, you MUST use list_tasks to check status and get_task_result to retrieve results, then report findings to user.",
        {"description": str, "prompt": str}
    )
    async def delegate_task(args: dict[str, Any]) -> dict[str, Any]:
        """Delegate a task to a Sub Agent"""
        description = args.get("description", "")
        prompt = args.get("prompt", "")

        if not description or not prompt:
            return {
                "content": [{"type": "text", "text": "Error: Both description and prompt are required"}],
                "is_error": True
            }

        if not _delegate_callback:
            return {
                "content": [{"type": "text", "text": "Error: Task delegation not available"}],
                "is_error": True
            }

        try:
            task_id = await _delegate_callback(description, prompt)
            
            if task_id:
                logger.info(f"Delegated task {task_id}: {description[:50]}...")
                return {
                    "content": [{"type": "text", "text": t("DELEGATE_TASK_CREATED", task_id=task_id, description=description)}]
                }
            else:
                return {
                    "content": [{"type": "text", "text": t("DELEGATE_TASK_LIMIT", limit=_max_sub_agents)}],
                    "is_error": True
                }

        except Exception as e:
            logger.error(f"Failed to delegate task: {e}")
            return {
                "content": [{"type": "text", "text": f"Failed to delegate task: {str(e)}"}],
                "is_error": True
            }

    @tool(
        "delegate_and_review",
        """Delegate a task to a Sub Agent with automatic quality review.

The task will run in background. When completed:
1. Full result is automatically sent to user
2. Quality is automatically reviewed against your criteria
3. If not satisfactory, task is automatically retried (max 10 times)
4. Each retry sends progress report to user with result + feedback + attempt number

Use this for tasks where quality matters and you want automatic validation.
The review criteria should clearly describe what makes a good result.

Parameters:
- description: Brief task description (shown to user)
- prompt: Detailed instructions for the Sub Agent
- review_criteria: What makes a good result (guides automatic review)

Example review_criteria:
- "报告必须包含：摘要、关键发现、建议，每部分至少200字"
- "分析必须涵盖所有上传的文件，并提供具体数据支撑"
- "输出必须是有效的 JSON 格式，包含 name, age, email 字段"
""",
        {"description": str, "prompt": str, "review_criteria": str}
    )
    async def delegate_and_review(args: dict[str, Any]) -> dict[str, Any]:
        """Delegate a task to a Sub Agent with automatic quality review"""
        description = args.get("description", "")
        prompt = args.get("prompt", "")
        review_criteria = args.get("review_criteria", "")

        if not description or not prompt:
            return {
                "content": [{"type": "text", "text": "Error: description and prompt are required"}],
                "is_error": True
            }

        if not review_criteria:
            return {
                "content": [{"type": "text", "text": "Error: review_criteria is required for delegate_and_review. Use delegate_task for tasks without review."}],
                "is_error": True
            }

        if not _delegate_review_callback:
            return {
                "content": [{"type": "text", "text": "Error: Review task delegation not available"}],
                "is_error": True
            }

        try:
            task_id = await _delegate_review_callback(description, prompt, review_criteria)

            if task_id:
                logger.info(f"Delegated review task {task_id}: {description[:50]}...")
                return {
                    "content": [{"type": "text", "text": t("DELEGATE_REVIEW_TASK_CREATED", task_id=task_id, description=description)}]
                }
            else:
                return {
                    "content": [{"type": "text", "text": t("DELEGATE_TASK_LIMIT", limit=_max_sub_agents)}],
                    "is_error": True
                }

        except Exception as e:
            logger.error(f"Failed to delegate review task: {e}")
            return {
                "content": [{"type": "text", "text": f"Failed to delegate review task: {str(e)}"}],
                "is_error": True
            }

    @tool(
        "get_task_result",
        "Get the result of a delegated Sub Agent task. Use this to retrieve the output from a previously delegated task. You MUST call this after delegating a task and report the results to the user.",
        {"task_id": str}
    )
    async def get_task_result(args: dict[str, Any]) -> dict[str, Any]:
        """Get result of a Sub Agent task"""
        task_id = args.get("task_id", "")

        if not task_id:
            return {
                "content": [{"type": "text", "text": "Error: task_id is required"}],
                "is_error": True
            }

        if not _task_manager:
            return {
                "content": [{"type": "text", "text": "Error: Task manager not available"}],
                "is_error": True
            }

        try:
            task = _task_manager.get_task(task_id)
            if not task:
                return {
                    "content": [{"type": "text", "text": f"Task '{task_id}' not found"}],
                    "is_error": True
                }

            status = task.status.value
            result_text = f"Task ID: {task_id}\n"
            result_text += f"Description: {task.description}\n"
            result_text += f"Status: {status}\n"
            result_text += f"Created: {task.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"

            if status == "completed" and task.result:
                result_text += f"\nResult:\n{task.result}"
            elif status == "failed" and task.error:
                result_text += f"\nError: {task.error}"
            elif status in ("pending", "running"):
                result_text += "\nTask is still running. Please check again later."

            return {
                "content": [{"type": "text", "text": result_text}]
            }

        except Exception as e:
            logger.error(f"Failed to get task result: {e}")
            return {
                "content": [{"type": "text", "text": f"Failed to get task result: {str(e)}"}],
                "is_error": True
            }

    @tool(
        "list_tasks",
        "List all delegated Sub Agent tasks and their statuses. Shows task ID, description, status, and creation time for each task.",
        {}
    )
    async def list_tasks(args: dict[str, Any]) -> dict[str, Any]:
        """List all Sub Agent tasks"""
        if not _task_manager:
            return {
                "content": [{"type": "text", "text": "Error: Task manager not available"}],
                "is_error": True
            }

        try:
            tasks = _task_manager.get_all_tasks()

            if not tasks:
                return {
                    "content": [{"type": "text", "text": "No delegated tasks found."}]
                }

            result_text = f"Delegated Tasks ({len(tasks)}):\n\n"
            for task in tasks:
                result_text += f"- [{task['task_id']}] {task['description']}\n"
                result_text += f"  Status: {task['status']} | Created: {task['created_at']}\n"
                if task['status'] == 'completed' and 'result' in task:
                    # Show truncated result
                    result_preview = task['result'][:200] + "..." if len(task['result']) > 200 else task['result']
                    result_text += f"  Result preview: {result_preview}\n"
                elif task['status'] == 'failed' and 'error' in task:
                    result_text += f"  Error: {task['error']}\n"
                result_text += "\n"

            return {
                "content": [{"type": "text", "text": result_text}]
            }

        except Exception as e:
            logger.error(f"Failed to list tasks: {e}")
            return {
                "content": [{"type": "text", "text": f"Failed to list tasks: {str(e)}"}],
                "is_error": True
            }

    # Schedule management tools
    @tool(
        "schedule_list",
        "List all scheduled tasks for the current user. Returns task ID, name, schedule type, run count, enabled status, and last run time.",
        {}
    )
    async def schedule_list(args: dict[str, Any]) -> dict[str, Any]:
        """List all scheduled tasks"""
        logger.info(f"schedule_list called: _schedule_manager={_schedule_manager is not None}, _current_user_id={_current_user_id}")
        if not _schedule_manager or not _current_user_id:
            return {
                "content": [{"type": "text", "text": "Schedule feature not available"}],
                "is_error": True
            }

        try:
            tasks = _schedule_manager.get_tasks(_current_user_id)
            timezone = _schedule_manager.get_user_timezone(_current_user_id)

            if not tasks:
                return {
                    "content": [{"type": "text", "text": f"No scheduled tasks found.\nTimezone: {timezone}"}]
                }

            output = f"Scheduled Tasks (Timezone: {timezone}):\n\n"
            for task in tasks:
                # Determine status
                if task.max_runs and task.run_count >= task.max_runs:
                    status = "⏸️ Completed (max runs reached)"
                elif task.enabled:
                    status = "🟢 Enabled"
                else:
                    status = "🔴 Disabled"

                schedule_str = _schedule_manager.format_schedule_type(task)
                run_count_str = _schedule_manager.format_run_count(task)
                last_run = task.last_run[:16].replace("T", " ") if task.last_run else "Never"

                output += f"- {task.task_id}\n"
                output += f"  Name: {task.name}\n"
                output += f"  Schedule: {schedule_str}\n"
                output += f"  Runs: {run_count_str}\n"
                output += f"  Status: {status}\n"
                output += f"  Last Run: {last_run}\n\n"

            return {"content": [{"type": "text", "text": output}]}

        except Exception as e:
            logger.error(f"Failed to list schedules: {e}")
            return {
                "content": [{"type": "text", "text": f"Failed to list schedules: {str(e)}"}],
                "is_error": True
            }

    @tool(
        "schedule_get",
        "Get detailed information about a specific scheduled task, including schedule type, run count, and the full prompt.",
        {"task_id": str}
    )
    async def schedule_get(args: dict[str, Any]) -> dict[str, Any]:
        """Get details of a scheduled task"""
        task_id = args.get("task_id", "")

        if not _schedule_manager or not _current_user_id:
            return {
                "content": [{"type": "text", "text": "Schedule feature not available"}],
                "is_error": True
            }

        if not task_id:
            return {
                "content": [{"type": "text", "text": "Error: task_id is required"}],
                "is_error": True
            }

        try:
            task = _schedule_manager.get_task(_current_user_id, task_id)
            if not task:
                return {
                    "content": [{"type": "text", "text": f"Task '{task_id}' not found"}],
                    "is_error": True
                }

            prompt = _schedule_manager.get_task_prompt(_current_user_id, task_id)
            timezone = _schedule_manager.get_user_timezone(_current_user_id)

            # Determine status
            if task.max_runs and task.run_count >= task.max_runs:
                status = "Completed (max runs reached)"
            elif task.enabled:
                status = "Enabled"
            else:
                status = "Disabled"

            schedule_str = _schedule_manager.format_schedule_type(task)
            run_count_str = _schedule_manager.format_run_count(task)
            last_run = task.last_run[:16].replace("T", " ") if task.last_run else "Never"
            created = task.created_at[:16].replace("T", " ") if task.created_at else "Unknown"

            output = f"Task: {task_id}\n"
            output += f"Name: {task.name}\n"
            output += f"Schedule: {schedule_str}\n"
            output += f"Timezone: {timezone}\n"
            output += f"Status: {status}\n"
            output += f"Runs: {run_count_str}\n"
            output += f"Created: {created}\n"
            output += f"Last Run: {last_run}\n"
            output += f"\nPrompt:\n{prompt or '(No prompt set)'}"

            return {"content": [{"type": "text", "text": output}]}

        except Exception as e:
            logger.error(f"Failed to get schedule: {e}")
            return {
                "content": [{"type": "text", "text": f"Failed to get schedule: {str(e)}"}],
                "is_error": True
            }

    @tool(
        "schedule_create",
        """Create a new scheduled task with flexible scheduling options.

Parameters:
- task_id: 1-32 chars (alphanumeric and underscore)
- name: Task display name
- prompt: Instructions for the agent to execute
- schedule_type: daily, weekly, monthly, interval, or once (default: daily)
- time: HH:MM format (required for daily/weekly/monthly/once)
- weekdays: Comma-separated days for weekly type (e.g., "mon,wed,fri" or "1,3,5")
- month_day: Day of month (1-31) for monthly type
- interval: Interval string for interval type (e.g., "30m", "2h", "1d")
- run_date: Date (YYYY-MM-DD) for once type
- start_time: First execution time for interval type (HH:MM or YYYY-MM-DDTHH:MM)
- max_runs: Maximum executions (optional, task auto-disables when reached)
- enabled: Whether to enable immediately (default: true)""",
        {"task_id": str, "name": str, "prompt": str, "schedule_type": str, "time": str,
         "weekdays": str, "month_day": int, "interval": str, "run_date": str, "start_time": str, "max_runs": int, "enabled": bool}
    )
    async def schedule_create(args: dict[str, Any]) -> dict[str, Any]:
        """Create a new scheduled task with flexible scheduling"""
        task_id = args.get("task_id", "")
        name = args.get("name", "")
        prompt = args.get("prompt", "")
        schedule_type = args.get("schedule_type", "daily")
        time_str = args.get("time", "")
        weekdays_str = args.get("weekdays", "")
        month_day = args.get("month_day")
        interval_str = args.get("interval", "")
        start_time = args.get("start_time", "")
        run_date = args.get("run_date", "")
        max_runs = args.get("max_runs")
        enabled = args.get("enabled", True)

        if not _schedule_manager or not _current_user_id:
            return {
                "content": [{"type": "text", "text": "Schedule feature not available"}],
                "is_error": True
            }

        # Validate task_id
        valid, error = _schedule_manager.validate_task_id(task_id)
        if not valid:
            return {
                "content": [{"type": "text", "text": f"Invalid task_id: {error}"}],
                "is_error": True
            }

        # Check if task already exists
        if _schedule_manager.get_task(_current_user_id, task_id):
            return {
                "content": [{"type": "text", "text": f"Task '{task_id}' already exists"}],
                "is_error": True
            }

        # Validate required fields
        if not name:
            return {
                "content": [{"type": "text", "text": "Error: name is required"}],
                "is_error": True
            }
        if not prompt:
            return {
                "content": [{"type": "text", "text": "Error: prompt is required"}],
                "is_error": True
            }

        # Validate schedule_type
        from ..schedule import VALID_SCHEDULE_TYPES, SCHEDULE_TYPE_INTERVAL
        if schedule_type not in VALID_SCHEDULE_TYPES:
            return {
                "content": [{"type": "text", "text": f"Invalid schedule_type. Must be one of: {', '.join(VALID_SCHEDULE_TYPES)}"}],
                "is_error": True
            }

        # Parse parameters based on schedule_type
        hour, minute = 0, 0
        weekdays = None
        interval_minutes = None

        if schedule_type == SCHEDULE_TYPE_INTERVAL:
            # Interval type uses interval parameter
            if not interval_str:
                return {
                    "content": [{"type": "text", "text": "Error: interval is required for interval schedule type (e.g., '30m', '2h', '1d')"}],
                    "is_error": True
                }
            valid, interval_minutes, error = _schedule_manager.parse_interval(interval_str)
            if not valid:
                return {
                    "content": [{"type": "text", "text": f"Invalid interval: {error}"}],
                    "is_error": True
                }
        else:
            # Other types need time
            if not time_str:
                return {
                    "content": [{"type": "text", "text": "Error: time is required (HH:MM format)"}],
                    "is_error": True
                }
            valid, hour, minute, error = _schedule_manager.validate_time(time_str)
            if not valid:
                return {
                    "content": [{"type": "text", "text": f"Invalid time: {error}"}],
                    "is_error": True
                }

        # Parse weekdays for weekly type
        if schedule_type == "weekly":
            if not weekdays_str:
                return {
                    "content": [{"type": "text", "text": "Error: weekdays is required for weekly type (e.g., 'mon,wed,fri')"}],
                    "is_error": True
                }
            valid, weekdays, error = _schedule_manager.parse_weekdays(weekdays_str)
            if not valid:
                return {
                    "content": [{"type": "text", "text": f"Invalid weekdays: {error}"}],
                    "is_error": True
                }

        # Validate month_day for monthly type
        if schedule_type == "monthly":
            if not month_day:
                return {
                    "content": [{"type": "text", "text": "Error: month_day is required for monthly type (1-31)"}],
                    "is_error": True
                }
            if not (1 <= month_day <= 31):
                return {
                    "content": [{"type": "text", "text": "Error: month_day must be between 1 and 31"}],
                    "is_error": True
                }

        # Validate run_date for once type
        if schedule_type == "once":
            if not run_date:
                return {
                    "content": [{"type": "text", "text": "Error: run_date is required for once type (YYYY-MM-DD)"}],
                    "is_error": True
                }
            try:
                from datetime import datetime
                datetime.strptime(run_date, "%Y-%m-%d")
            except ValueError:
                return {
                    "content": [{"type": "text", "text": "Error: run_date must be in YYYY-MM-DD format"}],
                    "is_error": True
                }

        # Validate max_runs
        if max_runs is not None and max_runs <= 0:
            return {
                "content": [{"type": "text", "text": "Error: max_runs must be a positive integer"}],
                "is_error": True
            }

        try:
            success = _schedule_manager.add_task(
                user_id=_current_user_id,
                task_id=task_id,
                name=name,
                hour=hour,
                minute=minute,
                prompt=prompt,
                enabled=enabled,
                schedule_type=schedule_type,
                weekdays=weekdays,
                month_day=month_day,
                interval_minutes=interval_minutes,
                run_date=run_date if run_date else None,
                max_runs=max_runs,
                start_time=start_time if start_time else None
            )

            if success:
                task = _schedule_manager.get_task(_current_user_id, task_id)
                timezone = _schedule_manager.get_user_timezone(_current_user_id)
                schedule_str = _schedule_manager.format_schedule_type(task) if task else schedule_type
                status = "enabled" if enabled else "disabled"
                max_info = f"\nMax runs: {max_runs}" if max_runs else ""
                start_info = f"\nFirst run: {start_time}" if start_time else ""

                return {
                    "content": [{"type": "text", "text": f"Created scheduled task '{task_id}'\nSchedule: {schedule_str}\nTimezone: {timezone}\nStatus: {status}{max_info}{start_info}"}]
                }
            else:
                return {
                    "content": [{"type": "text", "text": "Failed to create task"}],
                    "is_error": True
                }

        except Exception as e:
            logger.error(f"Failed to create schedule: {e}")
            return {
                "content": [{"type": "text", "text": f"Failed to create schedule: {str(e)}"}],
                "is_error": True
            }

    @tool(
        "schedule_update",
        """Update an existing scheduled task. Only provide the fields you want to change.

Parameters:
- task_id: Task to update (required)
- name: New display name
- time: New time (HH:MM format)
- prompt: New instructions
- enabled: Enable/disable task
- max_runs: New max executions (-1 to remove limit)
- reset_run_count: Set to true to reset execution counter to 0""",
        {"task_id": str, "name": str, "time": str, "prompt": str, "enabled": bool, "max_runs": int, "reset_run_count": bool}
    )
    async def schedule_update(args: dict[str, Any]) -> dict[str, Any]:
        """Update a scheduled task"""
        task_id = args.get("task_id", "")
        name = args.get("name")
        time_str = args.get("time")
        prompt = args.get("prompt")
        enabled = args.get("enabled")
        max_runs = args.get("max_runs")
        reset_run_count = args.get("reset_run_count", False)

        if not _schedule_manager or not _current_user_id:
            return {
                "content": [{"type": "text", "text": "Schedule feature not available"}],
                "is_error": True
            }

        if not task_id:
            return {
                "content": [{"type": "text", "text": "Error: task_id is required"}],
                "is_error": True
            }

        # Check at least one field to update
        if all(x is None for x in [name, time_str, prompt, enabled, max_runs]) and not reset_run_count:
            return {
                "content": [{"type": "text", "text": "Error: At least one field must be provided to update"}],
                "is_error": True
            }

        # Parse time if provided
        hour = None
        minute = None
        if time_str:
            valid, hour, minute, error = _schedule_manager.validate_time(time_str)
            if not valid:
                return {
                    "content": [{"type": "text", "text": f"Invalid time: {error}"}],
                    "is_error": True
                }

        try:
            success, error = _schedule_manager.update_task(
                user_id=_current_user_id,
                task_id=task_id,
                name=name,
                hour=hour,
                minute=minute,
                prompt=prompt,
                enabled=enabled,
                max_runs=max_runs,
                reset_run_count=reset_run_count
            )

            if success:
                # Build response
                changes = []
                if name is not None:
                    changes.append(f"name -> {name}")
                if time_str:
                    changes.append(f"time -> {time_str}")
                if prompt is not None:
                    changes.append(f"prompt updated ({len(prompt)} chars)")
                if enabled is not None:
                    changes.append(f"enabled -> {enabled}")
                if max_runs is not None:
                    if max_runs == -1:
                        changes.append("max_runs -> unlimited")
                    else:
                        changes.append(f"max_runs -> {max_runs}")
                if reset_run_count:
                    changes.append("run_count -> 0")

                return {
                    "content": [{"type": "text", "text": f"Updated task '{task_id}':\n" + "\n".join(f"- {c}" for c in changes)}]
                }
            else:
                return {
                    "content": [{"type": "text", "text": error or "Failed to update task"}],
                    "is_error": True
                }

        except Exception as e:
            logger.error(f"Failed to update schedule: {e}")
            return {
                "content": [{"type": "text", "text": f"Failed to update schedule: {str(e)}"}],
                "is_error": True
            }

    @tool(
        "schedule_delete",
        "Delete a scheduled task. This action is logged and the task data is preserved in the operation log for recovery.",
        {"task_id": str}
    )
    async def schedule_delete(args: dict[str, Any]) -> dict[str, Any]:
        """Delete a scheduled task"""
        task_id = args.get("task_id", "")

        if not _schedule_manager or not _current_user_id:
            return {
                "content": [{"type": "text", "text": "Schedule feature not available"}],
                "is_error": True
            }

        if not task_id:
            return {
                "content": [{"type": "text", "text": "Error: task_id is required"}],
                "is_error": True
            }

        try:
            # Get task info before deletion for confirmation message
            task = _schedule_manager.get_task(_current_user_id, task_id)
            if not task:
                return {
                    "content": [{"type": "text", "text": f"Task '{task_id}' not found"}],
                    "is_error": True
                }

            task_name = task.name
            success = _schedule_manager.delete_task(_current_user_id, task_id)

            if success:
                return {
                    "content": [{"type": "text", "text": f"Deleted scheduled task '{task_id}' ({task_name})\nNote: Task data has been preserved in the operation log for recovery."}]
                }
            else:
                return {
                    "content": [{"type": "text", "text": f"Failed to delete task '{task_id}'"}],
                    "is_error": True
                }

        except Exception as e:
            logger.error(f"Failed to delete schedule: {e}")
            return {
                "content": [{"type": "text", "text": f"Failed to delete schedule: {str(e)}"}],
                "is_error": True
            }

    # Custom command management tools (admin only)
    @tool(
        "custom_command_list",
        "List all custom commands. Shows command name, target user, type, and description.",
        {}
    )
    async def custom_command_list(args: dict[str, Any]) -> dict[str, Any]:
        """List all custom commands"""
        if not _custom_command_manager:
            return {
                "content": [{"type": "text", "text": "Custom command feature not available"}],
                "is_error": True
            }

        try:
            commands = _custom_command_manager.get_all_commands()

            if not commands:
                return {
                    "content": [{"type": "text", "text": "No custom commands defined."}]
                }

            output = f"Custom Commands ({len(commands)}):\n\n"
            for cmd in commands:
                output += f"- /{cmd.name}\n"
                output += f"  Target User: {cmd.target_user_id}\n"
                output += f"  Type: {cmd.command_type}\n"
                output += f"  Description: {cmd.description}\n"
                if cmd.command_type == "random_media":
                    media_type = cmd.config.get("media_type", "voice")
                    balance = "enabled" if cmd.config.get("balance_mode", True) else "disabled"
                    output += f"  Media Type: {media_type}, Balance: {balance}\n"
                elif cmd.command_type == "agent_script":
                    script_preview = cmd.script[:100] + "..." if len(cmd.script) > 100 else cmd.script
                    output += f"  Script: {script_preview}\n"
                output += "\n"

            return {"content": [{"type": "text", "text": output}]}

        except Exception as e:
            logger.error(f"Failed to list custom commands: {e}")
            return {
                "content": [{"type": "text", "text": f"Failed to list custom commands: {str(e)}"}],
                "is_error": True
            }

    @tool(
        "custom_command_get",
        "Get detailed information about a specific custom command, including full script for agent_script type.",
        {"name": str}
    )
    async def custom_command_get(args: dict[str, Any]) -> dict[str, Any]:
        """Get details of a custom command"""
        name = args.get("name", "")

        if not _custom_command_manager:
            return {
                "content": [{"type": "text", "text": "Custom command feature not available"}],
                "is_error": True
            }

        if not name:
            return {
                "content": [{"type": "text", "text": "Error: name is required"}],
                "is_error": True
            }

        try:
            cmd = _custom_command_manager.get_command(name)
            if not cmd:
                return {
                    "content": [{"type": "text", "text": f"Command '/{name}' not found"}],
                    "is_error": True
                }

            output = f"Command: /{cmd.name}\n"
            output += f"Target User ID: {cmd.target_user_id}\n"
            output += f"Type: {cmd.command_type}\n"
            output += f"Description: {cmd.description}\n"
            output += f"Created By: {cmd.created_by}\n"
            output += f"Created At: {cmd.created_at}\n"

            if cmd.command_type == "random_media":
                output += f"\nMedia Configuration:\n"
                output += f"  Folder: {cmd.config.get('media_folder', cmd.name)}\n"
                output += f"  Type: {cmd.config.get('media_type', 'voice')}\n"
                output += f"  Balance Mode: {'enabled' if cmd.config.get('balance_mode', True) else 'disabled'}\n"

                # Get media files count
                files = _custom_command_manager.list_media_files(name)
                output += f"  Files Count: {len(files)}\n"
            elif cmd.command_type == "agent_script":
                output += f"\nScript:\n{cmd.script or '(No script defined)'}"

            return {"content": [{"type": "text", "text": output}]}

        except Exception as e:
            logger.error(f"Failed to get custom command: {e}")
            return {
                "content": [{"type": "text", "text": f"Failed to get custom command: {str(e)}"}],
                "is_error": True
            }

    @tool(
        "custom_command_create",
        """Create a new custom command for a specific user.

Parameters:
- name: Command name (alphanumeric only, max 20 chars, without /)
- target_user_id: Telegram user ID who can use this command
- description: Short description shown in help
- command_type: "random_media" or "agent_script" (default: random_media)
- media_type: For random_media type - voice, photo, video, or document (default: voice)
- balance_mode: For random_media type - prioritize least-sent files (default: true)
- script: For agent_script type - instructions for the agent to execute""",
        {"name": str, "target_user_id": int, "description": str, "command_type": str,
         "media_type": str, "balance_mode": bool, "script": str}
    )
    async def custom_command_create(args: dict[str, Any]) -> dict[str, Any]:
        """Create a new custom command"""
        logger.info(f"custom_command_create called with args: {args}")
        logger.info(f"Current user: {_current_user_id}, Admin users: {_admin_user_ids}")

        name = args.get("name", "")
        target_user_id = args.get("target_user_id")
        description = args.get("description", "")
        command_type = args.get("command_type", "random_media")
        media_type = args.get("media_type", "voice")
        balance_mode = args.get("balance_mode", True)
        script = args.get("script", "")

        if not _custom_command_manager or not _current_user_id:
            return {
                "content": [{"type": "text", "text": "Custom command feature not available"}],
                "is_error": True
            }

        # Admin permission check
        if _current_user_id not in _admin_user_ids:
            return {
                "content": [{"type": "text", "text": "Error: Only admin users can create custom commands"}],
                "is_error": True
            }

        if not name:
            return {
                "content": [{"type": "text", "text": "Error: name is required"}],
                "is_error": True
            }
        if not target_user_id:
            return {
                "content": [{"type": "text", "text": "Error: target_user_id is required"}],
                "is_error": True
            }
        if not description:
            return {
                "content": [{"type": "text", "text": "Error: description is required"}],
                "is_error": True
            }

        # Validate command_type
        if command_type not in ("random_media", "agent_script"):
            return {
                "content": [{"type": "text", "text": "Error: command_type must be 'random_media' or 'agent_script'"}],
                "is_error": True
            }

        # For agent_script, script is required
        if command_type == "agent_script" and not script:
            return {
                "content": [{"type": "text", "text": "Error: script is required for agent_script type"}],
                "is_error": True
            }

        try:
            config = {}
            if command_type == "random_media":
                config = {
                    "media_type": media_type,
                    "balance_mode": balance_mode
                }

            success, message = _custom_command_manager.create_command(
                name=name,
                target_user_id=target_user_id,
                description=description,
                created_by=_current_user_id,
                command_type=command_type,
                config=config,
                script=script
            )

            if success:
                result = f"Created command /{name}\n"
                result += f"Target User: {target_user_id}\n"
                result += f"Type: {command_type}\n"
                result += f"Description: {description}"
                if command_type == "random_media":
                    folder = _custom_command_manager.get_media_folder(name)
                    result += f"\n\nMedia folder created at: {folder}"
                    result += f"\nMedia type: {media_type}"
                    result += "\nYou can now add media files to this command's folder."
                return {"content": [{"type": "text", "text": result}]}
            else:
                return {
                    "content": [{"type": "text", "text": message}],
                    "is_error": True
                }

        except Exception as e:
            logger.error(f"Failed to create custom command: {e}")
            return {
                "content": [{"type": "text", "text": f"Failed to create custom command: {str(e)}"}],
                "is_error": True
            }

    @tool(
        "custom_command_update",
        """Update an existing custom command. Only provide the fields you want to change.

Parameters:
- name: Command name to update (required)
- description: New description
- command_type: Change type to "random_media" or "agent_script"
- script: New script for agent_script type
- media_type: For random_media type - voice, photo, video, or document
- balance_mode: For random_media type - true/false""",
        {"name": str, "description": str, "command_type": str, "script": str,
         "media_type": str, "balance_mode": bool}
    )
    async def custom_command_update(args: dict[str, Any]) -> dict[str, Any]:
        """Update a custom command"""
        name = args.get("name", "")
        description = args.get("description")
        command_type = args.get("command_type")
        script = args.get("script")
        media_type = args.get("media_type")
        balance_mode = args.get("balance_mode")

        if not _custom_command_manager:
            return {
                "content": [{"type": "text", "text": "Custom command feature not available"}],
                "is_error": True
            }

        # Admin permission check
        if _current_user_id not in _admin_user_ids:
            return {
                "content": [{"type": "text", "text": "Error: Only admin users can update custom commands"}],
                "is_error": True
            }

        if not name:
            return {
                "content": [{"type": "text", "text": "Error: name is required"}],
                "is_error": True
            }

        # Check at least one field to update
        if all(x is None for x in [description, command_type, script, media_type, balance_mode]):
            return {
                "content": [{"type": "text", "text": "Error: At least one field must be provided to update"}],
                "is_error": True
            }

        try:
            # Build config update
            config = {}
            if media_type is not None:
                config["media_type"] = media_type
            if balance_mode is not None:
                config["balance_mode"] = balance_mode

            success, message = _custom_command_manager.update_command(
                name=name,
                description=description,
                config=config if config else None,
                script=script,
                command_type=command_type
            )

            if success:
                changes = []
                if description is not None:
                    changes.append(f"description -> {description}")
                if command_type is not None:
                    changes.append(f"command_type -> {command_type}")
                if script is not None:
                    changes.append(f"script updated ({len(script)} chars)")
                if media_type is not None:
                    changes.append(f"media_type -> {media_type}")
                if balance_mode is not None:
                    changes.append(f"balance_mode -> {balance_mode}")

                return {
                    "content": [{"type": "text", "text": f"Updated command /{name}:\n" + "\n".join(f"- {c}" for c in changes)}]
                }
            else:
                return {
                    "content": [{"type": "text", "text": message}],
                    "is_error": True
                }

        except Exception as e:
            logger.error(f"Failed to update custom command: {e}")
            return {
                "content": [{"type": "text", "text": f"Failed to update custom command: {str(e)}"}],
                "is_error": True
            }

    @tool(
        "custom_command_delete",
        "Delete a custom command. The media folder will be preserved for safety.",
        {"name": str}
    )
    async def custom_command_delete(args: dict[str, Any]) -> dict[str, Any]:
        """Delete a custom command"""
        name = args.get("name", "")

        if not _custom_command_manager:
            return {
                "content": [{"type": "text", "text": "Custom command feature not available"}],
                "is_error": True
            }

        # Admin permission check
        if _current_user_id not in _admin_user_ids:
            return {
                "content": [{"type": "text", "text": "Error: Only admin users can delete custom commands"}],
                "is_error": True
            }

        if not name:
            return {
                "content": [{"type": "text", "text": "Error: name is required"}],
                "is_error": True
            }

        try:
            success, message = _custom_command_manager.delete_command(name)

            if success:
                return {"content": [{"type": "text", "text": message}]}
            else:
                return {
                    "content": [{"type": "text", "text": message}],
                    "is_error": True
                }

        except Exception as e:
            logger.error(f"Failed to delete custom command: {e}")
            return {
                "content": [{"type": "text", "text": f"Failed to delete custom command: {str(e)}"}],
                "is_error": True
            }

    @tool(
        "custom_command_rename",
        "Rename a custom command. Both admin and target user will see the new name.",
        {"old_name": str, "new_name": str}
    )
    async def custom_command_rename(args: dict[str, Any]) -> dict[str, Any]:
        """Rename a custom command"""
        old_name = args.get("old_name", "")
        new_name = args.get("new_name", "")

        if not _custom_command_manager:
            return {
                "content": [{"type": "text", "text": "Custom command feature not available"}],
                "is_error": True
            }

        # Admin permission check
        if _current_user_id not in _admin_user_ids:
            return {
                "content": [{"type": "text", "text": "Error: Only admin users can rename custom commands"}],
                "is_error": True
            }

        if not old_name or not new_name:
            return {
                "content": [{"type": "text", "text": "Error: both old_name and new_name are required"}],
                "is_error": True
            }

        try:
            success, message = _custom_command_manager.rename_command(old_name, new_name)

            if success:
                return {"content": [{"type": "text", "text": message}]}
            else:
                return {
                    "content": [{"type": "text", "text": message}],
                    "is_error": True
                }

        except Exception as e:
            logger.error(f"Failed to rename custom command: {e}")
            return {
                "content": [{"type": "text", "text": f"Failed to rename custom command: {str(e)}"}],
                "is_error": True
            }

    @tool(
        "custom_command_list_media",
        "List all media files for a random_media type command with their statistics.",
        {"name": str}
    )
    async def custom_command_list_media(args: dict[str, Any]) -> dict[str, Any]:
        """List media files for a custom command"""
        name = args.get("name", "")

        if not _custom_command_manager:
            return {
                "content": [{"type": "text", "text": "Custom command feature not available"}],
                "is_error": True
            }

        if not name:
            return {
                "content": [{"type": "text", "text": "Error: name is required"}],
                "is_error": True
            }

        try:
            cmd = _custom_command_manager.get_command(name)
            if not cmd:
                return {
                    "content": [{"type": "text", "text": f"Command '/{name}' not found"}],
                    "is_error": True
                }

            if cmd.command_type != "random_media":
                return {
                    "content": [{"type": "text", "text": f"Command '/{name}' is not a random_media type"}],
                    "is_error": True
                }

            files = _custom_command_manager.list_media_files(name)

            if not files:
                folder = _custom_command_manager.get_media_folder(name)
                return {
                    "content": [{"type": "text", "text": f"No media files found for /{name}\nMedia folder: {folder}"}]
                }

            output = f"Media files for /{name} ({len(files)} files):\n\n"
            for f in files:
                last_sent = f["last_sent"][:16].replace("T", " ") if f["last_sent"] else "Never"
                size_kb = f["size"] / 1024
                output += f"- {f['filename']}\n"
                output += f"  Size: {size_kb:.1f} KB, Sent: {f['count']} times, Last: {last_sent}\n"

            return {"content": [{"type": "text", "text": output}]}

        except Exception as e:
            logger.error(f"Failed to list media files: {e}")
            return {
                "content": [{"type": "text", "text": f"Failed to list media files: {str(e)}"}],
                "is_error": True
            }

    return [
        send_telegram_message,
        send_telegram_file,
        web_search,
        web_fetch,
        pdf_to_markdown,
        delete_file,
        compress_folder,
        delegate_task,
        delegate_and_review,
        get_task_result,
        list_tasks,
        schedule_list,
        schedule_get,
        schedule_create,
        schedule_update,
        schedule_delete,
        custom_command_list,
        custom_command_get,
        custom_command_create,
        custom_command_update,
        custom_command_delete,
        custom_command_rename,
        custom_command_list_media
    ]
