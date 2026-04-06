"""Public package surface for the Webly framework."""

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
