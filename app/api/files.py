# app/api/files.py
import logging
from fastapi import APIRouter, HTTPException, Response
from app.tools.storage import download_file_from_storage, STORAGE_PROVIDER

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/files", tags=["files"])


@router.get("/{filename}")
async def get_file(filename: str):
    """
    Serve files from storage.
    This is primarily used for Tigris storage in production where
    direct file access isn't available.
    """
    try:
        # Download file from storage
        file_data = download_file_from_storage(filename)
        
        # Determine content type based on file extension
        content_type = "application/octet-stream"
        if filename.lower().endswith('.pdf'):
            content_type = "application/pdf"
        elif filename.lower().endswith('.png'):
            content_type = "image/png"
        elif filename.lower().endswith('.jpg') or filename.lower().endswith('.jpeg'):
            content_type = "image/jpeg"
        elif filename.lower().endswith('.txt'):
            content_type = "text/plain"
        
        # Return file with appropriate headers
        return Response(
            content=file_data,
            media_type=content_type,
            headers={
                "Content-Disposition": f"inline; filename={filename}",
                "Cache-Control": "public, max-age=3600"  # Cache for 1 hour
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to serve file {filename}: {e}")
        raise HTTPException(status_code=404, detail=f"File not found: {filename}")


@router.get("/{filename}/download")
async def download_file(filename: str):
    """
    Force download of files from storage.
    """
    try:
        # Download file from storage
        file_data = download_file_from_storage(filename)
        
        # Determine content type based on file extension
        content_type = "application/octet-stream"
        if filename.lower().endswith('.pdf'):
            content_type = "application/pdf"
        
        # Return file with download headers
        return Response(
            content=file_data,
            media_type=content_type,
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Cache-Control": "no-cache"
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to download file {filename}: {e}")
        raise HTTPException(status_code=404, detail=f"File not found: {filename}") 