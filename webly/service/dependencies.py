from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from fastapi import Request

from webly.service.services.chat_service import ChatService
from webly.service.services.project_service import ProjectService
from webly.service.services.runtime_service import RuntimeService
from webly.storage.chat_repository import FileChatRepository
from webly.storage.project_repository import FileProjectRepository


def default_storage_root() -> str:
    env_root = os.getenv("WEBLY_STORAGE_ROOT")
    if env_root:
        return env_root
    repo_root = Path(__file__).resolve().parents[2]
    return str(repo_root / "websites_storage")


@dataclass(slots=True)
class ServiceContainer:
    storage_root: str
    projects: FileProjectRepository
    chats: FileChatRepository
    chat_service: ChatService
    project_service: ProjectService
    runtime_service: RuntimeService


def build_container(storage_root: str | None = None) -> ServiceContainer:
    root = storage_root or default_storage_root()
    projects = FileProjectRepository(root)
    chats = FileChatRepository(projects)
    chat_service = ChatService(projects, chats)
    project_service = ProjectService(projects)
    runtime_service = RuntimeService(projects)
    return ServiceContainer(
        storage_root=root,
        projects=projects,
        chats=chats,
        chat_service=chat_service,
        project_service=project_service,
        runtime_service=runtime_service,
    )


def get_container(request: Request) -> ServiceContainer:
    return request.app.state.container


def get_project_service(request: Request) -> ProjectService:
    return get_container(request).project_service


def get_runtime_service(request: Request) -> RuntimeService:
    return get_container(request).runtime_service


def get_chat_service(request: Request) -> ChatService:
    return get_container(request).chat_service
