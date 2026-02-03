"""Files API routes."""

import os
import logging
import mimetypes
from pathlib import Path
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, status, Depends, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..dependencies import (
    get_current_user_id,
    get_working_directory,
    get_user_manager
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
