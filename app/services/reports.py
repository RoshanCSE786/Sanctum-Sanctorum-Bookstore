"""Reporting queries."""
from typing import List

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Book, Order, OrderItem, OrderStatus
from app.schemas import TopBook


def top_books(db: Session, limit: int = 5) -> List[TopBook]:
    """Best-selling books.

    Rules: copies_sold sums quantities over ``paid`` orders only; books with no sales are
    excluded; sorted by copies_sold desc, then title asc; at most ``limit`` rows.
    """
    # raise NotImplementedError("top_books")
    # *****************************************************************************
    stmt = (
        select(
            Book.id.label("book_id"),
            Book.title.label("title"),
            func.sum(OrderItem.quantity).label("copies_sold"),
        )
        .join(OrderItem, Book.id == OrderItem.book_id)
        .join(Order, OrderItem.order_id == Order.id)
        .where(Order.status == OrderStatus.PAID.value)
        .group_by(Book.id, Book.title)
        .order_by(
            func.sum(OrderItem.quantity).desc(),
            Book.title.asc(),
        )
        .limit(limit)
    )

    rows = db.execute(stmt).all()

    return [
        TopBook(
            book_id = row.book_id,
            title = row.title,
            copies_sold = row.copies_sold,
        )
        for row in rows
    ]
    # *****************************************************************************
