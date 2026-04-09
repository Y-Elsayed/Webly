from __future__ import annotations

import os
from typing import Any, Mapping

from webly.project_config import ProjectConfig
from webly.service.errors import ConflictError, NotFoundError
from webly.storage.project_repository import FileProjectRepository


class ProjectService:
    def __init__(self, projects: FileProjectRepository):
        self.projects = projects

    def list_projects(self) -> list[str]:
        return sorted(self.projects.list())

    def exists(self, name: str) -> bool:
        return os.path.exists(self.projects.get_paths(name).config)

    def create_project(self, name: str, cfg: Mapping[str, Any]) -> ProjectConfig:
        safe_name = self.projects.sanitize_name(name, "project name")
        if self.exists(safe_name):
            raise ConflictError(f"Project already exists: {safe_name}")
        return self.projects.create(safe_name, cfg)

    def get_project(self, name: str) -> ProjectConfig:
        safe_name = self.projects.sanitize_name(name, "project name")
        if not self.exists(safe_name):
            raise NotFoundError(f"Project not found: {safe_name}")
        return self.projects.load(safe_name)

    def update_project(self, name: str, patch: Mapping[str, Any]) -> ProjectConfig:
        safe_name = self.projects.sanitize_name(name, "project name")
        current = self.get_project(safe_name)
        merged = current.to_storage_dict()
        for key, value in patch.items():
            if value is not None:
                merged[key] = value
        return self.projects.save(safe_name, merged)

    def delete_project(self, name: str) -> None:
        safe_name = self.projects.sanitize_name(name, "project name")
        if not self.exists(safe_name):
            raise NotFoundError(f"Project not found: {safe_name}")
        self.projects.delete(safe_name)

    def results_ready(self, name: str) -> bool:
        config = self.get_project(name)
        path = os.path.join(config.output_dir, config.results_file)
        return os.path.exists(path) and os.path.getsize(path) > 0

    def index_ready(self, name: str) -> bool:
        config = self.get_project(name)
        if not config.index_dir or not os.path.isdir(config.index_dir):
            return False
        try:
            files = os.listdir(config.index_dir)
        except Exception:
            return False
        has_index = any(file_name.lower().endswith(".index") for file_name in files)
        has_meta = any(file_name.lower().startswith("metadata") for file_name in files)
        return has_index and has_meta
