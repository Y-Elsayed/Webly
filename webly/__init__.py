"""Public package surface for the Webly framework."""

# ruff: noqa: E402

from pathlib import Path

# Allow `webly.<subpackage>` to resolve to the existing top-level project
# packages during the packaging transition without relying on cwd hacks.
_PACKAGE_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _PACKAGE_DIR.parent
if str(_PROJECT_ROOT) not in __path__:
    __path__.append(str(_PROJECT_ROOT))

from webly.pipeline.ingest_pipeline import IngestPipeline
from webly.pipeline.query_pipeline import QueryPipeline
from webly.vector_index.faiss_db import FaissDatabase

from .framework import PipelineConfig, build_pipelines

__all__ = [
    "PipelineConfig",
    "build_pipelines",
    "IngestPipeline",
    "QueryPipeline",
    "FaissDatabase",
]
