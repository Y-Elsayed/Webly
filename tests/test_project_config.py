from webly.project_config import ProjectConfig


def test_project_config_applies_runtime_defaults():
    cfg = ProjectConfig.from_dict(
        {
            "start_url": "https://example.com",
            "output_dir": "/tmp/out",
            "index_dir": "/tmp/out/index",
            "embedding_model": "default",
            "chat_model": "",
        }
    )

    assert cfg.embedding_model == "openai:text-embedding-3-small"
    assert cfg.chat_model == "gpt-4o-mini"
    assert cfg.results_file == "results.jsonl"


def test_project_config_storage_dict_omits_derived_paths():
    cfg = ProjectConfig.from_dict(
        {
            "start_url": "https://example.com",
            "output_dir": "/tmp/out",
            "index_dir": "/tmp/out/index",
        }
    )

    data = cfg.to_storage_dict()
    assert "output_dir" not in data
    assert "index_dir" not in data
