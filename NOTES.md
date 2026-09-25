# Sanctum Sanctorum Bookstore — Backend Architecture & Notes

## 1. Deployment URL & Infrastructure
- **Live Application:** https://sanctum-sanctorum-bookstore-cerv.onrender.com
- **Interactive API Documentation (Swagger UI):** https://sanctum-sanctorum-bookstore-cerv.onrender.com/docs
- **Alternative Documentation (ReDoc):** https://sanctum-sanctorum-bookstore-cerv.onrender.com/redoc
- **Production Database:** Hosted PostgreSQL on Neon (Serverless Postgres via pooled connection string)
- **Local Testing Database:** SQLite (`sanctum.db`)
- **Runtime Environment:** Python 3.10+, FastAPI, SQLAlchemy 2.0 (`Mapped[]`), Pydantic v2, managed with `uv`

---

## 2. How to Test / Sign In
- To interact with the web dashboard, enter an existing Member ID in the **Sign in by member ID** input:
  - **Member ID:** `6` (Name: Vishal, Tier: Apprentice)
  - Alternatively, register a new member with any tier (e.g., `Master` to access restricted titles) 
  using the **Create member** form on the Members page or via `POST /members`.

---

## 3. Status of Requirements & Acceptance Tests
100% of acceptance tests pass without modifying files in `tests/`:

**Module 1 (Books):** Complete (67 / 67 tests passing). 
Normalized 13-digit modulo-10 ISBN validation, 
title/author whitespace sanitization, price range filtering, 
sorting with primary key tie-breaking, and selective `PATCH` updates.

**Module 2 (Members):** Complete (32 / 32 tests passing). 
Lowercase email validation with duplicate conflict rejection (HTTP 409), 
tier hierarchy checks, and lifetime statistics aggregation.

**Module 3 (Orders):** Complete (46 / 46 tests passing). 
Duplicate book and empty list validation (HTTP 422),
all-or-nothing stock reservation, tier discounts, bulk discounts ($\ge 10$ items), 
price freezing at order time, and `/pay` and `/cancel` state machines with stock rollback.

**Module 4 (Loans):** Complete (45 / 45 tests passing). 
Concurrency quotas per tier, overdue blocks, duplicate unreturned book blocks, 
dynamic read-time status evaluation, and return processing with late fees ($0.25/day capped at book price).

**Module 5 (Reports):** Complete (11 / 11 tests passing). 
`GET /reports/top-books` aggregating total copies sold across `paid` orders only, 
omitting unsold inventory, sorted by `copies_sold` DESC, `title` ASC.

---

## 4. Optional Feature Implemented: Added paginated `GET /members` 

**Motivation:** While the base specification only requires single-member retrieval (`GET /members/{id}`), 
inspecting registered users (or populating frontend directory tables) required a collection endpoint.

* **Implementation:** Followed the existing `BookPage` design pattern to introduce `GET /members?limit=20&offset=0`:
  - **Schema (`app/schemas.py`):** Added `MemberPage` containing `items: List[MemberOut]`, `total: int`, `limit: int`, and `offset: int`.
  - **Service (`app/services/members.py`):** Implemented `list_members` executing a count subquery 
  alongside sliced database retrieval ordered by `Member.id.asc()`.
  - **Router (`app/routers/members.py`):** Exposed `@router.get("", response_model=MemberPage)` 
  with defensive query parameter validation (`1 <= limit <= 100`, `offset >= 0`).

* **Verification:** Fully backwards-compatible; 
  preserves 202/202 passing acceptance tests while enabling direct member discovery at `/members`.

- **Total Test Suite:** **202 / 202 passed cleanly** via `uv run pytest`.

---

## 5. Architectural Decisions & Trade-Offs

1. **Strict 3-Tier Layering & Separation of Concerns.**
The application maintains explicit boundaries across every layer:
- **Validation Layer (`app/schemas.py`):** Pydantic v2 schemas sanitize and validate payloads before entering controller logic. 
  Modulo-10 ISBN-13 checksums, string trimming, email lowercasing, and explicit `null` rejection are enforced here, 
  returning HTTP 422 immediately on malformed input.
- **Controller Layer (`app/routers/`):** Thin routers manage path/query parameter parsing, HTTP status codes, 
  and dependency injection (`get_db`, `get_now`). Routers contain zero SQL queries, business transactions, or pricing formulas.
- **Domain & Service Layer (`app/services/`):** Encapsulates all domain invariants, atomic stock mutations, 
  discount arithmetic, tier access control, and reporting queries.
- **Persistence Layer (`app/models.py`):** Declarative SQLAlchemy 2.0 ORM persistence using 
  synchronous `Mapped[]` and `mapped_column()` annotations.

2. **Time Ingestion & Deterministic Testing.**
- Production logic strictly forbids direct calls to `datetime.now()`.
- All time-dependent calculations (order creation timestamps, 14-day loan horizons, overdue loan assessments, late fees, 
  and member lifetime statistics) ingest time through `now: datetime = Depends(get_now)` from `app/clock.py`.
- This enables Pytest fixtures in `conftest.py` to freeze and advance clock cycles deterministically without test flakiness.

3. **Dynamic Read-Time Status Evaluation for Loans.**
- Loan lifecycle statuses (`active`, `overdue`, `returned`) are calculated dynamically 
  upon read instead of persisting static database strings.
- This eliminates the need for background cron jobs or scheduled workers to synchronize database columns as time advances.
- Status resolves to `returned` if `returned_at` is populated, `overdue` if `now > due_at`, and `active` otherwise.
- Strict boundary compliance is enforced: at exactly `now == due_at`, `now > due_at` evaluates to `False`, 
  maintaining the loan as `active` with zero penalty fees.

4. **Data Integrity & Atomic Inventory Management.**
- **All-or-Nothing Stock Reservation:** In `create_order`, the service verifies shelf stock across all requested items 
  prior to decrementing inventory. If any item has insufficient stock, the transaction halts immediately and 
  raises HTTP 409 Conflict without modifying any book rows.
- **State Reversibility:** Cancelling a pending order (`POST /orders/{id}/cancel`) rolls back inventory 
  by adding item quantities back to the shelf. Returning a book (`POST /loans/{id}/return`) atomically 
  increments book stock within the return transaction.
- **Price Freezing:** Historical order line items freeze the book price as `unit_price_cents` at checkout time, 
  ensuring future price edits to books do not distort historical sales receipts.

5. **Multi-Database Engine Portability.**
- `app/db.py` dynamically inspects `SANCTUM_DATABASE_URL`:
  - When running locally against SQLite, it injects `connect_args={"check_same_thread": False}`.
  - When deployed on Render connecting to PostgreSQL (Neon), it strips SQLite-specific flags, 
    sets `pool_pre_ping=True`, and connects through binary drivers (`psycopg2-binary`, `psycopg-binary`) 
    to maintain resilient connection pooling.

---

## 6. Frontend Integration & Browser Diagnostics (`frontend/app.js`)

While grading focuses on backend acceptance tests, the client web UI was audited and verified for production:
- **Loan Return Button Fix:** The return loan function was previously isolated in an ES module scope, 
  leaving `onclick="returnLoan(...)"` unreachable from the global `window` context. 
  Binding `window.returnLoan = async function` resolved this, and adding explicit JSON headers alongside 
  dynamic table reloading ensured returns update instantly.
- **Local Chrome Extension Interference:** Local testing revealed that certain third-party browser extensions 
  injected overlay elements on `http://127.0.0.1:8000`, intercepting DOM click events. 
  Running in Chrome Incognito mode verified that the API was functioning properly. On Render over HTTPS, 
  the application runs isolated on its own origin without extension interference.

---

## 7. Spec Ambiguities & Observations

- **Mixed-Case Sorting:** `SPEC.md` noted that mixed-case title sorting is unspecified across databases 
  (SQLite sorts uppercase before lowercase by default, whereas PostgreSQL collation rules typically treat them case-insensitively). 
  In `app/services/books.py`, sorting adheres to standard database collation order, which cleanly passes all acceptance fixtures.
- **Missing Loan Model Columns:** The initial `Loan` ORM definition lacked `due_at`, `returned_at`, and `late_fee_cents`. 
  Adding these required dropping stale local `sanctum.db` files so SQLAlchemy could recreate the full schema cleanly.

---

## 8. AI Usage & Engineering Workflow

AI collaboration was used throughout this project as a developer productivity and 
diagnostic tool—analogous to a pair programmer for rubber-duck debugging, 
cross-dialect configuration checks, and fast root-cause analysis. 

The core domain logic, service-layer transactions, invariant validations, 
and RESTful API structures were implemented manually 
to adhere strictly to `SPEC.md` and the 3-tier layering requirements.

1. **Conceptual Verification & Syntax Alignment.**
-  **SQLAlchemy 2.0 Declarative Typing:** Used AI to verify synchronous declarative annotations 
  (`Mapped[]` and `mapped_column()`) under SQLAlchemy 2.0 to ensure relational integrity without 
  runtime attribute-mapping warnings.
  **Pydantic v2 Serialization Standards:** Verified idiom changes in Pydantic v2, 
  employing `@field_validator` and `@model_validator(mode="after")` over deprecated v1 patterns to enforce 
  explicit null rejection and strict ISBN modulo-10 validation at the boundary.

2. **Concrete Debugging & Root-Cause Resolution.**
- **ORM Property Mutation Trap:** During Module 3 (`Orders`), an initial dict-unpacking assignment 
  raised `AttributeError: property 'line_total_cents' of 'OrderItem' object has no setter`. 
  AI was used to trace the trace log, confirming that `line_total_cents` was declared as a 
  read-only ORM `@property` rather than a table column. The solution was to keep the model computed on the fly 
  while letting Pydantic serialize it dynamically in response schemas.
- **Database Schema Drift in Local SQLite:** Adding `due_at`, `returned_at`, and `late_fee_cents` to `Loan` in Module 4 
  led to `sqlite3.OperationalError: no such column: loans.due_at`. 
  AI was used as a sounding board to verify that SQLAlchemy’s `create_all()` is non-destructive and 
  will not run ad-hoc migrations on an existing `sanctum.db` instance, 
  isolating the fix: purging the stale SQLite file to allow clean table re-creation.
- **FastAPI Signature Mismatch:** Quickly caught an argument bug in exception handling where custom service helpers 
  invoked `HTTPException(details=...)` instead of the required singular keyword argument `detail=...`.

3. **Production Environment & Multi-Dialect Portability.**
- **Dialect-Aware Engine Configuration:** Render deployment logs initially failed with 
  an `invalid connection option "check_same_thread"` startup crash. 
  Used AI to inspect dialect-level arguments between SQLite and managed PostgreSQL, 
  arriving at the clean conditional separation in `app/db.py` (applying SQLite thread flags only when `DATABASE_URL.startswith("sqlite")`, 
  while enabling `pool_pre_ping=True` and binary drivers on PostgreSQL).
- **Client-Side Event Diagnostics:** Used console output traces to diagnose why loan returns failed locally 
  in Google Chrome despite passing all backend tests. Confirmed that a third-party developer extension was intercepting 
  global DOM click events on `http://127.0.0.1:8000`, verified that the backend endpoint functioned properly 
  in isolated environments (Incognito / direct HTTP calls), and updated `frontend/app.js` to 
  expose `window.returnLoan` globally for full production reliability.