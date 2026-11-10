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
    MovementKind,
)
from inventory.services import items as items_service
from inventory.services import reports, search, stock
from inventory.services.errors import InventoryError

router = APIRouter()

_ERROR_CODES = {
    400: "bad_request",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
}


def _error_code_for_status(status_code: int) -> str:
    code = _ERROR_CODES.get(status_code)
    if code is not None:
        return code
    if 400 <= status_code < 500:
        return "bad_request"
    return "internal_error"


def error_response(status_code: int, message: str) -> JSONResponse:
    """Uniform error body: {"error": {"code": "<snake_case>", "message": "<text>"}}."""
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": _error_code_for_status(status_code), "message": message}},
    )


def inventory_error_handler(request: Request, exc: InventoryError) -> JSONResponse:
    """Translate service-layer errors into HTTP responses in one place.

    Registered on the application (see ``inventory.main.create_app``) so no
    route needs its own try/except around service calls. The response body
    uses the uniform error shape shared by every 4xx/5xx response.
    """
    return error_response(exc.status_code, str(exc))


def _fetch_item(conn: sqlite3.Connection, item_id: int) -> Item:
    item = items_service.get_item(conn, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"item {item_id} not found")
    return item


# --- items -------------------------------------------------------------------

_SORTABLE_ITEM_COLUMNS = {"id", "name", "sku"}


def _parse_items_sort(sort: str) -> str:
    """Translate a sort query value into an ORDER BY clause; 422 if invalid."""
    direction = "ASC"
    column = sort
    if sort.startswith("-"):
        direction = "DESC"
        column = sort[1:]
    if column not in _SORTABLE_ITEM_COLUMNS:
        allowed = ", ".join(sorted(_SORTABLE_ITEM_COLUMNS))
        raise HTTPException(
            status_code=422,
            detail=f"invalid sort {sort!r}: must be one of {allowed}, optionally prefixed with '-'",
        )
    return f"{column} {direction}"


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
            # Atomic: discard everything inserted so far.
            conn.rollback()
            if "barcode" in str(exc):
                raise HTTPException(
                    status_code=409, detail=f"barcode {entry.barcode!r} already exists"
                )
            raise HTTPException(status_code=409, detail=f"sku {entry.sku!r} already exists")
    return created


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
    order_by = _parse_items_sort(sort)
    params: list = []
    clauses: list[str] = []
    if active is not None:
        clauses.append("active = ?")
        params.append(int(active))
    if sku is not None:
        clauses.append("sku = ?")
        params.append(sku)
    if barcode is not None:
        clauses.append("barcode = ?")
        params.append(barcode)
    where = ""
    if clauses:
        where = " WHERE " + " AND ".join(clauses)
    total = conn.execute(f"SELECT COUNT(*) FROM items{where}", params).fetchone()[0]
    response.headers["X-Total-Count"] = str(total)
    sql = f"SELECT * FROM items{where} ORDER BY {order_by} LIMIT ? OFFSET ?"
    params += [limit, offset]
    items = [items_service.row_to_item(r) for r in conn.execute(sql, params).fetchall()]
    return ItemPage(items=items, total=total, limit=limit, offset=offset)


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
    return _row_to_location(row)


@router.get("/locations", response_model=list[Location])
def list_locations(
    active: Optional[bool] = None, conn: sqlite3.Connection = Depends(get_db)
) -> list[Location]:
    sql = "SELECT * FROM locations"
    params: list = []
    if active is not None:
        sql += " WHERE active = ?"
        params.append(int(active))
    sql += " ORDER BY id"
    rows = conn.execute(sql, params).fetchall()
    return [_row_to_location(r) for r in rows]


@router.get("/locations/{location_id}", response_model=Location)
def get_location(location_id: int, conn: sqlite3.Connection = Depends(get_db)) -> Location:
    row = conn.execute("SELECT * FROM locations WHERE id = ?", (location_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"location {location_id} not found")
    return _row_to_location(row)


@router.put("/locations/{location_id}", response_model=Location)
def update_location(
    location_id: int, payload: LocationUpdate, conn: sqlite3.Connection = Depends(get_db)
) -> Location:
    row = conn.execute("SELECT * FROM locations WHERE id = ?", (location_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"location {location_id} not found")
    updates = {
        k: v for k, v in payload.model_dump(exclude_unset=True).items() if v is not None
    }
    if updates:
        if "active" in updates:
            updates["active"] = int(updates["active"])
        assignments = ", ".join(f"{k} = ?" for k in updates)
        conn.execute(
            f"UPDATE locations SET {assignments} WHERE id = ?",
            [*updates.values(), location_id],
        )
    row = conn.execute("SELECT * FROM locations WHERE id = ?", (location_id,)).fetchone()
    return _row_to_location(row)


@router.get("/locations/{location_id}/stock", response_model=LocationStock)
def location_stock(
    location_id: int, conn: sqlite3.Connection = Depends(get_db)
) -> LocationStock:
    levels = stock.get_location_levels(conn, location_id)
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
            status_code=409,
            detail=f"location {location_id} still holds stock and cannot be deleted",
        )
    # Detach movement history (FK has no ON DELETE action) before deleting.
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


@router.post("/movements/{movement_id}/reverse", response_model=Movement, status_code=201)
def reverse_movement(movement_id: int, conn: sqlite3.Connection = Depends(get_db)) -> Movement:
    return stock.reverse_movement(conn, movement_id)


@router.get("/movements/{movement_id}", response_model=Movement)
def get_movement(movement_id: int, conn: sqlite3.Connection = Depends(get_db)) -> Movement:
    return stock.get_movement(conn, movement_id)


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
    location_id: Optional[int] = None, conn: sqlite3.Connection = Depends(get_db)
) -> list[LowStockEntry]:
    if location_id is not None:
        row = conn.execute(
            "SELECT id FROM locations WHERE id = ?", (location_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail=f"location {location_id} not found")
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
            raise HTTPException(status_code=404, detail=f"location {location_id} not found")
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
    query = q.strip()
    if not query:
        raise HTTPException(status_code=422, detail="q must not be blank")
    return search.search_items(conn, query, limit=limit)
