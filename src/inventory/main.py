"""Application factory and entry point."""

import os
import sqlite3
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from inventory import __version__
from inventory.api import register_exception_handlers, router
from inventory.db import connect, init_db

DEFAULT_DB_PATH = "inventory.db"


def create_app(db_path: str | None = None) -> FastAPI:
    db_path = db_path or os.environ.get("INVENTORY_DB", DEFAULT_DB_PATH)
    init_db(db_path)
    app = FastAPI(title="Inventory", version=__version__)
    app.state.db_path = db_path
    app.include_router(router)
    register_exception_handlers(app)

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
                conn.execute("SELECT 1").fetchone()
            finally:
                conn.close()
        except sqlite3.Error:
            return JSONResponse(
                status_code=503,
                content={"status": "degraded", "version": __version__, "db": "error"},
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
