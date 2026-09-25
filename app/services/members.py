"""Member operations and tier helpers."""
from datetime import datetime
from typing import List

from fastapi import HTTPException, status
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.models import Member, MemberTier, Order, Loan
from app.schemas import MemberCreate, MemberStats

from app.schemas import MemberPage

# Tiers from lowest to highest; a member's rank is their index in this list.
TIER_ORDER: List[str] = [
    MemberTier.APPRENTICE.value,
    MemberTier.ADEPT.value,
    MemberTier.MASTER.value,
    MemberTier.SUPREME.value,
]

# Minimum tier allowed to buy or borrow restricted books.
RESTRICTED_MIN_TIER = MemberTier.MASTER.value

# ********************************************************************
def tier_at_least(tier: str, minimum: str) -> bool:
    """True if ``tier`` ranks at or above ``minimum``."""
    return TIER_ORDER.index(tier) >= TIER_ORDER.index(minimum)


def ensure_can_access_restricted(member: Member) -> None:
    """Raise 403 unless the member's tier may access restricted books."""
    if not tier_at_least(member.tier, RESTRICTED_MIN_TIER):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail=f"Restricted books require tier '{RESTRICTED_MIN_TIER}' or higher"
        )
# **************************************************************************

def create_member(db: Session, data: MemberCreate, now: datetime) -> Member:
    """Register a member.

    Rules: email (already stripped + lowercased) must be unique -> 409; created_at = now.
    """
    # ***********************************************************************
    # TODO: reject an email that is already in use with 409
    existing = db.scalar(
        select(Member)
        .where(func.lower(Member.email) == data.email.lower())
    )

    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Member with this email already exists",
        )
    member = Member(
        name=data.name, 
        email=data.email, 
        tier=data.tier.value if hasattr(data.tier, "value") else data.tier, 
        created_at=now,
    )
    # ************************************************************************
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


def get_member(db: Session, member_id: int) -> Member:
    """Return a member by id, or raise 404."""
    member = db.get(Member, member_id)
    if member is None:
        raise HTTPException(status_code=404, detail="Member not found")
    return member


def list_member_orders(db: Session, member_id: int) -> List[Order]:
    """All orders of a member ordered by id ascending; 404 if the member is missing."""
    get_member(db, member_id) #Throw 404 if missing
    return list(
        db.scalars(
            select(Order)
            .where(Order.member_id == member_id)
            .order_by(Order.id.asc()) #order members by ascending order
        )
    )


def get_member_stats(db: Session, member_id: int, now: datetime) -> MemberStats:
    """Summarize a member's activity.

    Rules:
    - 404 if the member is missing.
    - orders_paid / total_spent_cents consider only ``paid`` orders.
    - active_loans counts every unreturned loan (overdue ones included).
    - overdue_loans counts unreturned loans with now > due_at.
    - late_fees_cents sums late fees of returned loans.
    """
    # raise NotImplementedError("get_member_stats")
    # *********************************************************
    get_member(db, member_id) #Throw 404 if missing

    # 1.Paid order statistics
    paid_orders = db.scalars(
        select(Order)
        .where(Order.member_id == member_id, Order.status == "paid")
    ).all()
    orders_paid = len(paid_orders)
    total_spent_cents = sum(order.total_cents for order in paid_orders)

    # 2. Loan Statistics
    all_loans = db.scalars(
        select(Loan)
        .where(Loan.member_id == member_id)
    ).all()

    active_loans = sum(1 for loan in all_loans if loan.returned_at is None)
    overdue_loans = sum(
        1 for loan in all_loans if loan.returned_at is None and now > loan.due_at
    )
    late_fees_cents = sum(
        loan.late_fee_cents or 0 for loan in all_loans if loan.returned_at is not None
    )

    return MemberStats(
        member_id = member_id,
        orders_paid = orders_paid,
        total_spent_cents = total_spent_cents,
        active_loans = active_loans,
        overdue_loans = overdue_loans,
        late_fees_cents = late_fees_cents,
    )
    # *********************************************************

# Adding a function that calculates total rows in the members table and loads a paginated slice ordered by id ascending.
def list_members(db: Session, limit: int = 20, offset: int = 0) -> MemberPage:
    """Return a paginated list of members present in the database"""
    # 1. Count the total members present in the database
    total = db.scalar(select(func.count()).select_from(Member)) or 0

    # 2. Retrieve only the requested slice
    members = db.scalars(
        select(Member)
        .order_by(Member.id.asc())
        .limit(limit)
        .offset(offset)
    ).all()

    # Return the structured page
    return MemberPage(
        items = list(members),
        total = total,
        limit = limit,
        offset = offset,
    )