"""Pydantic models (request/response schemas) for the inventory service."""

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

MovementKind = Literal["receive", "ship", "transfer", "adjust"]


class _RejectsReorderPoint(BaseModel):
    """Reject the legacy ``reorder_point`` field (renamed to ``reorder_level``)."""

    @model_validator(mode="before")
    @classmethod
    def reject_reorder_point(cls, data: object) -> object:
        if isinstance(data, dict) and "reorder_point" in data:
            raise ValueError("'reorder_point' was renamed to 'reorder_level'")
        return data


class ItemCreate(_RejectsReorderPoint):
    sku: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=200)
    description: str = ""
    unit_price: float = 0.0
    reorder_level: int = 0

    @field_validator("sku", mode="before")
    @classmethod
    def normalise_sku(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip().upper()
        return value


class ItemUpdate(_RejectsReorderPoint):
    name: Optional[str] = None
    description: Optional[str] = None
    unit_price: Optional[float] = None
    reorder_level: Optional[int] = None
    active: Optional[bool] = None


class Item(BaseModel):
    id: int
    sku: str
    name: str
    description: str
    unit_price: float
    reorder_level: int
    active: bool
    created_at: str


class LocationCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=32, pattern=r"^[A-Z0-9][A-Z0-9-]{0,31}$")
    name: str = Field(..., min_length=1, max_length=200)


class LocationUpdate(BaseModel):
    code: Optional[str] = Field(None, min_length=1, max_length=32)
    name: Optional[str] = Field(None, min_length=1, max_length=200)


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
    note: str = Field(default="", max_length=500)


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
    shortfall: int = Field(..., ge=0)
