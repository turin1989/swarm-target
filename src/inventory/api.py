"""HTTP routes."""

import sqlite3
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from inventory.db import get_db
from inventory.models import (
    Item,
    ItemCreate,
    ItemStock,
    ItemUpdate,
    Location,
    LocationCreate,
    LocationStock,
    LowStockEntry,
    Movement,
    MovementCreate,
)
from inventory.services import items as items_service
from inventory.services import reports, search, stock

router = APIRouter()


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
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail=f"sku {payload.sku!r} already exists")


_SORTABLE_ITEM_COLUMNS = {"id", "name", "sku"}


@router.post("/items/bulk", response_model=list[Item], status_code=201)
def create_items_bulk(
    payload: list[ItemCreate], conn: sqlite3.Connection = Depends(get_db)
) -> list[Item]:
    if not payload:
        raise HTTPException(status_code=422, detail="item list must not be empty")
    created_ids: list[int] = []
    try:
        for item in payload:
            cur = conn.execute(
                """
                INSERT INTO items (sku, name, description, unit_price, reorder_point)
                VALUES (?, ?, ?, ?, ?)
                """,
                (item.sku, item.name, item.description, item.unit_price, item.reorder_point),
            )
            created_ids.append(cur.lastrowid)
    except sqlite3.IntegrityError:
        conn.rollback()
        raise HTTPException(status_code=409, detail=f"sku {item.sku!r} already exists")
    return [_fetch_item(conn, item_id) for item_id in created_ids]


@router.get("/items", response_model=list[Item])
def list_items(
    response: Response,
    active: Optional[bool] = None,
    sku: Optional[str] = None,
    sort: str = Query("id", pattern=r"^-?(id|name|sku)$"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_db),
) -> list[Item]:
    sql = "SELECT * FROM items"
    params: list = []
    conditions: list[str] = []
    if active is not None:
        conditions.append("active = ?")
        params.append(int(active))
    if sku is not None:
        conditions.append("sku = ?")
        params.append(sku)
    where = ""
    if conditions:
        where = " WHERE " + " AND ".join(conditions)
        sql += where
    total = conn.execute(
        "SELECT COUNT(*) FROM items" + where, params
    ).fetchone()[0]
    response.headers["X-Total-Count"] = str(total)
    direction = "ASC"
    column = sort
    if column.startswith("-"):
        direction = "DESC"
        column = column[1:]
    if column not in _SORTABLE_ITEM_COLUMNS:  # defence in depth; pattern already enforces
        raise HTTPException(status_code=422, detail=f"invalid sort field {sort!r}")
    sql += f" ORDER BY {column} {direction} LIMIT ? OFFSET ?"
    params += [limit, offset]
    return [items_service.row_to_item(r) for r in conn.execute(sql, params).fetchall()]


@router.get("/items/by-sku/{sku}", response_model=Item)
def get_item_by_sku(sku: str, conn: sqlite3.Connection = Depends(get_db)) -> Item:
    row = conn.execute("SELECT * FROM items WHERE sku = ?", (sku,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"sku {sku} not found")
    return items_service.row_to_item(row)


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
    deleted = items_service.delete_item(conn, item_id)
    if not deleted:
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


@router.get("/locations/{location_id}/stock", response_model=LocationStock)
def location_stock(
    location_id: int, conn: sqlite3.Connection = Depends(get_db)
) -> LocationStock:
    try:
        levels = stock.get_location_levels(conn, location_id)
    except stock.StockError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))
    return LocationStock(location_id=location_id, levels=levels)


@router.delete("/locations/{location_id}", status_code=204)
def delete_location(location_id: int, conn: sqlite3.Connection = Depends(get_db)) -> Response:
    row = conn.execute("SELECT id FROM locations WHERE id = ?", (location_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"location {location_id} not found")
    holds_stock = conn.execute(
        "SELECT 1 FROM stock_levels WHERE location_id = ? AND qty != 0 LIMIT 1",
        (location_id,),
    ).fetchone()
    if holds_stock is not None:
        raise HTTPException(
            status_code=409, detail=f"location {location_id} holds stock"
        )
    # Movement history rows reference locations without a cascade; detach them
    # so the delete can proceed (stock_levels rows cascade automatically).
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
    try:
        return stock.apply_movement(conn, payload)
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
            "SELECT id FROM locations WHERE id = ?", (location_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(
                status_code=404, detail=f"location {location_id} not found"
            )
    return reports.low_stock(conn, location_id=location_id)


@router.get("/reports/movements-summary")
def movements_summary_report(conn: sqlite3.Connection = Depends(get_db)) -> dict:
    return reports.movements_summary(conn)


@router.get("/reports/value")
def inventory_value_report(
    location_id: Optional[int] = None, conn: sqlite3.Connection = Depends(get_db)
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
