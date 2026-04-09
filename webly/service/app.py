from __future__ import annotations

from fastapi import FastAPI

from webly.service.dependencies import build_container
from webly.service.routes.chats import router as chats_router
from webly.service.routes.jobs import router as jobs_router
from webly.service.routes.projects import router as projects_router
from webly.service.routes.query import router as query_router


def create_app(*, storage_root: str | None = None) -> FastAPI:
    app = FastAPI(
        title="Webly Service",
        version="0.1.0",
        description="Filesystem-backed local API for Webly projects and query runtime.",
    )
    app.state.container = build_container(storage_root=storage_root)

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    app.include_router(projects_router)
    app.include_router(chats_router)
    app.include_router(jobs_router)
    app.include_router(query_router)
    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("webly.service.app:app", host="127.0.0.1", port=8000, reload=False)
