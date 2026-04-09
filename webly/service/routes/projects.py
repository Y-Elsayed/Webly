from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

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
    config = project_service.create_project(request.name, request.config.model_dump())
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
    config = project_service.get_project(project)
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
    config = project_service.update_project(project, request.config.model_dump(exclude_none=True))
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
    project_service.delete_project(project)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/{project}/status",
    response_model=ProjectStatusResponse,
    responses={404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
def get_project_status(
    project: str,
    runtime_service: RuntimeService = Depends(get_runtime_service),
) -> ProjectStatusResponse:
    runtime_status = runtime_service.status(project)
    config = runtime_status["config"]
    paths = runtime_status["paths"]
    capabilities = runtime_status["capabilities"]

    return ProjectStatusResponse(
        name=project,
        config=config.to_dict(),
        paths=ProjectPathsResponse(**paths.as_dict()),
        results_ready=bool(runtime_status["results_ready"]),
        index_ready=bool(runtime_status["index_ready"]),
        query_ready=bool(runtime_status["query_ready"]),
        chat_ready=bool(runtime_status["chat_ready"]),
        capabilities=RuntimeCapabilitiesResponse(
            has_openai_api_key=bool(capabilities["has_openai_api_key"]),
            uses_openai_embeddings=bool(capabilities["uses_openai_embeddings"]),
            uses_summary_model=bool(capabilities["uses_summary_model"]),
            requires_openai_for_ingest=bool(capabilities["requires_openai_for_ingest"]),
            requires_openai_for_query=bool(capabilities["requires_openai_for_query"]),
            ingest_pipeline_available=bool(capabilities["ingest_pipeline_available"]),
            query_pipeline_available=bool(capabilities["query_pipeline_available"]),
            blockers=list(capabilities["blockers"]),
        ),
    )
