from webly.storage.chat_repository import FileChatRepository
from webly.storage.project_repository import FileProjectRepository


class StorageManager:
    def __init__(self, root_dir: str):
        self.root = root_dir
        self.projects = FileProjectRepository(root_dir)
        self.chats = FileChatRepository(self.projects)

    @staticmethod
    def _sanitize_name(name: str, label: str = "name") -> str:
        """Compatibility wrapper around the project repository sanitizer."""
        return FileProjectRepository.sanitize_name(name, label)

    def get_paths(self, project: str):
        return self.projects.get_paths(project).as_dict()

    def list_projects(self):
        return self.projects.list()

    def create_project(self, name: str, cfg: dict):
        self.projects.create(name, cfg)

    def get_config(self, project: str) -> dict:
        return self.projects.load_dict(project)

    def save_config(self, project: str, cfg: dict):
        self.projects.save(project, cfg)

    def delete_project(self, project: str):
        self.projects.delete(project)

    # ---------- Chat Management ----------
    def list_chats(self, project: str):
        return self.chats.list(project)

    def load_chat(self, project: str, chat_name: str):
        return self.chats.load(project, chat_name)

    def save_chat(self, project: str, chat_name: str, payload: dict):
        self.chats.save(project, chat_name, payload)

    def delete_chat(self, project: str, chat_name: str):
        self.chats.delete(project, chat_name)

    def rename_chat(self, project: str, old: str, new: str):
        self.chats.rename(project, old, new)
