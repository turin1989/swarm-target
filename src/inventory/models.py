"""Pydantic models (request/response schemas) for the inventory service."""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

MovementKind = Literal["receive", "ship", "transfer"]


class ItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    unit_price: float = Field(default=0.0, ge=0)
    reorder_level: int = Field(default=0, ge=0)


class ItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    description: Optional[str] = Field(default=None, max_length=2000)
    unit_price: Optional[float] = Field(default=None, ge=0)
    reorder_level: Optional[int] = Field(default=None, ge=0)
    active: Optional[bool] = None


class Item(BaseModel):
    id: int
    sku: str
    name: str
    description: str
    unit_price: float
    reorder_level: int
    active: bool


class ItemPage(BaseModel):
    items: list[Item]
    total: int
    limit: int
    offset: int


class LocationCreate(BaseModel):
    code: str = Field(..., pattern=r"^[A-Z0-9][A-Z0-9-]{0,31}$")
    name: str = Field(..., min_length=1, max_length=200)


class Location(BaseModel):
    id: int
    code: str
    name: str


class MovementCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: int
    kind: MovementKind
    quantity: int
    from_location_id: Optional[int] = None
    to_location_id: Optional[int] = None
    note: str = Field(default="", max_length=500)


class Movement(BaseModel):
    id: int
    item_id: int
    kind: MovementKind
    quantity: int
    from_location_id: Optional[int]
    to_location_id: Optional[int]
    note: str


class StockLevel(BaseModel):
    item_id: int
    location_id: int
    quantity: int


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
    shortfall: int = Field(ge=0)
