"""Pydantic models (request/response schemas) for the inventory service."""

from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

MovementKind = Literal["receive", "ship", "transfer"]


class ItemCreate(BaseModel):
    sku: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field("", max_length=2000)
    unit_price: float = Field(0.0, ge=0)
    reorder_level: int = 0

    @model_validator(mode="before")
    @classmethod
    def _reject_reorder_point(cls, data):
        if isinstance(data, dict) and "reorder_point" in data:
            raise ValueError("'reorder_point' has been renamed to 'reorder_level'")
        return data


class ItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = Field(None, max_length=2000)
    unit_price: Optional[float] = Field(None, ge=0)
    reorder_level: Optional[int] = None
    active: Optional[bool] = None

    @model_validator(mode="before")
    @classmethod
    def _reject_reorder_point(cls, data):
        if isinstance(data, dict) and "reorder_point" in data:
            raise ValueError("'reorder_point' has been renamed to 'reorder_level'")
        return data


class Item(BaseModel):
    id: int
    sku: str
    name: str
    description: str
    unit_price: float
    reorder_level: int
    active: bool
    created_at: str


class ItemPage(BaseModel):
    items: list[Item]
    total: int
    limit: int
    offset: int


class LocationCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=32, pattern=r"^[A-Z0-9][A-Z0-9-]{0,31}$")
    name: str = Field(..., min_length=1, max_length=200)


class Location(BaseModel):
    id: int
    code: str
    name: str


class MovementCreate(BaseModel):
    item_id: int
    kind: MovementKind
    qty: int = Field(..., gt=0)
    from_location_id: Optional[int] = None
    to_location_id: Optional[int] = None
    note: str = ""


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
    reorder_level: int
