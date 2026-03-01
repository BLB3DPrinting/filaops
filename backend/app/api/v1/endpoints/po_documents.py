"""
Purchase Order Documents API Endpoints

Handles multi-file document storage for purchase orders:
- Upload documents (invoice, packing slip, receipt, etc.)
- List documents for a PO
- Download/delete documents
- Supports local storage and Google Drive
"""
import os
import uuid
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File, Form, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.db.session import get_db
from app.logging_config import get_logger
from app.models.purchase_order import PurchaseOrder
from app.models.purchase_order_document import PurchaseOrderDocument
from app.api.v1.endpoints.auth import get_current_user
from app.models.user import User
from app.schemas.purchasing import (
    PODocumentResponse,
    PODocumentUpdate,
    DocumentType,
)

router = APIRouter()
logger = get_logger(__name__)

# Upload directory for local storage (resolved relative to this file, works in Docker and CI)
UPLOAD_DIR = Path(__file__).resolve().parent.parent.parent.parent.parent / "uploads" / "po_documents"


def _ensure_upload_dir():
    """Ensure upload directory exists"""
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def _get_safe_filename(original_filename: str, po_number: str) -> str:
    """Generate a safe, unique filename"""
    ext = os.path.splitext(original_filename)[1] or ".pdf"
    timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
    unique_id = str(uuid.uuid4())[:8]
    return f"{po_number}_{timestamp}_{unique_id}{ext}"


def _document_to_response(doc: PurchaseOrderDocument) -> PODocumentResponse:
    """Convert document model to response schema"""
    return PODocumentResponse(
        id=doc.id,
        purchase_order_id=doc.purchase_order_id,
        document_type=doc.document_type,
        file_name=doc.file_name,
        original_file_name=doc.original_file_name,
        file_url=doc.file_url,
        file_path=doc.file_path,
        storage_type=doc.storage_type,
        file_size=doc.file_size,
        mime_type=doc.mime_type,
        notes=doc.notes,
        uploaded_by=doc.uploaded_by,
        uploaded_at=doc.uploaded_at,
        download_url=doc.download_url,
        preview_url=doc.preview_url,
    )


# ============================================================================
# Document Upload
# ============================================================================

@router.post("/{po_id}/documents", response_model=PODocumentResponse, status_code=201)
async def upload_document(
    po_id: int,
    file: UploadFile = File(...),
    document_type: str = Form("other"),
    notes: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Upload a document to a purchase order
    
    Supports multiple files per PO with categorization:
    - invoice: Vendor invoice
    - packing_slip: Packing slip / delivery note
    - receipt: Payment receipt
    - quote: Price quote
    - shipping_label: Shipping label
    - other: Other documents
    
    Files are stored in Google Drive if configured, otherwise locally.
    """
    # Verify PO exists
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    
    # Validate document type
    valid_types = [t.value for t in DocumentType]
    if document_type not in valid_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid document type. Must be one of: {', '.join(valid_types)}"
        )
    
    # Validate file type
    allowed_extensions = {'.pdf', '.jpg', '.jpeg', '.png', '.webp', '.xlsx', '.xls', '.csv', '.doc', '.docx'}
    original_filename = file.filename or "document"
    ext = os.path.splitext(original_filename)[1].lower()
    
    if ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext}' not allowed. Allowed: {', '.join(allowed_extensions)}"
        )
    
    # Read file content
    file_content = await file.read()
    file_size = len(file_content)
    
    # Detect mime type
    mime_type = file.content_type or mimetypes.guess_type(original_filename)[0] or "application/octet-stream"
    
    # Generate safe filename
    safe_filename = _get_safe_filename(original_filename, po.po_number)
    
    # Storage configuration
    storage_type = "local"
    file_url = None
    file_path = None
    # Save to local storage
    _ensure_upload_dir()
    local_path = os.path.join(UPLOAD_DIR, safe_filename)
    with open(local_path, "wb") as f:
        f.write(file_content)
    file_path = local_path
    logger.info(f"Saved {safe_filename} locally to {local_path}")
    
    # Create document record
    doc = PurchaseOrderDocument(
        purchase_order_id=po_id,
        document_type=document_type,
        file_name=safe_filename,
        original_file_name=original_filename,
        file_url=file_url,
        file_path=file_path,
        storage_type=storage_type,
        file_size=file_size,
        mime_type=mime_type,
        notes=notes,
        uploaded_by=current_user.email,
        uploaded_at=datetime.now(timezone.utc),
    )
    
    db.add(doc)
    db.commit()
    db.refresh(doc)
    
    logger.info(f"Created document record {doc.id} for PO {po.po_number}: {document_type}")
    
    return _document_to_response(doc)


# ============================================================================
# List Documents
# ============================================================================

@router.get("/{po_id}/documents", response_model=List[PODocumentResponse])
async def list_documents(
    po_id: int,
    document_type: Optional[str] = Query(None, description="Filter by document type"),
    db: Session = Depends(get_db),
):
    """
    List all documents attached to a purchase order
    
    Optionally filter by document type.
    """
    # Verify PO exists
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    
    query = db.query(PurchaseOrderDocument).filter(
        PurchaseOrderDocument.purchase_order_id == po_id
    )
    
    if document_type:
        query = query.filter(PurchaseOrderDocument.document_type == document_type)
    
    documents = query.order_by(desc(PurchaseOrderDocument.uploaded_at)).all()
    
    return [_document_to_response(doc) for doc in documents]


# ============================================================================
# Get Single Document
# ============================================================================

@router.get("/{po_id}/documents/{doc_id}", response_model=PODocumentResponse)
async def get_document(
    po_id: int,
    doc_id: int,
    db: Session = Depends(get_db),
):
    """Get document details by ID"""
    doc = db.query(PurchaseOrderDocument).filter(
        PurchaseOrderDocument.id == doc_id,
        PurchaseOrderDocument.purchase_order_id == po_id
    ).first()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return _document_to_response(doc)


# ============================================================================
# Download Document
# ============================================================================

@router.get("/{po_id}/documents/{doc_id}/download")
async def download_document(
    po_id: int,
    doc_id: int,
    db: Session = Depends(get_db),
):
    """
    Download a document
    
    Returns the file for download.
    """
    doc = db.query(PurchaseOrderDocument).filter(
        PurchaseOrderDocument.id == doc_id,
        PurchaseOrderDocument.purchase_order_id == po_id
    ).first()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Local file
    if doc.file_path and os.path.exists(doc.file_path):
        return FileResponse(
            path=doc.file_path,
            filename=doc.original_file_name or doc.file_name,
            media_type=doc.mime_type or "application/octet-stream"
        )
    
    raise HTTPException(status_code=404, detail="File not found on storage")


# ============================================================================
# Update Document Metadata
# ============================================================================

@router.patch("/{po_id}/documents/{doc_id}", response_model=PODocumentResponse)
async def update_document(
    po_id: int,
    doc_id: int,
    request: PODocumentUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Update document metadata (type, notes)"""
    doc = db.query(PurchaseOrderDocument).filter(
        PurchaseOrderDocument.id == doc_id,
        PurchaseOrderDocument.purchase_order_id == po_id
    ).first()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    if request.document_type is not None:
        doc.document_type = request.document_type.value
    
    if request.notes is not None:
        doc.notes = request.notes
    
    doc.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(doc)
    
    logger.info(f"Updated document {doc_id} metadata")
    
    return _document_to_response(doc)


# ============================================================================
# Delete Document
# ============================================================================

@router.delete("/{po_id}/documents/{doc_id}")
async def delete_document(
    po_id: int,
    doc_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Delete a document
    
    Removes the database record and attempts to delete the file.
    Google Drive files are NOT deleted (manual cleanup required).
    """
    doc = db.query(PurchaseOrderDocument).filter(
        PurchaseOrderDocument.id == doc_id,
        PurchaseOrderDocument.purchase_order_id == po_id
    ).first()
    
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Try to delete local file
    if doc.storage_type == "local" and doc.file_path:
        try:
            if os.path.exists(doc.file_path):
                os.remove(doc.file_path)
                logger.info(f"Deleted local file: {doc.file_path}")
        except OSError as e:
            logger.warning(f"Could not delete local file {doc.file_path}: {e}")
    
    # Note: We don't delete Google Drive files automatically
    # They can be cleaned up manually or via a separate process
    
    db.delete(doc)
    db.commit()
    
    logger.info(f"Deleted document {doc_id} from PO {po_id}")
    
    return {"message": "Document deleted", "id": doc_id}


# ============================================================================
# Bulk Upload (for multiple files at once)
# ============================================================================

@router.post("/{po_id}/documents/bulk", response_model=List[PODocumentResponse], status_code=201)
async def bulk_upload_documents(
    po_id: int,
    files: List[UploadFile] = File(...),
    document_type: str = Form("other"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Upload multiple documents at once
    
    All files will be assigned the same document type.
    Use individual upload for different types per file.
    """
    # Verify PO exists
    po = db.query(PurchaseOrder).filter(PurchaseOrder.id == po_id).first()
    if not po:
        raise HTTPException(status_code=404, detail="Purchase order not found")
    
    if len(files) > 10:
        raise HTTPException(status_code=400, detail="Maximum 10 files per upload")
    
    results = []
    
    for file in files:
        # Reuse single upload logic
        try:
            # Reset file position for each read
            await file.seek(0)
            
            doc_response = await upload_document(
                po_id=po_id,
                file=file,
                document_type=document_type,
                notes=None,
                current_user=current_user,
                db=db,
            )
            results.append(doc_response)
        except HTTPException as e:
            logger.warning(f"Failed to upload {file.filename}: {e.detail}")
            # Continue with other files
            continue
    
    if not results:
        raise HTTPException(status_code=400, detail="No files were uploaded successfully")
    
    return results
