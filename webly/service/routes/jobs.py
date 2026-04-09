from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

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
    try:
        result = runtime_service.run_ingest(
            project,
            mode=request.mode,
            force_crawl=request.force_crawl,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    return IngestResponse(status="completed", result=result)
