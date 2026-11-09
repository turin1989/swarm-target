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
    LocationStock,
    LocationUpdate,
    LowStockEntry,
    Movement,
    MovementCreate,
)
from inventory.services import items as items_service
from inventory.services import reports, search, stock
from inventory.services.errors import InventoryError

router = APIRouter()

ERROR_CODES = {
    400: "bad_request",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
}


def error_response(status_code: int, message: str) -> JSONResponse:
    """Build the uniform error body: {"error": {"code": ..., "message": ...}}."""
    code = ERROR_CODES.get(status_code, "error")
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message}},
    )


def inventory_error_handler(request: Request, exc: InventoryError) -> JSONResponse:
    """Translate service-layer errors into HTTP responses in one place."""
    return error_response(exc.status_code, str(exc))


def _fetch_item(conn: sqlite3.Connection, item_id: int) -> Item:
    item = items_service.get_item(conn, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"item {item_id} not found")
    return item


# --- items -------------------------------------------------------------------


@router.post("/items", response_model=Item, status_code=201)
def create_item(payload: ItemCreate, conn: sqlite3.Connection = Depends(get_db)) -> Item:
    try:
        return items_service.create_item(conn, payload)
    except sqlite3.IntegrityError as exc:
        if "barcode" in str(exc):
            raise HTTPException(
                status_code=409, detail=f"barcode {payload.barcode!r} already exists"
            )
        raise HTTPException(status_code=409, detail=f"sku {payload.sku!r} already exists")


@router.post("/items/bulk", response_model=list[Item], status_code=201)
def create_items_bulk(
    payload: Annotated[list[ItemCreate], Body(min_length=1)],
    conn: sqlite3.Connection = Depends(get_db),
) -> list[Item]:
    created: list[Item] = []
    for entry in payload:
        try:
            created.append(items_service.create_item(conn, entry))
        except sqlite3.IntegrityError as exc:
            conn.rollback()
            if "barcode" in str(exc):
                raise HTTPException(
                    status_code=409, detail=f"barcode {entry.barcode!r} already exists"
                )
            raise HTTPException(status_code=409, detail=f"sku {entry.sku!r} already exists")
    return created


_SORTABLE_COLUMNS = items_service.SORTABLE_COLUMNS


@router.get("/items", response_model=ItemPage)
def list_items(
    response: Response,
    active: Optional[bool] = None,
    sku: Optional[str] = None,
    barcode: Optional[str] = None,
    sort: str = Query("id"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_db),
) -> ItemPage:
    descending = sort.startswith("-")
    column = sort[1:] if descending else sort
    if column not in _SORTABLE_COLUMNS:
        raise HTTPException(status_code=422, detail=f"invalid sort field {sort!r}")
    items = items_service.list_items(
        conn,
        active=active,
        sku=sku,
        barcode=barcode,
        sort=column,
        descending=descending,
        limit=limit,
        offset=offset,
    )
    total = items_service.count_items(conn, active=active, sku=sku, barcode=barcode)
    response.headers["X-Total-Count"] = str(total)
    return ItemPage(items=items, total=total, limit=limit, offset=offset)


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
    if not items_service.delete_item(conn, item_id):
        raise HTTPException(status_code=404, detail=f"item {item_id} not found")
    return Response(status_code=204)


@router.get("/items/{item_id}/stock", response_model=ItemStock)
def item_stock(item_id: int, conn: sqlite3.Connection = Depends(get_db)) -> ItemStock:
    _fetch_item(conn, item_id)
    return ItemStock(
        item_id=item_id,
        total=stock.total_stock(conn, item_id),
        levels=stock.get_item_levels(conn, item_id),
    )


@router.get("/items/{item_id}/movements", response_model=list[Movement])
def item_movements(
    item_id: int,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_db),
) -> list[Movement]:
    _fetch_item(conn, item_id)
    return stock.list_movements(conn, item_id=item_id, limit=limit, offset=offset)


# --- locations ---------------------------------------------------------------


@router.post("/locations", response_model=Location, status_code=201)
def create_location(
    payload: LocationCreate, conn: sqlite3.Connection = Depends(get_db)
) -> Location:
    try:
        cur = conn.execute(
            "INSERT INTO locations (code, name) VALUES (?, ?)", (payload.code, payload.name)
        )
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail=f"location code {payload.code!r} already exists")
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


@router.get("/locations/{location_id}/stock", response_model=LocationStock)
def location_stock(
    location_id: int, conn: sqlite3.Connection = Depends(get_db)
) -> LocationStock:
    row = conn.execute("SELECT id FROM locations WHERE id = ?", (location_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"location {location_id} not found")
    return LocationStock(
        location_id=location_id,
        levels=stock.get_location_levels(conn, location_id),
    )


@router.put("/locations/{location_id}", response_model=Location)
def update_location(
    location_id: int, payload: LocationUpdate, conn: sqlite3.Connection = Depends(get_db)
) -> Location:
    row = conn.execute("SELECT * FROM locations WHERE id = ?", (location_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"location {location_id} not found")
    updates = payload.model_dump(exclude_unset=True)
    updates = {k: v for k, v in updates.items() if k in {"name", "code"} and v is not None}
    if updates:
        assignments = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(
            f"UPDATE locations SET {assignments} WHERE id = ?", [*updates.values(), location_id]
        )
    row = conn.execute("SELECT * FROM locations WHERE id = ?", (location_id,)).fetchone()
    return Location(**dict(row))


# --- movements ---------------------------------------------------------------


@router.post("/movements", response_model=Movement, status_code=201)
def create_movement(
    payload: MovementCreate, conn: sqlite3.Connection = Depends(get_db)
) -> Movement:
    return stock.apply_movement(conn, payload)


@router.post("/movements/{movement_id}/reverse", response_model=Movement, status_code=201)
def reverse_movement(
    movement_id: int, conn: sqlite3.Connection = Depends(get_db)
) -> Movement:
    return stock.reverse_movement(conn, movement_id)


@router.get("/movements", response_model=list[Movement])
def list_movements(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_db),
) -> list[Movement]:
    return stock.list_movements(conn, limit=limit, offset=offset)


# --- reports & search --------------------------------------------------------


@router.get("/reports/low-stock", response_model=list[LowStockEntry])
def low_stock_report(
    location_id: Optional[int] = None,
    conn: sqlite3.Connection = Depends(get_db),
) -> list[LowStockEntry]:
    if location_id is not None:
        row = conn.execute(
            "SELECT id FROM locations WHERE id = ?", (location_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"location {location_id} not found")
    return reports.low_stock(conn, location_id=location_id)


@router.get("/reports/value")
def inventory_value_report(
    location_id: Optional[int] = Query(None),
    conn: sqlite3.Connection = Depends(get_db),
) -> dict:
    if location_id is not None:
        row = conn.execute(
            "SELECT id FROM locations WHERE id = ?", (location_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(
                status_code=404, detail=f"location {location_id} not found"
            )
    return {"value": reports.inventory_value(conn, location_id=location_id)}


@router.get("/search", response_model=list[Item])
def search_items(
    q: str = Query(..., min_length=1, max_length=100),
    limit: int = Query(50, ge=1, le=500),
    conn: sqlite3.Connection = Depends(get_db),
) -> list[Item]:
    q = q.strip()
    if not q:
        raise HTTPException(status_code=422, detail="q must not be blank")
    return search.search_items(conn, q, limit=limit)
