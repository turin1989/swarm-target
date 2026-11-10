"""HTTP routes."""

import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response

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
    LowStockEntry,
    Movement,
    MovementCreate,
)
from inventory.services import reports, search, stock

router = APIRouter()


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
            INSERT INTO items (sku, name, description, unit_price, reorder_level, barcode)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                payload.sku,
                payload.name,
                payload.description,
                payload.unit_price,
                payload.reorder_level,
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
    active: Optional[bool] = None,
    barcode: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_db),
) -> ItemPage:
    params: list = []
    conditions: list[str] = []
    if active is not None:
        conditions.append("active = ?")
        params.append(int(active))
    if barcode is not None:
        conditions.append("barcode = ?")
        params.append(barcode)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    total = conn.execute(f"SELECT COUNT(*) FROM items{where}", params).fetchone()[0]
    rows = conn.execute(
        f"SELECT * FROM items{where} ORDER BY id LIMIT ? OFFSET ?",
        [*params, limit, offset],
    ).fetchall()
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
    remaining = stock.total_stock(conn, item_id)
    if remaining > 0:
        raise HTTPException(
            status_code=409,
            detail=f"item {item_id} still has {remaining} units in stock",
        )
    conn.execute("DELETE FROM items WHERE id = ?", (item_id,))
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


@router.delete("/locations/{location_id}", status_code=204)
def delete_location(location_id: int, conn: sqlite3.Connection = Depends(get_db)) -> Response:
    row = conn.execute("SELECT id FROM locations WHERE id = ?", (location_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"location {location_id} not found")
    holding = conn.execute(
        "SELECT 1 FROM stock_levels WHERE location_id = ? AND qty != 0 LIMIT 1",
        (location_id,),
    ).fetchone()
    if holding is not None:
        raise HTTPException(
            status_code=409, detail=f"location {location_id} holds stock and cannot be deleted"
        )
    # Detach movement history so the FK constraint allows the delete.
    conn.execute(
        "UPDATE movements SET from_location_id = NULL WHERE from_location_id = ?", (location_id,)
    )
    conn.execute(
        "UPDATE movements SET to_location_id = NULL WHERE to_location_id = ?", (location_id,)
    )
    conn.execute("DELETE FROM locations WHERE id = ?", (location_id,))
    return Response(status_code=204)


# --- movements ---------------------------------------------------------------


@router.post("/movements", response_model=Movement, status_code=201)
def create_movement(
    payload: MovementCreate, conn: sqlite3.Connection = Depends(get_db)
) -> Movement:
    try:
        return stock.apply_movement(conn, payload)
    except stock.StockError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))


@router.post("/movements/{movement_id}/reverse", response_model=Movement, status_code=201)
def reverse_movement(movement_id: int, conn: sqlite3.Connection = Depends(get_db)) -> Movement:
    try:
        return stock.reverse_movement(conn, movement_id)
    except stock.StockError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get("/movements/{movement_id}", response_model=Movement)
def get_movement(movement_id: int, conn: sqlite3.Connection = Depends(get_db)) -> Movement:
    try:
        return stock.get_movement(conn, movement_id)
    except stock.StockError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))


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
    location_id: Optional[int] = None, conn: sqlite3.Connection = Depends(get_db)
) -> list[LowStockEntry]:
    if location_id is not None:
        row = conn.execute(
            "SELECT 1 FROM locations WHERE id = ?", (location_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(
                status_code=404, detail=f"location {location_id} not found"
            )
    return reports.low_stock(conn, location_id=location_id)


@router.get("/reports/value")
def inventory_value_report(
    location_id: Optional[int] = None, conn: sqlite3.Connection = Depends(get_db)
) -> dict:
    if location_id is not None:
        row = conn.execute(
            "SELECT id FROM locations WHERE id = ?", (location_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"location {location_id} not found")
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
