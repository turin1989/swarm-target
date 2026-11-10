"""Application factory and entry point."""

import os
import uuid

from fastapi import FastAPI

from inventory import __version__
from inventory.api import inventory_error_handler, router
from inventory.db import init_db
from inventory.services.errors import InventoryError

DEFAULT_DB_PATH = "inventory.db"

REQUEST_ID_HEADER = "x-request-id"


class RequestIDMiddleware:
    """Echo the incoming X-Request-ID header or generate a new uuid4.

    Implemented as pure ASGI middleware so the header is attached to every
    response, including error responses.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = None
        for name, value in scope.get("headers", []):
            if name == REQUEST_ID_HEADER.encode("latin-1"):
                request_id = value.decode("latin-1")
                break
        if not request_id:
            request_id = str(uuid.uuid4())

        async def send_with_request_id(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers = [
                    (name, value)
                    for name, value in headers
                    if name.lower() != REQUEST_ID_HEADER.encode("latin-1")
                ]
                headers.append(
                    (REQUEST_ID_HEADER.encode("latin-1"), request_id.encode("latin-1"))
                )
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_request_id)


def create_app(db_path: str | None = None) -> FastAPI:
    db_path = db_path or os.environ.get("INVENTORY_DB", DEFAULT_DB_PATH)
    init_db(db_path)
    app = FastAPI(title="Inventory", version=__version__)
    app.state.db_path = db_path
    app.add_middleware(RequestIDMiddleware)
    app.add_exception_handler(InventoryError, inventory_error_handler)
    app.include_router(router)

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
