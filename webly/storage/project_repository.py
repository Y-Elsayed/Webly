from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from typing import Any, Mapping

from webly.project_config import ProjectConfig


@dataclass(frozen=True, slots=True)
class ProjectPaths:
    root: str
    config: str
    index: str
    chats: str

    def as_dict(self) -> dict[str, str]:
        return {
            "root": self.root,
            "config": self.config,
            "index": self.index,
            "chats": self.chats,
        }


class FileProjectRepository:
    def __init__(self, root_dir: str):
        self.root = root_dir
        os.makedirs(self.root, exist_ok=True)

    @staticmethod
    def sanitize_name(name: str, label: str = "name") -> str:
        clean = os.path.basename(name.replace("\\", "/"))
        if not clean or clean.startswith("."):
            raise ValueError(f"Invalid {label}: {name!r}")
        return clean

    def get_paths(self, project: str) -> ProjectPaths:
        project = self.sanitize_name(project, "project name")
        root = os.path.join(self.root, project)
        return ProjectPaths(
            root=root,
            config=os.path.join(root, "config.json"),
            index=os.path.join(root, "index"),
            chats=os.path.join(root, "chats"),
        )

    def list(self) -> list[str]:
        return [d for d in os.listdir(self.root) if os.path.isdir(os.path.join(self.root, d))]

    def create(self, name: str, cfg: Mapping[str, Any]) -> ProjectConfig:
        paths = self.get_paths(name)
        os.makedirs(paths.root, exist_ok=True)
        os.makedirs(paths.index, exist_ok=True)
        os.makedirs(paths.chats, exist_ok=True)
        config = ProjectConfig.from_dict(cfg, output_dir=paths.root, index_dir=paths.index)
        self._write_config(paths.config, config)
        return config

    def load(self, project: str) -> ProjectConfig:
        paths = self.get_paths(project)
        with open(paths.config, "r", encoding="utf-8-sig") as f:
            raw = json.load(f)
        return ProjectConfig.from_dict(raw, output_dir=paths.root, index_dir=paths.index)

    def load_dict(self, project: str) -> dict[str, Any]:
        return self.load(project).to_dict()

    def save(self, project: str, cfg: Mapping[str, Any] | ProjectConfig) -> ProjectConfig:
        paths = self.get_paths(project)
        config = cfg if isinstance(cfg, ProjectConfig) else ProjectConfig.from_dict(cfg, output_dir=paths.root, index_dir=paths.index)
        os.makedirs(paths.root, exist_ok=True)
        os.makedirs(paths.index, exist_ok=True)
        os.makedirs(paths.chats, exist_ok=True)
        self._write_config(paths.config, config)
        return config

    def delete(self, project: str) -> None:
        shutil.rmtree(self.get_paths(project).root, ignore_errors=True)

    def _write_config(self, path: str, config: ProjectConfig) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(config.to_storage_dict(), f, indent=2)
