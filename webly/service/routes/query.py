from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from webly.query_result import QueryResult
from webly.service.dependencies import get_runtime_service
from webly.service.schemas import ErrorResponse, QueryRequest, QueryResponse, SourceRefResponse
from webly.service.services.runtime_service import RuntimeService

router = APIRouter(prefix="/v1/projects", tags=["query"])


def _query_response(result: QueryResult) -> QueryResponse:
    return QueryResponse(
        answer=result.answer,
        supported=result.supported,
        sources=[SourceRefResponse(**source.to_dict()) for source in result.sources],
        trace=result.trace,
    )


@router.post(
    "/{project}/query",
    response_model=QueryResponse,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
def query_project(
    project: str,
    request: QueryRequest,
    runtime_service: RuntimeService = Depends(get_runtime_service),
) -> QueryResponse:
    try:
        result = runtime_service.query_project(
            project,
            question=request.question,
            retry_on_empty=request.retry_on_empty,
            memory_context=request.memory_context,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    return _query_response(result)
