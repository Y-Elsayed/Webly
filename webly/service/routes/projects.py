from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status

from webly.service.dependencies import get_project_service, get_runtime_service
from webly.service.schemas import (
    ErrorResponse,
    ProjectCreateRequest,
    ProjectListResponse,
    ProjectPathsResponse,
    ProjectResponse,
    ProjectStatusResponse,
    RuntimeCapabilitiesResponse,
    ProjectUpdateRequest,
)
from webly.service.services.project_service import ProjectService
from webly.service.services.runtime_service import RuntimeService

router = APIRouter(prefix="/v1/projects", tags=["projects"])


def _project_response(name: str, config, paths) -> ProjectResponse:
    return ProjectResponse(
        name=name,
        config=config.to_dict(),
        paths=ProjectPathsResponse(**paths.as_dict()),
    )


@router.get("", response_model=ProjectListResponse)
def list_projects(project_service: ProjectService = Depends(get_project_service)) -> ProjectListResponse:
    return ProjectListResponse(items=project_service.list_projects())


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"model": ErrorResponse}},
)
def create_project(
    request: ProjectCreateRequest,
    project_service: ProjectService = Depends(get_project_service),
) -> ProjectResponse:
    try:
        config = project_service.create_project(request.name, request.config.model_dump())
    except FileExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    paths = project_service.projects.get_paths(request.name)
    return _project_response(request.name, config, paths)


@router.get(
    "/{project}",
    response_model=ProjectResponse,
    responses={404: {"model": ErrorResponse}},
)
def get_project(
    project: str,
    project_service: ProjectService = Depends(get_project_service),
) -> ProjectResponse:
    try:
        config = project_service.get_project(project)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    paths = project_service.projects.get_paths(project)
    return _project_response(project, config, paths)


@router.patch(
    "/{project}",
    response_model=ProjectResponse,
    responses={404: {"model": ErrorResponse}},
)
def update_project(
    project: str,
    request: ProjectUpdateRequest,
    project_service: ProjectService = Depends(get_project_service),
) -> ProjectResponse:
    try:
        config = project_service.update_project(project, request.config.model_dump(exclude_none=True))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    paths = project_service.projects.get_paths(project)
    return _project_response(project, config, paths)


@router.delete(
    "/{project}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses={404: {"model": ErrorResponse}},
)
def delete_project(
    project: str,
    project_service: ProjectService = Depends(get_project_service),
) -> Response:
    try:
        project_service.delete_project(project)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{project}/status",
    response_model=ProjectStatusResponse,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
def get_project_status(
    project: str,
    project_service: ProjectService = Depends(get_project_service),
    runtime_service: RuntimeService = Depends(get_runtime_service),
) -> ProjectStatusResponse:
    try:
        config = project_service.get_project(project)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    paths = project_service.projects.get_paths(project)
    results_ready = project_service.results_ready(project)
    index_ready = project_service.index_ready(project)
    uses_openai_embeddings = config.embedding_model.startswith("openai:")
    uses_summary_model = bool(config.summary_model)
    has_openai_api_key = False
    query_pipeline_available = False
    try:
        runtime_status = runtime_service.status(project)
        has_openai_api_key = bool(runtime_status["capabilities"]["has_openai_api_key"])
        query_pipeline_available = bool(runtime_status["capabilities"]["query_pipeline_available"])
        index_ready = bool(runtime_status["index_ready"])
        results_ready = bool(runtime_status["results_ready"])
        query_ready = bool(runtime_status["query_ready"])
        chat_ready = bool(runtime_status["chat_ready"])
    except RuntimeError:
        query_ready = False
        chat_ready = False
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    return ProjectStatusResponse(
        name=project,
        config=config.to_dict(),
        paths=ProjectPathsResponse(**paths.as_dict()),
        results_ready=results_ready,
        index_ready=index_ready,
        query_ready=query_ready,
        chat_ready=chat_ready,
        capabilities=RuntimeCapabilitiesResponse(
            has_openai_api_key=has_openai_api_key,
            uses_openai_embeddings=uses_openai_embeddings,
            uses_summary_model=uses_summary_model,
            query_pipeline_available=query_pipeline_available,
        ),
    )
