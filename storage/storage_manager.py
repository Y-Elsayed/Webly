import json
import os
import shutil


class StorageManager:
    def __init__(self, root_dir: str):
        self.root = root_dir
        os.makedirs(self.root, exist_ok=True)

    def get_paths(self, project: str):
        root = os.path.join(self.root, project)
        return {
            "root": root,
            "config": os.path.join(root, "config.json"),
            "index": os.path.join(root, "index"),
            "chats": os.path.join(root, "chats"),
        }

    def list_projects(self):
        return [d for d in os.listdir(self.root) if os.path.isdir(os.path.join(self.root, d))]

    def create_project(self, name: str, cfg: dict):
        p = self.get_paths(name)
        os.makedirs(p["root"], exist_ok=True)
        os.makedirs(p["index"], exist_ok=True)
        os.makedirs(p["chats"], exist_ok=True)
        with open(p["config"], "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)

    def get_config(self, project: str) -> dict:
        p = self.get_paths(project)
        # utf-8-sig tolerates BOM and plain UTF-8.
        with open(p["config"], "r", encoding="utf-8-sig") as f:
            return json.load(f)

    def save_config(self, project: str, cfg: dict):
        p = self.get_paths(project)
        with open(p["config"], "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)

    def delete_project(self, project: str):
        shutil.rmtree(os.path.join(self.root, project), ignore_errors=True)

    # ---------- Chat Management ----------
    def list_chats(self, project: str):
        p = self.get_paths(project)
        os.makedirs(p["chats"], exist_ok=True)
        return sorted([f[:-5] for f in os.listdir(p["chats"]) if f.endswith(".json")])

    def load_chat(self, project: str, chat_name: str):
        fp = os.path.join(self.get_paths(project)["chats"], f"{chat_name}.json")
        if not os.path.exists(fp):
            return {"title": chat_name, "settings": {"score_threshold": 0.5}, "messages": []}
        with open(fp, "r", encoding="utf-8-sig") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                return {"title": chat_name, "settings": {"score_threshold": 0.5}, "messages": []}
        # backward compatibility if file is list
        if isinstance(data, list):
            # old format: [[q, a], [q, a], ...]
            messages = []
            for item in data:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    messages.append({"role": "user", "content": item[0]})
                    messages.append({"role": "assistant", "content": item[1]})
            return {"title": chat_name, "settings": {"score_threshold": 0.5}, "messages": messages}
        # else dict in new shape
        data.setdefault("title", chat_name)
        data.setdefault("settings", {"score_threshold": 0.5})
        data.setdefault("messages", [])
        data["settings"].setdefault("score_threshold", 0.5)
        return data

    def save_chat(self, project: str, chat_name: str, payload: dict):
        fp = os.path.join(self.get_paths(project)["chats"], f"{chat_name}.json")
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)

    def delete_chat(self, project: str, chat_name: str):
        fp = os.path.join(self.get_paths(project)["chats"], f"{chat_name}.json")
        if os.path.exists(fp):
            os.remove(fp)

    def rename_chat(self, project: str, old: str, new: str):
        p = self.get_paths(project)
        old_fp = os.path.join(p["chats"], f"{old}.json")
        new_fp = os.path.join(p["chats"], f"{new}.json")
        if os.path.exists(old_fp):
            os.rename(old_fp, new_fp)
