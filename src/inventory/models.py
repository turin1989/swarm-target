"""Pydantic models (request/response schemas) for the inventory service."""

from typing import Literal, Optional

from pydantic import BaseModel, Field

MovementKind = Literal["receive", "ship", "transfer"]


class ItemCreate(BaseModel):
    sku: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    unit_price: float = Field(0.0, ge=0)
    reorder_point: int = 0


class ItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    unit_price: Optional[float] = Field(None, ge=0)
    reorder_point: Optional[int] = None
    active: Optional[bool] = None


class Item(BaseModel):
    id: int
    sku: str
    name: str
    description: str
    unit_price: float
    reorder_point: int
    active: bool


class LocationCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=32)
    name: str = Field(..., min_length=1, max_length=200)


class Location(BaseModel):
    id: int
    code: str
    name: str


class MovementCreate(BaseModel):
    item_id: int
    kind: MovementKind
    qty: int
    from_location_id: Optional[int] = None
    to_location_id: Optional[int] = None
    note: str = Field("", max_length=500)


class Movement(BaseModel):
    id: int
    item_id: int
    kind: MovementKind
    qty: int
    from_location_id: Optional[int]
    to_location_id: Optional[int]
    note: str


class StockLevel(BaseModel):
    item_id: int
    location_id: int
    qty: int


class ItemStock(BaseModel):
    item_id: int
    total: int
    levels: list[StockLevel]


class LowStockEntry(BaseModel):
    item_id: int
    sku: str
    name: str
    total_qty: int
    reorder_point: int
    shortfall: int = Field(0, ge=0)
