"""Book catalogue operations."""
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session

from app.models import Book
from app.schemas import BookCreate, BookPage, BookSort, BookUpdate


def create_book(db: Session, data: BookCreate) -> Book:
    """Add a book to the catalogue.

    Rules: the (already normalized) ISBN must be unique -> 409 otherwise.
    """
    # TODO: reject a duplicate ISBN with 409
    # *****************************************************
    # Reject duplicate ISBN
    existing = db.scalar(select(Book).where(Book.isbn == data.isbn))
    if existing is not None:
        raise HTTPException(
            status_code = status.HTTP_409_CONFLICT,
            detail = "Book with this ISBN already exists",
        )
    # ************************************************************
    book = Book(**data.model_dump())
    db.add(book)
    db.commit()
    db.refresh(book)
    return book


def get_book(db: Session, book_id: int) -> Book:
    """Return a book by id, or raise 404."""
    book = db.get(Book, book_id)
    if book is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return book


def update_book(db: Session, book_id: int, data: BookUpdate) -> Book:
    """Apply a partial update. Only fields present in the request are changed; 404 if missing."""
    # raise NotImplementedError("update_book")
    # **********************************************
    book = get_book(db, book_id)
    # Exclude unset fields so non-provided fields are untouched
    update_data = data.model_dump(exclude_unset = True)
    for field, value in update_data.items():
        setattr(book, field, value)

    db.commit()
    db.refresh(book)
    return book
    # ******************************************************

def list_books(
    db: Session,
    q: Optional[str] = None,
    restricted: Optional[bool] = None,
    min_price: Optional[int] = None,
    max_price: Optional[int] = None,
    sort: Optional[BookSort] = None,
    limit: int = 20,
    offset: int = 0,
) -> BookPage:
    """Search the catalogue.

    Rules:
    - ``q`` matches title OR author, case-insensitive substring.
    - ``restricted`` filters exactly; ``min_price``/``max_price`` are inclusive.
    - Sorted by ``sort`` (title / price, ``-`` for descending) with ties broken by id;
      default order is id ascending.
    - ``total`` counts all matches before ``limit``/``offset`` are applied.
    """
    query = select(Book)
    # if q:
    #     query = query.where(Book.title.icontains(q, autoescape=True))
    
    # ***********************************************************************
    # Search filter across title OR auther (case - insensitive)
    if q:
        search_pattern = f"%{q.strip()}%"
        query = query.where(
            or_(
                Book.title.ilike(search_pattern),
                Book.author.ilike(search_pattern),
            )
        )

    # Boolean Filter
    if restricted is not None:
        query = query.where(Book.restricted == restricted)
    # TODO: min_price / max_price filters
    # Inclusive price range filters
    if min_price is not None:
        query = query.where(Book.price_cents >= min_price)
    if max_price is not None:
        query = query.where(Book.price_cents <= max_price)
    
    # Count total matching records before applying pagination (limit/offset)
    count_query = select(func.count()).select_from(query.subquery())
    total = db.scalar(count_query) or 0

    # TODO: apply ``sort``
    # Sorting Logic
    if sort == "title":
        query = query.order_by(Book.title.asc(), Book.id.asc())
    elif sort == "-title":
        query = query.order_by(Book.title.desc(), Book.id.asc())
    elif sort == "price":
        query = query.order_by(Book.price_cents.asc(), Book.id.asc())
    elif sort == "-price":
        query = query.order_by(Book.price_cents.desc(), Book.id.asc())
    else:
        query = query.order_by(Book.id.asc())

    # books = db.scalars(query.order_by(Book.id.asc()).limit(limit).offset(offset)).all()
    # total = len(books)

    # Apply pagination
    items = db.scalars(query.limit(limit).offset(offset)).all()
    # **************************************************************************

    return BookPage(
        items=list(items), 
        total=total, 
        limit=limit, 
        offset=offset,
    )
