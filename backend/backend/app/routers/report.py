from __future__ import annotations

from fastapi import APIRouter, Depends, File, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db_session
from app.core.security import get_current_user
from app.db.models.user import User
from app.schemas.report import (
    BusinessReportResponse,
    DeleteReportPdfsRequest,
    ReportPdfListResponse,
    ReportPdfUploadResponse,
    ReportResponse,
)
from app.services.report_service import ReportService

router = APIRouter(prefix="/api/v1/reports", tags=["reports"])
db_session_dependency = Depends(get_db_session)
current_user_dependency = Depends(get_current_user)
pdf_file_dependency = File(...)


@router.get("/by-evaluation/{evaluation_id}", response_model=ReportResponse)
async def get_report_by_evaluation(
    evaluation_id: int,
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> ReportResponse:
    """Return or generate a report for a completed evaluation."""

    return await ReportService(session).get_or_create_report(
        user=current_user,
        evaluation_id=evaluation_id,
    )


@router.get("/by-evaluation/{evaluation_id}/business", response_model=BusinessReportResponse)
async def get_business_report_by_evaluation(
    evaluation_id: int,
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> BusinessReportResponse:
    """Return or generate a business-shaped report for a completed evaluation."""

    return await ReportService(session).get_or_create_business_report(
        user=current_user,
        evaluation_id=evaluation_id,
    )


@router.post("/by-evaluation/{evaluation_id}/pdf", response_model=ReportPdfUploadResponse)
async def upload_report_pdf(
    evaluation_id: int,
    file: UploadFile = pdf_file_dependency,
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> ReportPdfUploadResponse:
    """Attach an exported PDF whitepaper to a report."""

    return await ReportService(session).save_report_pdf(
        user=current_user,
        evaluation_id=evaluation_id,
        pdf_bytes=await file.read(),
        original_filename=file.filename,
    )


@router.get("/pdfs", response_model=ReportPdfListResponse)
async def list_report_pdfs(
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> ReportPdfListResponse:
    """Return generated PDF reports for the current user."""

    return await ReportService(session).list_report_pdfs(user=current_user)


@router.post("/pdfs/delete", status_code=status.HTTP_204_NO_CONTENT)
async def delete_report_pdfs(
    payload: DeleteReportPdfsRequest,
    current_user: User = current_user_dependency,
    session: AsyncSession = db_session_dependency,
) -> None:
    """Soft-delete generated PDF reports for the current user."""

    await ReportService(session).delete_report_pdfs(
        user=current_user,
        payload=payload,
    )
