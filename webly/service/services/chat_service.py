from __future__ import annotations

import os
from typing import Any

from webly.storage.chat_repository import FileChatRepository
from webly.storage.project_repository import FileProjectRepository


class ChatService:
    def __init__(self, projects: FileProjectRepository, chats: FileChatRepository):
        self.projects = projects
        self.chats = chats

    def _require_project(self, project: str) -> str:
        safe_name = self.projects.sanitize_name(project, "project name")
        if not os.path.exists(self.projects.get_paths(safe_name).config):
            raise FileNotFoundError(f"Project not found: {safe_name}")
        return safe_name

    def _chat_path(self, project: str, chat_name: str) -> str:
        safe_project = self._require_project(project)
        safe_chat = self.projects.sanitize_name(chat_name, "chat name")
        return os.path.join(self.projects.get_paths(safe_project).chats, f"{safe_chat}.json")

    def list_chats(self, project: str) -> list[str]:
        safe_project = self._require_project(project)
        return self.chats.list(safe_project)

    def get_chat(self, project: str, chat_name: str) -> dict[str, Any]:
        chat_path = self._chat_path(project, chat_name)
        if not os.path.exists(chat_path):
            safe_chat = self.projects.sanitize_name(chat_name, "chat name")
            raise FileNotFoundError(f"Chat not found: {safe_chat}")
        safe_project = self.projects.sanitize_name(project, "project name")
        return self.chats.load(safe_project, chat_name)

    def save_chat(self, project: str, chat_name: str, payload: Any) -> dict[str, Any]:
        safe_project = self._require_project(project)
        return self.chats.save(safe_project, chat_name, payload)

    def delete_chat(self, project: str, chat_name: str) -> None:
        chat_path = self._chat_path(project, chat_name)
        if not os.path.exists(chat_path):
            safe_chat = self.projects.sanitize_name(chat_name, "chat name")
            raise FileNotFoundError(f"Chat not found: {safe_chat}")
        safe_project = self.projects.sanitize_name(project, "project name")
        self.chats.delete(safe_project, chat_name)
