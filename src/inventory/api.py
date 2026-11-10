"""HTTP routes."""

import sqlite3
from typing import Annotated, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

from inventory.db import get_db
from inventory.models import (
    Item,
    ItemCreate,
    ItemPage,
    ItemStock,
    ItemUpdate,
    Location,
    LocationCreate,
    LowStockEntry,
    Movement,
    MovementCreate,
)
from inventory.services import items as items_service
from inventory.services import reports, search, stock
from inventory.services.errors import InventoryError

router = APIRouter()


_STATUS_TO_ERROR_CODE = {
    400: "bad_request",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
}


def error_body(status_code: int, message: str) -> dict:
    """Build the uniform error response body for a status code and message."""
    code = _STATUS_TO_ERROR_CODE.get(
        status_code, "internal_error" if status_code >= 500 else "bad_request"
    )
    return {"error": {"code": code, "message": message}}


def inventory_error_handler(request: Request, exc: InventoryError) -> JSONResponse:
    """Map any InventoryError to its HTTP response in one place."""
    return JSONResponse(
        status_code=exc.status_code, content=error_body(exc.status_code, str(exc))
    )


def _row_to_item(row: sqlite3.Row) -> Item:
    data = dict(row)
    data["active"] = bool(data["active"])
    return Item(**data)


def _fetch_item(conn: sqlite3.Connection, item_id: int) -> Item:
    item = items_service.get_item(conn, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"item {item_id} not found")
    return item


# --- items -------------------------------------------------------------------


@router.post("/items", response_model=Item, status_code=201)
def create_item(payload: ItemCreate, conn: sqlite3.Connection = Depends(get_db)) -> Item:
    return items_service.create_item(conn, payload)


@router.post("/items/bulk", response_model=list[Item], status_code=201)
def create_items_bulk(
    payload: Annotated[list[ItemCreate], Body(min_length=1)],
    conn: sqlite3.Connection = Depends(get_db),
) -> list[Item]:
    """Create several items atomically: all succeed or none are created."""
    created_ids: list[int] = []
    for entry in payload:
        try:
            cur = conn.execute(
                """
                INSERT INTO items (sku, name, description, unit_price, reorder_level)
                VALUES (?, ?, ?, ?, ?)
                """,
                (entry.sku, entry.name, entry.description, entry.unit_price, entry.reorder_level),
            )
        except sqlite3.IntegrityError:
            conn.rollback()
            raise HTTPException(status_code=409, detail=f"sku {entry.sku!r} already exists")
        created_ids.append(cur.lastrowid)
    return [_fetch_item(conn, item_id) for item_id in created_ids]


_SORTABLE_ITEM_COLUMNS = {"id", "name", "sku"}


@router.get("/items", response_model=ItemPage)
def list_items(
    response: Response,
    active: Optional[bool] = None,
    sku: Optional[str] = None,
    sort: str = Query("id", pattern=r"^-?(id|name|sku)$"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_db),
) -> ItemPage:
    conditions: list[str] = []
    where_params: list = []
    if active is not None:
        conditions.append("active = ?")
        where_params.append(int(active))
    if sku is not None:
        conditions.append("sku = ?")
        where_params.append(sku)
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    direction = "ASC"
    if sort.startswith("-"):
        direction = "DESC"
        sort = sort[1:]
    if sort not in _SORTABLE_ITEM_COLUMNS:  # defence in depth; pattern already enforces
        raise HTTPException(status_code=422, detail=f"invalid sort field {sort!r}")
    total = conn.execute(f"SELECT COUNT(*) FROM items{where}", where_params).fetchone()[0]
    response.headers["X-Total-Count"] = str(total)
    rows = conn.execute(
        f"SELECT * FROM items{where} ORDER BY {sort} {direction} LIMIT ? OFFSET ?",
        [*where_params, limit, offset],
    ).fetchall()
    return ItemPage(
        items=[_row_to_item(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


# Registered before `/items/{item_id}` so the literal `by-sku` segment is not
# swallowed by the item-id path parameter.
@router.get("/items/by-sku/{sku}", response_model=Item)
def get_item_by_sku(sku: str, conn: sqlite3.Connection = Depends(get_db)) -> Item:
    item = items_service.get_item_by_sku(conn, sku)
    if item is None:
        raise HTTPException(status_code=404, detail=f"sku {sku} not found")
    return item


@router.get("/items/{item_id}", response_model=Item)
def get_item(item_id: int, conn: sqlite3.Connection = Depends(get_db)) -> Item:
    return _fetch_item(conn, item_id)


@router.put("/items/{item_id}", response_model=Item)
def update_item(
    item_id: int, payload: ItemUpdate, conn: sqlite3.Connection = Depends(get_db)
) -> Item:
    item = items_service.update_item(conn, item_id, payload)
    if item is None:
        raise HTTPException(status_code=404, detail=f"item {item_id} not found")
    return item


@router.delete("/items/{item_id}", status_code=204)
def delete_item(item_id: int, conn: sqlite3.Connection = Depends(get_db)) -> Response:
    _fetch_item(conn, item_id)
    remaining = stock.total_stock(conn, item_id)
    if remaining > 0:
        raise HTTPException(
            status_code=409,
            detail=f"item {item_id} still has {remaining} units in stock and cannot be deleted",
        )
    items_service.delete_item(conn, item_id)
    return Response(status_code=204)


@router.get("/items/{item_id}/stock", response_model=ItemStock)
def item_stock(item_id: int, conn: sqlite3.Connection = Depends(get_db)) -> ItemStock:
    _fetch_item(conn, item_id)
    return ItemStock(
        item_id=item_id,
        total=stock.total_stock(conn, item_id),
        levels=stock.get_item_levels(conn, item_id),
    )


# --- locations ---------------------------------------------------------------


@router.post("/locations", response_model=Location, status_code=201)
def create_location(
    payload: LocationCreate, conn: sqlite3.Connection = Depends(get_db)
) -> Location:
    cur = conn.execute(
        "INSERT INTO locations (code, name) VALUES (?, ?)", (payload.code, payload.name)
    )
    row = conn.execute("SELECT * FROM locations WHERE id = ?", (cur.lastrowid,)).fetchone()
    return Location(**dict(row))


@router.get("/locations", response_model=list[Location])
def list_locations(conn: sqlite3.Connection = Depends(get_db)) -> list[Location]:
    rows = conn.execute("SELECT * FROM locations ORDER BY id").fetchall()
    return [Location(**dict(r)) for r in rows]


@router.get("/locations/{location_id}", response_model=Location)
def get_location(location_id: int, conn: sqlite3.Connection = Depends(get_db)) -> Location:
    row = conn.execute("SELECT * FROM locations WHERE id = ?", (location_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"location {location_id} not found")
    return Location(**dict(row))


@router.delete("/locations/{location_id}", status_code=204)
def delete_location(
    location_id: int, conn: sqlite3.Connection = Depends(get_db)
) -> Response:
    row = conn.execute("SELECT * FROM locations WHERE id = ?", (location_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"location {location_id} not found")
    holds_stock = conn.execute(
        "SELECT 1 FROM stock_levels WHERE location_id = ? AND qty != 0 LIMIT 1",
        (location_id,),
    ).fetchone()
    if holds_stock is not None:
        raise HTTPException(
            status_code=409,
            detail=f"location {location_id} still holds stock and cannot be deleted",
        )
    # Movement history references locations without ON DELETE; detach it so the
    # location row can be removed while keeping the movement log intact.
    conn.execute(
        "UPDATE movements SET from_location_id = NULL WHERE from_location_id = ?",
        (location_id,),
    )
    conn.execute(
        "UPDATE movements SET to_location_id = NULL WHERE to_location_id = ?",
        (location_id,),
    )
    conn.execute("DELETE FROM locations WHERE id = ?", (location_id,))
    return Response(status_code=204)


# --- movements ---------------------------------------------------------------


@router.post("/movements", response_model=Movement, status_code=201)
def create_movement(
    payload: MovementCreate, conn: sqlite3.Connection = Depends(get_db)
) -> Movement:
    return stock.apply_movement(conn, payload)


@router.get("/movements", response_model=list[Movement])
def list_movements(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_db),
) -> list[Movement]:
    return stock.list_movements(conn, limit=limit, offset=offset)


# --- reports & search --------------------------------------------------------


@router.get("/reports/low-stock", response_model=list[LowStockEntry])
def low_stock_report(conn: sqlite3.Connection = Depends(get_db)) -> list[LowStockEntry]:
    return reports.low_stock(conn)


@router.get("/reports/value")
def inventory_value_report(
    location_id: Optional[int] = None,
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    if location_id is not None:
        row = conn.execute(
            "SELECT 1 FROM locations WHERE id = ?", (location_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(
                status_code=404, detail=f"location {location_id} not found"
            )
    return {"value": reports.inventory_value(conn, location_id=location_id)}


@router.get("/search", response_model=list[Item])
def search_items(
    q: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=500),
    conn: sqlite3.Connection = Depends(get_db),
) -> list[Item]:
    return search.search_items(conn, q, limit=limit)
