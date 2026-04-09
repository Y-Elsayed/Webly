import importlib
import os


def test_webly_public_api_exports():
    import webly

    assert webly.build_pipelines is not None
    assert webly.build_runtime is not None
    assert webly.PipelineConfig is not None
    assert webly.ProjectConfig is not None
    assert webly.ProjectRuntime is not None
    assert webly.QueryResult is not None
    assert webly.SourceRef is not None
    assert webly.IngestPipeline is not None
    assert webly.QueryPipeline is not None
    assert webly.FaissDatabase is not None


def test_main_import_is_cwd_independent(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    module = importlib.import_module("main")

    assert hasattr(module, "build_pipelines")
    assert hasattr(module, "build_runtime")
    assert os.getcwd() == str(tmp_path)
