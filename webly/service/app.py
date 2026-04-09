from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from webly.service.dependencies import build_container
from webly.service.errors import ServiceError
from webly.service.routes.chats import router as chats_router
from webly.service.routes.jobs import router as jobs_router
from webly.service.routes.projects import router as projects_router
from webly.service.routes.query import router as query_router
from webly.service.schemas import ErrorResponse


def create_app(*, storage_root: str | None = None) -> FastAPI:
    app = FastAPI(
        title="Webly Service",
        version="0.1.0",
        description="Filesystem-backed local API for Webly projects and query runtime.",
    )
    app.state.container = build_container(storage_root=storage_root)

    @app.exception_handler(ServiceError)
    def handle_service_error(_request: Request, exc: ServiceError):
        payload = ErrorResponse(detail=exc.detail).model_dump()
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(FileNotFoundError)
    def handle_not_found(_request: Request, exc: FileNotFoundError):
        payload = ErrorResponse(detail=str(exc)).model_dump()
        return JSONResponse(status_code=404, content=payload)

    @app.exception_handler(FileExistsError)
    def handle_conflict(_request: Request, exc: FileExistsError):
        payload = ErrorResponse(detail=str(exc)).model_dump()
        return JSONResponse(status_code=409, content=payload)

    @app.exception_handler(ValueError)
    def handle_bad_request(_request: Request, exc: ValueError):
        payload = ErrorResponse(detail=str(exc)).model_dump()
        return JSONResponse(status_code=400, content=payload)

    @app.exception_handler(RuntimeError)
    def handle_runtime_unavailable(_request: Request, exc: RuntimeError):
        payload = ErrorResponse(detail=str(exc)).model_dump()
        return JSONResponse(status_code=503, content=payload)

    @app.exception_handler(ImportError)
    def handle_import_error(_request: Request, exc: ImportError):
        payload = ErrorResponse(detail=str(exc)).model_dump()
        return JSONResponse(status_code=503, content=payload)

    @app.exception_handler(RequestValidationError)
    def handle_validation_error(_request: Request, exc: RequestValidationError):
        messages = []
        for error in exc.errors():
            location = " -> ".join(str(part) for part in error.get("loc", ()))
            message = error.get("msg", "Invalid request.")
            messages.append(f"{location}: {message}" if location else message)
        detail = "; ".join(messages) or "Invalid request."
        payload = ErrorResponse(detail=detail).model_dump()
        return JSONResponse(status_code=400, content=payload)

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
