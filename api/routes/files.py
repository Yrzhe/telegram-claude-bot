"""Files API routes."""

import os
import logging
import mimetypes
import shutil
import tempfile
import zipfile
import asyncio
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, status, Depends, Query, BackgroundTasks
from fastapi.responses import FileResponse
from pydantic import BaseModel
import httpx

from ..dependencies import (
    get_current_user_id,
    get_working_directory,
    get_user_manager,
    get_bot_token
)

logger = logging.getLogger(__name__)

router = APIRouter()


class FileItem(BaseModel):
    """File or directory item."""
    name: str
    type: str  # "file" or "directory"
    size: Optional[int] = None
    modified: Optional[str] = None
    mime_type: Optional[str] = None


class StorageInfo(BaseModel):
    """Storage quota information."""
    used_bytes: int
    quota_bytes: int
    used_percent: float


class FileListResponse(BaseModel):
    """Response for file listing."""
    path: str
    items: List[FileItem]
    storage: StorageInfo


class MkdirRequest(BaseModel):
    """Request to create directory."""
    path: str


class MkdirResponse(BaseModel):
    """Response for directory creation."""
    success: bool
    path: str


class DeleteResponse(BaseModel):
    """Response for file deletion."""
    success: bool
    path: str


def sanitize_path(base_dir: str, user_path: str) -> Path:
    """
    Sanitize and validate user-provided path.

    Prevents directory traversal attacks.

    Args:
        base_dir: User's base directory
        user_path: User-provided path

    Returns:
        Resolved absolute path

    Raises:
        HTTPException: If path is invalid or outside base_dir
    """
    base = Path(base_dir).resolve()

    # Clean up the path
    if user_path.startswith("/"):
        user_path = user_path[1:]

    # Resolve the full path
    try:
        full_path = (base / "data" / user_path).resolve()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid path"
        )

    # Ensure path is within user's directory
    data_dir = (base / "data").resolve()
    if not str(full_path).startswith(str(data_dir)):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied: path outside user directory"
        )

    return full_path


@router.get("", response_model=FileListResponse)
async def list_files(
    path: str = Query("/", description="Directory path to list"),
    user_id: int = Depends(get_current_user_id),
    working_dir: str = Depends(get_working_directory),
    user_manager = Depends(get_user_manager)
):
    """
    List files and directories in the specified path.
    """
    # Sanitize path
    dir_path = sanitize_path(working_dir, path)

    if not dir_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Directory not found"
        )

    if not dir_path.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path is not a directory"
        )

    # List directory contents
    items = []
    try:
        for entry in sorted(dir_path.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower())):
            if entry.name.startswith("."):
                continue  # Skip hidden files

            stat = entry.stat()
            modified = datetime.fromtimestamp(stat.st_mtime).isoformat()

            if entry.is_dir():
                items.append(FileItem(
                    name=entry.name,
                    type="directory",
                    modified=modified
                ))
            else:
                mime_type, _ = mimetypes.guess_type(entry.name)
                items.append(FileItem(
                    name=entry.name,
                    type="file",
                    size=stat.st_size,
                    modified=modified,
                    mime_type=mime_type
                ))
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Permission denied"
        )

    # Get storage info
    storage_info = user_manager.get_user_storage_info(user_id)
    quota_bytes = storage_info.get("quota_bytes", 5 * 1024 * 1024 * 1024)
    used_bytes = storage_info.get("used_bytes", 0)

    return FileListResponse(
        path=path,
        items=items,
        storage=StorageInfo(
            used_bytes=used_bytes,
            quota_bytes=quota_bytes,
            used_percent=round(used_bytes / quota_bytes * 100, 2) if quota_bytes > 0 else 0
        )
    )


@router.get("/download/{file_path:path}")
async def download_file(
    file_path: str,
    user_id: int = Depends(get_current_user_id),
    working_dir: str = Depends(get_working_directory)
):
    """
    Download a file.
    """
    # Sanitize path
    full_path = sanitize_path(working_dir, file_path)

    if not full_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )

    if not full_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Path is not a file"
        )

    # Determine media type
    media_type, _ = mimetypes.guess_type(full_path.name)
    if media_type is None:
        media_type = "application/octet-stream"

    return FileResponse(
        path=full_path,
        filename=full_path.name,
        media_type=media_type
    )


@router.delete("/{file_path:path}", response_model=DeleteResponse)
async def delete_file(
    file_path: str,
    user_id: int = Depends(get_current_user_id),
    working_dir: str = Depends(get_working_directory)
):
    """
    Delete a file or empty directory.
    """
    # Sanitize path
    full_path = sanitize_path(working_dir, file_path)

    if not full_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found"
        )

    # Prevent deleting important directories
    protected = ["uploads", "documents", "analysis", "schedules"]
    if full_path.name in protected and full_path.parent.name == "data":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot delete protected directory"
        )

    try:
        if full_path.is_dir():
            # Only delete empty directories
            if any(full_path.iterdir()):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Directory is not empty"
                )
            full_path.rmdir()
        else:
            full_path.unlink()

        logger.info(f"User {user_id} deleted: {file_path}")
        return DeleteResponse(success=True, path=file_path)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Delete failed: {str(e)}"
        )


@router.post("/mkdir", response_model=MkdirResponse)
async def create_directory(
    request: MkdirRequest,
    user_id: int = Depends(get_current_user_id),
    working_dir: str = Depends(get_working_directory)
):
    """
    Create a new directory.
    """
    # Sanitize path
    dir_path = sanitize_path(working_dir, request.path)

    if dir_path.exists():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Path already exists"
        )

    try:
        dir_path.mkdir(parents=True, exist_ok=False)
        logger.info(f"User {user_id} created directory: {request.path}")
        return MkdirResponse(success=True, path=request.path)

    except Exception as e:
        logger.error(f"Mkdir failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create directory: {str(e)}"
        )


@router.get("/storage", response_model=StorageInfo)
async def get_storage_info(
    user_id: int = Depends(get_current_user_id),
    user_manager = Depends(get_user_manager)
):
    """
    Get storage quota information.
    """
    storage_info = user_manager.get_user_storage_info(user_id)
    quota_bytes = storage_info.get("quota_bytes", 5 * 1024 * 1024 * 1024)
    used_bytes = storage_info.get("used_bytes", 0)

    return StorageInfo(
        used_bytes=used_bytes,
        quota_bytes=quota_bytes,
        used_percent=round(used_bytes / quota_bytes * 100, 2) if quota_bytes > 0 else 0
    )


# Batch operation models
class BatchPathsRequest(BaseModel):
    """Request with multiple file paths."""
    paths: List[str]


class BatchResponse(BaseModel):
    """Response for batch operations."""
    success: bool
    message: str = ""


async def send_file_to_telegram(bot_token: str, user_id: int, file_path: Path, caption: str = ""):
    """Send a file to user via Telegram Bot API."""
    url = f"https://api.telegram.org/bot{bot_token}/sendDocument"

    async with httpx.AsyncClient(timeout=120.0) as client:
        with open(file_path, "rb") as f:
            files = {"document": (file_path.name, f)}
            data = {"chat_id": user_id}
            if caption:
                data["caption"] = caption

            response = await client.post(url, data=data, files=files)
            response.raise_for_status()
            return response.json()


def delete_file_or_dir(path: Path):
    """Recursively delete a file or directory."""
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


@router.post("/batch/delete", response_model=BatchResponse)
async def batch_delete(
    request: BatchPathsRequest,
    user_id: int = Depends(get_current_user_id),
    working_dir: str = Depends(get_working_directory)
):
    """
    Delete multiple files/directories.
    """
    if not request.paths:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No paths provided"
        )

    # Validate all paths first
    paths_to_delete = []
    protected = ["uploads", "documents", "analysis", "schedules"]

    for path in request.paths:
        full_path = sanitize_path(working_dir, path)

        if not full_path.exists():
            continue  # Skip non-existent files

        # Check protected directories
        if full_path.name in protected and full_path.parent.name == "data":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Cannot delete protected directory: {full_path.name}"
            )

        paths_to_delete.append(full_path)

    # Delete all paths
    deleted_count = 0
    for full_path in paths_to_delete:
        try:
            delete_file_or_dir(full_path)
            deleted_count += 1
        except Exception as e:
            logger.error(f"Failed to delete {full_path}: {e}")

    logger.info(f"User {user_id} batch deleted {deleted_count} items")

    return BatchResponse(
        success=True,
        message=f"Deleted {deleted_count} items"
    )


@router.post("/batch/download", response_model=BatchResponse)
async def batch_download(
    request: BatchPathsRequest,
    background_tasks: BackgroundTasks,
    user_id: int = Depends(get_current_user_id),
    working_dir: str = Depends(get_working_directory),
    bot_token: str = Depends(get_bot_token)
):
    """
    Download multiple files by sending them via Telegram.

    - Single file: sends the file directly
    - Multiple files or folder: creates a zip and sends it
    """
    if not request.paths:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No paths provided"
        )

    if not bot_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Bot token not configured"
        )

    # Validate and collect paths
    valid_paths = []
    for path in request.paths:
        full_path = sanitize_path(working_dir, path)
        if full_path.exists():
            valid_paths.append((path, full_path))

    if not valid_paths:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No valid files found"
        )

    # Determine if we need to zip
    need_zip = (
        len(valid_paths) > 1 or
        valid_paths[0][1].is_dir()
    )

    temp_zip_path = None

    try:
        if need_zip:
            # Create temporary zip file
            temp_dir = tempfile.mkdtemp()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            zip_name = f"files_{timestamp}.zip"
            temp_zip_path = Path(temp_dir) / zip_name

            with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for rel_path, full_path in valid_paths:
                    if full_path.is_dir():
                        # Add directory contents
                        for file_path in full_path.rglob('*'):
                            if file_path.is_file():
                                # Create relative path within zip
                                arc_name = str(Path(rel_path.lstrip('/')) / file_path.relative_to(full_path))
                                zipf.write(file_path, arc_name)
                    else:
                        # Add single file
                        arc_name = Path(rel_path.lstrip('/')).name
                        zipf.write(full_path, arc_name)

            # Send the zip file
            await send_file_to_telegram(
                bot_token,
                user_id,
                temp_zip_path,
                f"📦 {len(valid_paths)} files"
            )

            logger.info(f"User {user_id} batch downloaded {len(valid_paths)} items as zip")

        else:
            # Send single file directly
            _, full_path = valid_paths[0]
            await send_file_to_telegram(
                bot_token,
                user_id,
                full_path,
                f"📄 {full_path.name}"
            )

            logger.info(f"User {user_id} downloaded file: {full_path.name}")

        return BatchResponse(
            success=True,
            message=f"Sent {len(valid_paths)} file(s) to Telegram"
        )

    except httpx.HTTPStatusError as e:
        logger.error(f"Telegram API error: {e}")
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to send file to Telegram"
        )
    except Exception as e:
        logger.error(f"Batch download failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Download failed: {str(e)}"
        )
    finally:
        # Cleanup temp zip file
        if temp_zip_path and temp_zip_path.exists():
            try:
                temp_zip_path.unlink()
                temp_zip_path.parent.rmdir()
            except Exception:
                pass
