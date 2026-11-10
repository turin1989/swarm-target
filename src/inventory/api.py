"""HTTP routes."""

import sqlite3
from typing import Annotated, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response

from inventory.db import get_db, utc_now_iso
from inventory.models import (
    Item,
    ItemCreate,
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

_ITEM_SORT_COLUMNS = {"id", "name", "sku"}


def _parse_item_sort(sort: str) -> str:
    direction = "ASC"
    column = sort
    if sort.startswith("-"):
        direction = "DESC"
        column = sort[1:]
    if column not in _ITEM_SORT_COLUMNS:
        raise HTTPException(
            status_code=422,
            detail=f"invalid sort {sort!r}; expected one of: id, name, sku (optionally prefixed with '-')",
        )
    return f"{column} {direction}"


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


@router.post("/items/bulk", response_model=list[Item], status_code=201)
def create_items_bulk(
    payload: Annotated[list[ItemCreate], Body(min_length=1)],
    conn: sqlite3.Connection = Depends(get_db),
) -> list[Item]:
    created_ids: list[int] = []
    for entry in payload:
        try:
            cur = conn.execute(
                """
                INSERT INTO items (sku, name, description, unit_price, reorder_point, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.sku,
                    entry.name,
                    entry.description,
                    entry.unit_price,
                    entry.reorder_point,
                    utc_now_iso(),
                ),
            )
        except sqlite3.IntegrityError:
            # get_db rolls back the whole transaction, so nothing is created.
            raise HTTPException(status_code=409, detail=f"sku {entry.sku!r} already exists")
        created_ids.append(cur.lastrowid)
    return [_fetch_item(conn, item_id) for item_id in created_ids]


@router.get("/items", response_model=list[Item])
def list_items(
    response: Response,
    active: Optional[bool] = None,
    sku: Optional[str] = None,
    barcode: Optional[str] = None,
    sort: str = Query("id"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_db),
) -> list[Item]:
    order_by = _parse_item_sort(sort)
    params: list = []
    conditions: list[str] = []
    if active is not None:
        conditions.append("active = ?")
        params.append(int(active))
    if sku is not None:
        conditions.append("sku = ?")
        params.append(sku)
    if barcode is not None:
        conditions.append("barcode = ?")
        params.append(barcode)
    where = " WHERE " + " AND ".join(conditions) if conditions else ""
    total = conn.execute(f"SELECT COUNT(*) FROM items{where}", params).fetchone()[0]
    response.headers["X-Total-Count"] = str(total)
    sql = f"SELECT * FROM items{where} ORDER BY {order_by} LIMIT ? OFFSET ?"
    return [_row_to_item(r) for r in conn.execute(sql, [*params, limit, offset]).fetchall()]


@router.get("/items/by-sku/{sku}", response_model=Item)
def get_item_by_sku(sku: str, conn: sqlite3.Connection = Depends(get_db)) -> Item:
    row = conn.execute("SELECT * FROM items WHERE sku = ?", (sku,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"sku {sku} not found")
    return _row_to_item(row)


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
    _fetch_item(conn, item_id)
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


def _row_to_location(row: sqlite3.Row) -> Location:
    data = dict(row)
    data["active"] = bool(data["active"])
    return Location(**data)


def _fetch_location(conn: sqlite3.Connection, location_id: int) -> Location:
    row = conn.execute("SELECT * FROM locations WHERE id = ?", (location_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"location {location_id} not found")
    return _row_to_location(row)


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
    return _fetch_location(conn, cur.lastrowid)


@router.get("/locations", response_model=list[Location])
def list_locations(
    active: Optional[bool] = None,
    conn: sqlite3.Connection = Depends(get_db),
) -> list[Location]:
    params: list = []
    where = ""
    if active is not None:
        where = " WHERE active = ?"
        params.append(int(active))
    rows = conn.execute(f"SELECT * FROM locations{where} ORDER BY id", params).fetchall()
    return [_row_to_location(r) for r in rows]


@router.get("/locations/{location_id}", response_model=Location)
def get_location(location_id: int, conn: sqlite3.Connection = Depends(get_db)) -> Location:
    return _fetch_location(conn, location_id)


@router.put("/locations/{location_id}", response_model=Location)
def update_location(
    location_id: int, payload: LocationUpdate, conn: sqlite3.Connection = Depends(get_db)
) -> Location:
    _fetch_location(conn, location_id)
    updates = payload.model_dump(exclude_unset=True)
    allowed = {"name", "active"}
    updates = {k: v for k, v in updates.items() if k in allowed and v is not None}
    if updates:
        if "active" in updates:
            updates["active"] = int(updates["active"])
        assignments = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(
            f"UPDATE locations SET {assignments} WHERE id = ?",
            [*updates.values(), location_id],
        )
    return _fetch_location(conn, location_id)


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
    try:
        return stock.apply_movement(conn, payload)
    except stock.StockError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))


@router.post("/movements/{movement_id}/reverse", response_model=Movement, status_code=201)
def reverse_movement(
    movement_id: int, conn: sqlite3.Connection = Depends(get_db)
) -> Movement:
    try:
        return stock.reverse_movement(conn, movement_id)
    except stock.StockError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))


@router.get("/movements", response_model=list[Movement])
def list_movements(
    item_id: Optional[int] = None,
    kind: Optional[MovementKind] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_db),
) -> list[Movement]:
    return stock.list_movements(conn, item_id=item_id, kind=kind, limit=limit, offset=offset)


# --- reports & search --------------------------------------------------------


@router.get("/reports/low-stock", response_model=list[LowStockEntry])
def low_stock_report(
    location_id: Optional[int] = None,
    conn: sqlite3.Connection = Depends(get_db),
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


@router.get("/reports/movements-summary")
def movements_summary_report(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    return reports.movements_summary(conn)


@router.get("/stats")
def stats(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    return reports.stats(conn)


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
