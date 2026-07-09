"""API routes for virtual drive data pool management."""
import logging
from fastapi import APIRouter, HTTPException, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from backend.database import get_db
from backend.api.schemas import VirtualDriveFileRequest, VirtualDriveFileResponse
from backend.engine.virtual_drive import VirtualDrive
from backend.models.virtual_drive import VirtualDriveFile

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/files", response_model=List[VirtualDriveFileResponse])
async def list_files(
    category: Optional[str] = None,
    file_type: Optional[str] = None,
    active_only: bool = True,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
) -> List[dict]:
    """List files in virtual drive."""
    try:
        drive = VirtualDrive(db)
        files = await drive.list_files(
            category=category,
            file_type=file_type,
            active_only=active_only,
        )
        
        return [
            {
                "id": f.id,
                "file_path": f.file_path,
                "file_name": f.file_name,
                "file_type": f.file_type,
                "file_size_bytes": f.file_size_bytes,
                "file_category": f.file_category,
                "version": f.version,
                "access_count": f.access_count,
                "created_at": f.created_at,
                "updated_at": f.updated_at,
            }
            for f in files[:limit]
        ]
    except Exception as e:
        logger.error(f"Failed to list files: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.post("/files", response_model=VirtualDriveFileResponse, status_code=status.HTTP_201_CREATED)
async def upload_file(
    request: VirtualDriveFileRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Upload/save file to virtual drive."""
    try:
        drive = VirtualDrive(db)
        file = await drive.save_file(
            file_path=request.file_path,
            content=request.content,
            file_type=request.file_type,
            metadata=request.metadata,
            category=request.category,
        )
        
        if not file:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to save file",
            )
        
        logger.info(f"File uploaded: {file.file_path}")
        
        return {
            "id": file.id,
            "file_path": file.file_path,
            "file_name": file.file_name,
            "file_type": file.file_type,
            "file_size_bytes": file.file_size_bytes,
            "file_category": file.file_category,
            "version": file.version,
            "access_count": file.access_count,
            "created_at": file.created_at,
            "updated_at": file.updated_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to upload file: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/files/{file_id}", response_model=VirtualDriveFileResponse)
async def download_file(
    file_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Download/retrieve file from virtual drive."""
    try:
        stmt = select(VirtualDriveFile).where(VirtualDriveFile.id == file_id)
        result = await db.execute(stmt)
        file = result.scalars().first()
        
        if not file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found",
            )
        
        file.access_count += 1
        file.last_accessed = datetime.utcnow()
        await db.commit()
        
        logger.info(f"File downloaded: {file.file_path}")
        
        return {
            "id": file.id,
            "file_path": file.file_path,
            "file_name": file.file_name,
            "file_type": file.file_type,
            "file_size_bytes": file.file_size_bytes,
            "file_category": file.file_category,
            "version": file.version,
            "access_count": file.access_count,
            "created_at": file.created_at,
            "updated_at": file.updated_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to download file: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.get("/files/{file_id}/content")
async def get_file_content(
    file_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get file content (for JSON/YAML/CSV files)."""
    try:
        stmt = select(VirtualDriveFile).where(VirtualDriveFile.id == file_id)
        result = await db.execute(stmt)
        file = result.scalars().first()
        
        if not file:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found",
            )
        
        if not file.content:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File has no text content",
            )
        
        file.access_count += 1
        file.last_accessed = datetime.utcnow()
        await db.commit()
        
        content = file.content
        if file.file_type == "json":
            import json
            content = json.loads(content)
        elif file.file_type == "yaml":
            import yaml
            content = yaml.safe_load(content)
        
        return {
            "file_id": str(file.id),
            "file_path": file.file_path,
            "file_type": file.file_type,
            "content": content,
            "version": file.version,
            "access_count": file.access_count,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get file content: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@router.delete("/files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_file(
    file_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    """Delete file from virtual drive (soft delete)."""
    try:
        drive = VirtualDrive(db)
        success = await drive.delete_file(str(file_id))
        
        if not success:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to delete file",
            )
        
        logger.info(f"File deleted: {file_id}")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete file: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
