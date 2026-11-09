"""HTTP routes."""

import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import JSONResponse

from inventory.db import get_db, utc_now_iso
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
    MovementKind,
)
from inventory.services import reports, search, stock
from inventory.services.errors import InventoryError

router = APIRouter()


def inventory_error_handler(request: Request, exc: InventoryError) -> JSONResponse:
    """Translate service-layer ``InventoryError`` into an HTTP error response.

    Registered on the application in :func:`inventory.main.create_app` so that
    routes do not need per-route try/except blocks.
    """
    return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})


def _row_to_item(row: sqlite3.Row) -> Item:
    data = dict(row)
    data["active"] = bool(data["active"])
    return Item(**data)


def _fetch_item(conn: sqlite3.Connection, item_id: int) -> Item:
    row = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"item {item_id} not found")
    return _row_to_item(row)


# --- items -------------------------------------------------------------------


@router.post("/items", response_model=Item, status_code=201)
def create_item(payload: ItemCreate, conn: sqlite3.Connection = Depends(get_db)) -> Item:
    try:
        cur = conn.execute(
            """
            INSERT INTO items (sku, name, description, unit_price, reorder_point, created_at, barcode)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.sku,
                payload.name,
                payload.description,
                payload.unit_price,
                payload.reorder_point,
                utc_now_iso(),
                payload.barcode,
            ),
        )
    except sqlite3.IntegrityError as exc:
        if "barcode" in str(exc):
            raise HTTPException(
                status_code=409, detail=f"barcode {payload.barcode!r} already exists"
            )
        raise HTTPException(status_code=409, detail=f"sku {payload.sku!r} already exists")
    return _fetch_item(conn, cur.lastrowid)


@router.get("/items", response_model=ItemPage)
def list_items(
    response: Response,
    active: Optional[bool] = None,
    barcode: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_db),
) -> ItemPage:
    conditions: list[str] = []
    params: list = []
    if active is not None:
        conditions.append("active = ?")
        params.append(int(active))
    if barcode is not None:
        conditions.append("barcode = ?")
        params.append(barcode)
    where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
    total = conn.execute(f"SELECT COUNT(*) FROM items{where}", params).fetchone()[0]
    response.headers["X-Total-Count"] = str(total)
    sql = f"SELECT * FROM items{where} ORDER BY id LIMIT ? OFFSET ?"
    rows = conn.execute(sql, [*params, limit, offset]).fetchall()
    return ItemPage(
        items=[_row_to_item(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/items/{item_id}", response_model=Item)
def get_item(item_id: int, conn: sqlite3.Connection = Depends(get_db)) -> Item:
    return _fetch_item(conn, item_id)


@router.put("/items/{item_id}", response_model=Item)
def update_item(
    item_id: int, payload: ItemUpdate, conn: sqlite3.Connection = Depends(get_db)
) -> Item:
    _fetch_item(conn, item_id)
    updates = payload.model_dump(exclude_unset=True)
    allowed = {"name", "description", "unit_price", "active"}
    updates = {k: v for k, v in updates.items() if k in allowed and v is not None}
    if updates:
        if "active" in updates:
            updates["active"] = int(updates["active"])
        assignments = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(f"UPDATE items SET {assignments} WHERE id = ?", [*updates.values(), item_id])
    return _fetch_item(conn, item_id)


@router.delete("/items/{item_id}", status_code=204)
def delete_item(item_id: int, conn: sqlite3.Connection = Depends(get_db)) -> Response:
    cur = conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
    if cur.rowcount == 0:
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
        raise HTTPException(
            status_code=409, detail=f"location code {payload.code!r} already exists"
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


# --- movements ---------------------------------------------------------------


@router.post("/movements", response_model=Movement, status_code=201)
def create_movement(
    payload: MovementCreate, conn: sqlite3.Connection = Depends(get_db)
) -> Movement:
    return stock.apply_movement(conn, payload)


@router.get("/movements", response_model=list[Movement])
def list_movements(
    item_id: Optional[int] = None,
    kind: Optional[MovementKind] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_db),
) -> list[Movement]:
    return stock.list_movements(conn, limit=limit, offset=offset, item_id=item_id, kind=kind)


@router.get("/movements/{movement_id}", response_model=Movement)
def get_movement(movement_id: int, conn: sqlite3.Connection = Depends(get_db)) -> Movement:
    return stock.get_movement(conn, movement_id)


# --- reports & search --------------------------------------------------------


@router.get("/reports/low-stock", response_model=list[LowStockEntry])
def low_stock_report(conn: sqlite3.Connection = Depends(get_db)) -> list[LowStockEntry]:
    return reports.low_stock(conn)


@router.get("/reports/value")
def inventory_value_report(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    return {"value": reports.inventory_value(conn)}


@router.get("/search", response_model=list[Item])
def search_items(
    q: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=500),
    conn: sqlite3.Connection = Depends(get_db),
) -> list[Item]:
    return search.search_items(conn, q, limit=limit)
