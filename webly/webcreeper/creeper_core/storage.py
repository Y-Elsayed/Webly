import json
import os


def save_jsonl_line(path: str, data: dict):
    """
    Saves a single dictionary as a JSON line to a file.
    Creates the file and directory if needed.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False) + "\n")


def save_json(path: str, data: dict | list):
    """
    Saves a dictionary or list as a formatted JSON file.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)
