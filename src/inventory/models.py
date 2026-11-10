"""Pydantic models (request/response schemas) for the inventory service."""

from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator

MovementKind = Literal["receive", "ship", "transfer", "adjust"]


def _reject_reorder_point(data):
    """The field was renamed to reorder_level; the old name is rejected."""
    if isinstance(data, dict) and "reorder_point" in data:
        raise ValueError("reorder_point has been renamed to reorder_level")
    return data


class ItemCreate(BaseModel):
    sku: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=200)
    description: str = Field("", max_length=2000)
    unit_price: float = Field(0.0, ge=0)
    reorder_level: int = Field(0, ge=0)
    barcode: Optional[str] = Field(None, min_length=1, max_length=64)

    @field_validator("sku")
    @classmethod
    def normalise_sku(cls, value: str) -> str:
        normalised = value.strip().upper()
        if not normalised:
            raise ValueError("sku must not be empty or whitespace only")
        return normalised

    _no_reorder_point = model_validator(mode="before")(_reject_reorder_point)


class ItemUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = Field(None, max_length=2000)
    unit_price: Optional[float] = Field(None, ge=0)
    reorder_level: Optional[int] = Field(None, ge=0)
    active: Optional[bool] = None

    _no_reorder_point = model_validator(mode="before")(_reject_reorder_point)


class Item(BaseModel):
    id: int
    sku: str
    name: str
    description: str
    unit_price: float
    reorder_level: int
    active: bool
    created_at: str
    barcode: Optional[str] = None


class ItemPage(BaseModel):
    items: list[Item]
    total: int
    limit: int
    offset: int


class LocationCreate(BaseModel):
    code: str = Field(..., min_length=1, max_length=32, pattern=r"^[A-Z0-9][A-Z0-9-]{0,31}$")
    name: str = Field(..., min_length=1, max_length=200)


class LocationUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=200)
    code: Optional[str] = Field(
        None, min_length=1, max_length=32, pattern=r"^[A-Z0-9][A-Z0-9-]{0,31}$"
    )
    active: Optional[bool] = None


class Location(BaseModel):
    id: int
    code: str
    name: str
    active: bool = True


def _reject_qty(data):
    """The field was renamed to quantity; the old name is rejected."""
    if isinstance(data, dict) and "qty" in data:
        raise ValueError("qty has been renamed to quantity")
    return data


class MovementCreate(BaseModel):
    item_id: int
    kind: MovementKind
    quantity: int = Field(..., gt=0)
    from_location_id: Optional[int] = None
    to_location_id: Optional[int] = None
    note: str = Field("", max_length=500)
    reference: Optional[str] = Field(None, max_length=64)

    _no_qty = model_validator(mode="before")(_reject_qty)


class Movement(BaseModel):
    id: int
    item_id: int
    kind: MovementKind
    quantity: int
    from_location_id: Optional[int]
    to_location_id: Optional[int]
    note: str
    reference: Optional[str] = None
    created_at: str


class StockLevel(BaseModel):
    item_id: int
    location_id: int
    quantity: int


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
