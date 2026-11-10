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
    MovementKind,
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


@router.get("/items", response_model=ItemPage)
def list_items(
    response: Response,
    active: Optional[bool] = None,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    conn: sqlite3.Connection = Depends(get_db),
) -> ItemPage:
    where = ""
    where_params: list = []
    if active is not None:
        where = " WHERE active = ?"
        where_params.append(int(active))
    total = conn.execute(f"SELECT COUNT(*) FROM items{where}", where_params).fetchone()[0]
    response.headers["X-Total-Count"] = str(total)
    rows = conn.execute(
        f"SELECT * FROM items{where} ORDER BY id LIMIT ? OFFSET ?",
        [*where_params, limit, offset],
    ).fetchall()
    return ItemPage(
        items=[items_service.row_to_item(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


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
    return stock.list_movements(conn, limit=limit, offset=offset, item_id=item_id)


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
    conn.execute("DELETE FROM stock_levels WHERE location_id = ?", (location_id,))
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


@router.get("/locations/{location_id}/stock", response_model=LocationStock)
def location_stock(location_id: int, conn: sqlite3.Connection = Depends(get_db)) -> LocationStock:
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
    return stock.list_movements(conn, limit=limit, offset=offset, item_id=item_id, kind=kind)


@router.get("/movements/{movement_id}", response_model=Movement)
def get_movement(movement_id: int, conn: sqlite3.Connection = Depends(get_db)) -> Movement:
    try:
        return stock.get_movement(conn, movement_id)
    except stock.StockError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc))


# --- reports & search --------------------------------------------------------


@router.get("/reports/low-stock", response_model=list[LowStockEntry])
def low_stock_report(conn: sqlite3.Connection = Depends(get_db)) -> list[LowStockEntry]:
    return reports.low_stock(conn)


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
            raise HTTPException(status_code=404, detail=f"location {location_id} not found")
    return {"value": reports.inventory_value(conn, location_id=location_id)}


@router.get("/search", response_model=list[Item])
def search_items(
    q: str = Query(..., min_length=1),
    limit: int = Query(50, ge=1, le=500),
    conn: sqlite3.Connection = Depends(get_db),
) -> list[Item]:
    return search.search_items(conn, q, limit=limit)
