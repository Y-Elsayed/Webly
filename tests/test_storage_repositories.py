from webly.storage.chat_repository import FileChatRepository
from webly.storage.project_repository import FileProjectRepository


def test_project_repository_derives_runtime_paths(tmp_path):
    repo = FileProjectRepository(str(tmp_path))
    repo.create(
        "Docs",
        {
            "start_url": "https://example.com/docs",
            "allowed_domains": ["example.com"],
        },
    )

    cfg = repo.load("Docs")
    assert cfg.output_dir == str(tmp_path / "Docs")
    assert cfg.index_dir == str(tmp_path / "Docs" / "index")


def test_chat_repository_normalizes_legacy_payload(tmp_path):
    projects = FileProjectRepository(str(tmp_path))
    projects.create(
        "Docs",
        {
            "start_url": "https://example.com/docs",
        },
    )
    chats = FileChatRepository(projects)

    payload = chats.save("Docs", "Chat 1", [["Q", "A"]])
    assert payload["messages"] == [
        {"role": "user", "content": "Q"},
        {"role": "assistant", "content": "A"},
    ]
    assert payload["settings"]["memory_reset_at"] == 0
