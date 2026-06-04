import uuid
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends
from loguru import logger
from app.core.config import settings
from app.core.security import get_current_user
from app.models.schemas import (
    AnalysisResult, DocumentHistoryResponse,
    DocumentHistoryItem, UsageResponse, SupportedLanguage,
)
from app.services.pdf_service import PDFService, PDFExtractionError
from app.services.classifier_service import ClassifierService
from app.services.explanation_service import ExplanationService


router = APIRouter(prefix="/documents", tags=["Documents"])
_documents_db: dict = {}
_user_documents: dict = {}


def _check_usage(user_id: str) -> int:
    return len(_user_documents.get(user_id, []))


def _add_doc(user_id: str, doc_id: str):
    _user_documents.setdefault(user_id, []).append(doc_id)


from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Depends, Header
from typing import Optional

@router.post("/analyse", response_model=AnalysisResult)
async def analyse_document(
    file: UploadFile = File(...),
    language: SupportedLanguage = Form(SupportedLanguage.ENGLISH),
    authorization: Optional[str] = Header(None),
):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    user_id = "supabase_user"

    if _check_usage(user_id) >= settings.free_tier_docs_per_month:
        raise HTTPException(
            status_code=402,
            detail="Free tier limit reached. Upgrade to premium for unlimited analyses.",
        )

    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided.")

    ext = file.filename.rsplit(".", 1)[-1].lower()
    if ext not in settings.allowed_file_types:
        raise HTTPException(status_code=415, detail=f"File type .{ext} not supported.")

    file_bytes = await file.read()
    if len(file_bytes) > settings.max_file_size_bytes:
        raise HTTPException(status_code=413, detail="File too large.")
    if len(file_bytes) < 100:
        raise HTTPException(status_code=400, detail="File appears empty.")

    try:
        extracted_text, method = await PDFService.extract_text(file_bytes, file.filename)
    except PDFExtractionError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if len(extracted_text.strip()) < 50:
        raise HTTPException(status_code=422, detail="Could not extract readable text.")

    doc_type, confidence = ClassifierService.classify(extracted_text)
    document_id = str(uuid.uuid4())

    result = await ExplanationService.explain(
        text=extracted_text,
        doc_type=doc_type,
        language=language,
        document_id=document_id,
        document_name=file.filename,
    )

    _documents_db[document_id] = result
    _add_doc(user_id, document_id)
    logger.info(f"Analysis done: {document_id} | {doc_type} | AI:{result.ai_powered}")

    try:
            from supabase import create_client
            sb = create_client(settings.supabase_url, settings.supabase_service_key)
            sb.table("documents").insert({
                "id": document_id,
                "user_id": user_id,
                "document_name": file.filename,
                "document_type": result.document_type,
                "language": result.language,
                "summary": result.summary,
                "obligations": result.obligations,
                "key_dates": result.key_dates,
                "red_flags": result.red_flags,
                "next_steps": result.next_steps,
                "ai_powered": result.ai_powered,
            }).execute()
            logger.info(f"Saved to Supabase: {document_id}")
    except Exception as e:
            logger.warning(f"Supabase save failed: {e}")

     
    try:
            from supabase import create_client
            sb = create_client(settings.supabase_url, settings.supabase_service_key)
            sb.table("documents").insert({...}).execute()
            logger.info(f"Saved to Supabase: {document_id}")
    except Exception as e:
            logger.warning(f"Supabase save failed: {e}")
    try:
            sb2 = create_client(settings.supabase_url, settings.supabase_service_key)
            storage_path = f"{user_id}/{document_id}/{file.filename}"
            sb2.storage.from_("documents").upload(
                path=storage_path,
                file=file_bytes,
                file_options={"content-type": file.content_type or "application/pdf"}
            )
            logger.info(f"PDF saved to storage: {storage_path}")
    except Exception as e:
            logger.warning(f"Storage save failed: {e}")

    return result  # ← MUST BE LAST       

    return result


@router.get("/usage/summary", response_model=UsageResponse)
async def get_usage(current_user: dict = Depends(get_current_user)):
    from calendar import month_name
    now = datetime.utcnow()
    nm = now.month % 12 + 1
    ny = now.year + (1 if now.month == 12 else 0)
    return UsageResponse(
        plan="free",
        docs_used=_check_usage(current_user["sub"]),
        docs_limit=settings.free_tier_docs_per_month,
        resets_on=f"{month_name[nm]} 1, {ny}",
    )


@router.get("/history", response_model=DocumentHistoryResponse)
async def get_history(limit: int = 10, current_user: dict = Depends(get_current_user)):
    ids = _user_documents.get(current_user["sub"], [])
    items = []
    for doc_id in reversed(ids[-limit:]):
        r = _documents_db.get(doc_id)
        if r:
            items.append(DocumentHistoryItem(
                document_id=r.document_id,
                document_name=r.document_name,
                document_type=r.document_type,
                language=r.language,
                processed_at=r.processed_at,
            ))
    return DocumentHistoryResponse(items=items, total=len(ids))


@router.get("/{document_id}", response_model=AnalysisResult)
async def get_document(document_id: str, current_user: dict = Depends(get_current_user)):
    result = _documents_db.get(document_id)
    if not result:
        raise HTTPException(status_code=404, detail="Document not found.")
    if document_id not in _user_documents.get(current_user["sub"], []):
        raise HTTPException(status_code=403, detail="Access denied.")
    return result

