"""Pydantic models (request/response schemas) for the inventory service."""

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

MovementKind = Literal["receive", "ship", "transfer", "adjust"]

LOCATION_CODE_PATTERN = r"^[A-Z0-9][A-Z0-9-]{0,31}$"


class ItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sku: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field(default="", max_length=2000)
    unit_price: float = 0.0
    reorder_level: int = Field(default=0, ge=0)
    barcode: Optional[str] = None


class ItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Optional[str] = None
    description: Optional[str] = Field(default=None, max_length=2000)
    unit_price: Optional[float] = None
    reorder_level: Optional[int] = Field(default=None, ge=0)
    active: Optional[bool] = None
    # Accepted for convenience but ignored: created_at is server-managed.
    created_at: Optional[str] = None


class Item(BaseModel):
    id: int
    sku: str
    name: str
    description: str
    unit_price: float
    reorder_level: int
    active: bool
    barcode: Optional[str] = None
    created_at: str


class ItemPage(BaseModel):
    items: list[Item]
    total: int
    limit: int
    offset: int


class LocationCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=32, pattern=LOCATION_CODE_PATTERN)
    name: str = Field(..., min_length=1, max_length=200)


class LocationUpdate(BaseModel):
    code: Optional[str] = Field(
        default=None, min_length=1, max_length=32, pattern=LOCATION_CODE_PATTERN
    )
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    active: Optional[bool] = None


class Location(BaseModel):
    id: int
    code: str
    name: str
    active: bool = True


class MovementCreate(BaseModel):
    item_id: int
    kind: MovementKind
    qty: int = Field(..., gt=0)
    from_location_id: Optional[int] = None
    to_location_id: Optional[int] = None
    note: str = Field(default="", max_length=500)
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


class LocationStock(BaseModel):
    location_id: int
    levels: list[StockLevel]


class LowStockEntry(BaseModel):
    item_id: int
    sku: str
    name: str
    total_qty: int
    reorder_level: int
    shortfall: int = Field(..., ge=0)
