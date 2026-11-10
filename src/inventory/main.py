"""Application factory and entry point."""

import os
import uuid
from http import HTTPStatus

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from inventory import __version__
from inventory.api import inventory_error_to_http, router
from inventory.db import connect, init_db
from inventory.services.errors import InventoryError

DEFAULT_DB_PATH = "inventory.db"

_ERROR_CODES = {
    400: "bad_request",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
}


def _error_code(status_code: int) -> str:
    code = _ERROR_CODES.get(status_code)
    if code is not None:
        return code
    try:
        return HTTPStatus(status_code).phrase.lower().replace(" ", "_")
    except ValueError:
        return "error"


def _error_response(status_code: int, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": _error_code(status_code), "message": message}},
    )


def create_app(db_path: str | None = None) -> FastAPI:
    db_path = db_path or os.environ.get("INVENTORY_DB", DEFAULT_DB_PATH)
    init_db(db_path)
    app = FastAPI(title="Inventory", version=__version__)
    app.state.db_path = db_path
    app.include_router(router)

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        return _error_response(exc.status_code, message)

    @app.exception_handler(InventoryError)
    async def inventory_error_handler(
        request: Request, exc: InventoryError
    ) -> JSONResponse:
        # The mapping itself lives in inventory.api.inventory_error_to_http.
        return await http_exception_handler(request, inventory_error_to_http(exc))

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        parts = []
        for err in exc.errors():
            loc = ".".join(str(p) for p in err.get("loc", ()))
            msg = err.get("msg", "invalid")
            parts.append(f"{loc}: {msg}" if loc else msg)
        return _error_response(422, "; ".join(parts) or "validation error")

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
