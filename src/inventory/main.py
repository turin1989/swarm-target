"""Application factory and entry point."""

import os
import uuid

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from inventory import __version__
from inventory.api import error_response as _error_response
from inventory.api import inventory_error_handler, router
from inventory.db import connect, init_db
from inventory.services.errors import InventoryError

DEFAULT_DB_PATH = "inventory.db"


def create_app(db_path: str | None = None) -> FastAPI:
    db_path = db_path or os.environ.get("INVENTORY_DB", DEFAULT_DB_PATH)
    init_db(db_path)
    app = FastAPI(title="Inventory", version=__version__)
    app.state.db_path = db_path
    app.include_router(router)
    app.add_exception_handler(InventoryError, inventory_error_handler)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return _error_response(exc.status_code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = exc.errors()
        parts = []
        for err in errors:
            loc = ".".join(str(piece) for piece in err.get("loc", ()))
            msg = err.get("msg", "invalid")
            parts.append(f"{loc}: {msg}" if loc else msg)
        message = "; ".join(parts) or "request validation failed"
        return _error_response(422, message)

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
        except Exception:
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
