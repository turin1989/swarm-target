"""Pydantic models (request/response schemas) for the inventory service."""

from typing import Literal, Optional

from pydantic import BaseModel, Field

MovementKind = Literal["receive", "ship", "transfer"]


class ItemCreate(BaseModel):
    sku: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    unit_price: float = 0.0
    reorder_point: int = 0
    barcode: Optional[str] = None


class ItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = Field(default=None, max_length=2000)
    unit_price: Optional[float] = None
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
    barcode: Optional[str] = None


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
    note: str = ""
    reference: Optional[str] = Field(default=None, max_length=64)


class Movement(BaseModel):
    id: int
    item_id: int
    kind: MovementKind
    qty: int
    from_location_id: Optional[int]
    to_location_id: Optional[int]
    note: str
    reference: Optional[str] = None


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
