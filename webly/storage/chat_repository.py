from __future__ import annotations

import json
import os
from typing import Any

from webly.storage.project_repository import FileProjectRepository


class FileChatRepository:
    def __init__(self, projects: FileProjectRepository):
        self.projects = projects

    def list(self, project: str) -> list[str]:
        chats_dir = self.projects.get_paths(project).chats
        os.makedirs(chats_dir, exist_ok=True)
        return sorted([f[:-5] for f in os.listdir(chats_dir) if f.endswith(".json")])

    def load(self, project: str, chat_name: str) -> dict[str, Any]:
        chat_name = self.projects.sanitize_name(chat_name, "chat name")
        fp = os.path.join(self.projects.get_paths(project).chats, f"{chat_name}.json")
        if not os.path.exists(fp):
            return self.default_payload(chat_name)
        with open(fp, "r", encoding="utf-8-sig") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                return self.default_payload(chat_name)
        return self.normalize_payload(data, title=chat_name)

    def save(self, project: str, chat_name: str, payload: Any) -> dict[str, Any]:
        chat_name = self.projects.sanitize_name(chat_name, "chat name")
        fp = os.path.join(self.projects.get_paths(project).chats, f"{chat_name}.json")
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        normalized = self.normalize_payload(payload, title=chat_name)
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(normalized, f, indent=2)
        return normalized

    def delete(self, project: str, chat_name: str) -> None:
        chat_name = self.projects.sanitize_name(chat_name, "chat name")
        fp = os.path.join(self.projects.get_paths(project).chats, f"{chat_name}.json")
        if os.path.exists(fp):
            os.remove(fp)

    def rename(self, project: str, old: str, new: str) -> None:
        old = self.projects.sanitize_name(old, "chat name")
        new = self.projects.sanitize_name(new, "chat name")
        paths = self.projects.get_paths(project)
        old_fp = os.path.join(paths.chats, f"{old}.json")
        new_fp = os.path.join(paths.chats, f"{new}.json")
        if os.path.exists(old_fp):
            os.rename(old_fp, new_fp)

    @staticmethod
    def default_payload(title: str) -> dict[str, Any]:
        return {
            "title": title,
            "settings": {"score_threshold": 0.5, "memory_reset_at": 0},
            "messages": [],
        }

    @classmethod
    def normalize_payload(cls, payload: Any, *, title: str) -> dict[str, Any]:
        if isinstance(payload, list):
            messages = []
            for item in payload:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    messages.append({"role": "user", "content": item[0]})
                    messages.append({"role": "assistant", "content": item[1]})
            normalized = cls.default_payload(title)
            normalized["messages"] = messages
            return normalized

        if not isinstance(payload, dict):
            return cls.default_payload(title)

        normalized = dict(payload)
        normalized.setdefault("title", title)
        normalized.setdefault("settings", {})
        normalized.setdefault("messages", [])
        if not isinstance(normalized["settings"], dict):
            normalized["settings"] = {}
        normalized["settings"].setdefault("score_threshold", 0.5)
        normalized["settings"].setdefault("memory_reset_at", 0)
        if not isinstance(normalized["messages"], list):
            normalized["messages"] = []
        return normalized
