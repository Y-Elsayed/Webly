from __future__ import annotations

from fastapi import APIRouter, Depends

from webly.service.dependencies import get_runtime_service
from webly.service.schemas import ErrorResponse, IngestRequest, IngestResponse
from webly.service.services.runtime_service import RuntimeService

router = APIRouter(prefix="/v1/projects", tags=["ingest"])


@router.post(
    "/{project}/ingest",
    response_model=IngestResponse,
    responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
def ingest_project(
    project: str,
    request: IngestRequest,
    runtime_service: RuntimeService = Depends(get_runtime_service),
) -> IngestResponse:
    result = runtime_service.run_ingest(
        project,
        mode=request.mode,
        force_crawl=request.force_crawl,
    )
    return IngestResponse(status="completed", result=result)
