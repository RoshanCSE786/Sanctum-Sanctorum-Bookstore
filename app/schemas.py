"""Pydantic request/response schemas.

Field-level rules (trimming, lengths, ISBN checksum, email format) live here so that
invalid input is rejected with 422 before any business logic runs.
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.models import MemberTier

# --- Reusable field types ---------------------------------------------------------------

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
AuthorName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
MemberName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
NonNegativeInt = Annotated[int, Field(ge=0)]

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def normalize_isbn13(raw: str) -> str:
    """Strip hyphens/spaces and verify the ISBN-13 checksum. Raises ValueError if invalid."""
    isbn = raw.replace("-", "").replace(" ", "")
    if len(isbn) != 13 or not isbn.isdigit():
        raise ValueError("isbn must contain exactly 13 digits")
    # TODO: verify the ISBN-13 check digit (see SPEC.md)
    # ******************************************************************
    # Calculate the sum of 1st 12 digits using (1 & 3) alternate weights
    total = sum(
        int(digit) * (1 if i % 2 == 0 else 3)
        for i, digit in enumerate(isbn[:12])
    )

    # Calculate expected check digit: (10 - (sum) % 10) % 10
    check_digit = (10 - (total % 10)) % 10

    # Compare with actual 13th digit
    if check_digit != int(isbn[12]):
        raise ValueError("Invalid ISBN-13 checksum") 
    
    return isbn
    # ******************************************************************************

# --- Health -----------------------------------------------------------------------------


class HealthOut(BaseModel):
    status: str


# --- Books ------------------------------------------------------------------------------


class BookCreate(BaseModel):
    title: Title
    author: AuthorName
    isbn: str
    price_cents: NonNegativeInt
    stock: NonNegativeInt
    restricted: bool = False

    @field_validator("isbn")
    @classmethod
    def validate_isbn(cls, value: str) -> str:
        return normalize_isbn13(value)


class BookUpdate(BaseModel):
    """Partial update. Only fields present in the request body are applied; ``isbn`` is ignored."""

    title: Optional[Title] = None
    author: Optional[AuthorName] = None
    price_cents: Optional[NonNegativeInt] = None
    stock: Optional[NonNegativeInt] = None
    restricted: Optional[bool] = None

    @model_validator(mode="after")
    def reject_explicit_nulls(self) -> BookUpdate:
        for name in self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError(f"{name} may not be null")
        return self


class BookOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    author: str
    isbn: str
    price_cents: int
    stock: int
    restricted: bool


class BookPage(BaseModel):
    items: List[BookOut]
    total: int
    limit: int
    offset: int


BookSort = Literal["title", "-title", "price", "-price"]


# --- Members ----------------------------------------------------------------------------


class MemberCreate(BaseModel):
    name: MemberName
    email: str
    tier: MemberTier = MemberTier.APPRENTICE

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        """Validate and normalize the email address."""
        # *******************************************************
        cleaned = value.strip().lower()
        if not EMAIL_PATTERN.match(cleaned):
            raise ValueError("email is not valid")
        return cleaned
        # ***********************************************************


class MemberOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str
    tier: str
    created_at: datetime


class MemberStats(BaseModel):
    member_id: int
    orders_paid: int
    total_spent_cents: int
    active_loans: int
    overdue_loans: int
    late_fees_cents: int


# --- Orders -----------------------------------------------------------------------------


class OrderItemIn(BaseModel):
    book_id: int
    quantity: int = Field(ge=1)


class OrderCreate(BaseModel):
    member_id: int
    # *************************************************************************
    # TODO: reject an empty items list and the same book_id appearing twice (both 422)
    items: List[OrderItemIn]
    @field_validator("items")
    @classmethod
    def validate_items(cls, value: List[OrderItemIn]) -> List[OrderItemIn]:
        """Reject empty items list or duplicate book_ids in an order."""
        # 1. Reject empty list
        if not value:
            raise ValueError("items may not be empty")

        # 2. reject duplicate book_ids
        seen_book_ids = set()
        for item in value:
            if item.book_id in seen_book_ids:
                raise ValueError(f"Duplicate book_id {item.book_id} in items")
            seen_book_ids.add(item.book_id)
            return value
        
    # *************************************************************************

class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    book_id: int
    quantity: int
    unit_price_cents: int
    line_total_cents: int


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    member_id: int
    status: str
    items: List[OrderItemOut]
    subtotal_cents: int
    discount_percent: int
    discount_cents: int
    total_cents: int
    created_at: datetime


# --- Loans ------------------------------------------------------------------------------

LoanStatus = Literal["active", "overdue", "returned"]


class LoanCreate(BaseModel):
    member_id: int
    book_id: int


class LoanOut(BaseModel):
    id: int
    member_id: int
    book_id: int
    borrowed_at: datetime
    due_at: datetime
    returned_at: Optional[datetime]
    late_fee_cents: int
    status: LoanStatus


# --- Reports ----------------------------------------------------------------------------


class TopBook(BaseModel):
    book_id: int
    title: str
    copies_sold: int
