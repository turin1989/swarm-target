"""Application factory and entry point."""

import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from inventory import __version__
from inventory.api import router
from inventory.db import init_db

DEFAULT_DB_PATH = "inventory.db"

ERROR_CODES = {
    400: "bad_request",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
}


def _error_response(status_code: int, message: str) -> JSONResponse:
    code = ERROR_CODES.get(status_code, "internal_error" if status_code >= 500 else "bad_request")
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
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
        return _error_response(exc.status_code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        messages = []
        for err in exc.errors():
            loc = ".".join(str(part) for part in err.get("loc", ()))
            msg = err.get("msg", "invalid input")
            messages.append(f"{loc}: {msg}" if loc else msg)
        return _error_response(422, "; ".join(messages) or "validation error")

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    return app


app = create_app()


def run() -> None:  # pragma: no cover
    import uvicorn

    uvicorn.run("inventory.main:app", host="0.0.0.0", port=8000, reload=False)


if __name__ == "__main__":  # pragma: no cover
    run()
