"""Application factory and entry point."""

import os
import sqlite3
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from inventory import __version__
from inventory.api import error_body, inventory_error_handler, router
from inventory.db import connect, init_db
from inventory.services.errors import InventoryError

DEFAULT_DB_PATH = "inventory.db"


def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Convert HTTPException to the uniform error response shape."""
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(exc.status_code, str(exc.detail)),
    )


def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Convert request validation errors to the uniform error response shape."""
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", ()))
        msg = err.get("msg", "invalid")
        parts.append(f"{loc}: {msg}" if loc else msg)
    message = "; ".join(parts) or "validation error"
    return JSONResponse(status_code=422, content=error_body(422, message))


def create_app(db_path: str | None = None) -> FastAPI:
    db_path = db_path or os.environ.get("INVENTORY_DB", DEFAULT_DB_PATH)
    init_db(db_path)
    app = FastAPI(title="Inventory", version=__version__)
    app.state.db_path = db_path
    app.include_router(router)
    app.add_exception_handler(InventoryError, inventory_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.get("/health")
    def health() -> JSONResponse:
        try:
            conn = connect(app.state.db_path)
            try:
                conn.execute("SELECT 1")
            finally:
                conn.close()
        except sqlite3.Error:
            return JSONResponse(
                status_code=503,
                content={"status": "error", "version": __version__, "db": "error"},
            )
        return JSONResponse(
            content={"status": "ok", "version": __version__, "db": "ok"}
        )

    return app


app = create_app()


def run() -> None:  # pragma: no cover
    import uvicorn

    uvicorn.run("inventory.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":  # pragma: no cover
    run()
