"""Application factory and entry point."""

import os

import sqlite3

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from inventory import __version__
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
