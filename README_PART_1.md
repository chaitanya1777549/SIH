# SIH26027 — Automatic Block Planning System
## Part 1: Backend Foundation, Schema Integration & Core APIs (SQLAlchemy Edition)

---

### 1. Executive Summary & What Was Built

In **Part 1**, we constructed a production-grade **FastAPI backend** powered by **SQLAlchemy 2.0 ORM** connecting directly to the live Supabase PostgreSQL database. This layer bridges the underlying corridor database with the upcoming OR-Tools CP-SAT optimizer (Part 2), ML models (Part 4), emergency engine (Part 5), and React interfaces (Parts 7 & 8).

Key accomplishments in Part 1:
- **SQLAlchemy 2.0 Engine & Session Management (`backend/database.py`)**:
  - Configured `create_engine` with connection pooling (`pool_size=5`, `max_overflow=10`, `pool_pre_ping=True`, `pool_recycle=300`) and TCP keepalive configurations for Supabase connection pooling.
  - Implemented `get_db` generator dependency yielding SQLAlchemy `Session` instances for FastAPI dependency injection with clean disposal.
  - Created `check_db_health()` verifying database round-trip latency and live row counts via SQL execution.
- **Declarative ORM Models (`backend/models.py`)**:
  - Mirrored all 12 tables from `database_schema_reference.sql` verbatim using SQLAlchemy declarative models (`Station`, `Track`, `BlockSection`, `Train`, `TrainSchedule`, `TMSDefect`, `SMMSDefect`, `TDMSDefect`, `BlockRequest`, `Block`, `BlockAllocationHistory`, `EmergencyIncident`).
  - Configured full foreign key relationships (`relationship()`) with forward/backward linkages.
- **High-Performance Eager Loading**:
  - Applied `joinedload` on relationships across corridor queries to eliminate N+1 latency over remote database poolers, dropping test execution time from 111s to **11s**.
- **Strict Pydantic Data Contracts (`backend/schemas.py`)**:
  - Built validation schemas matching database constraints, including enums for departments (`TMS`, `SMMS`, `TDMS`), severities (`low`, `medium`, `high`, `critical`), statuses, work categories, and input sources.
- **Department Defect Endpoints (`backend/routes/departments.py`)**:
  - `GET /departments/{dept}/defects` — Fetches defects for TMS, SMMS, or TDMS, enriched with block section and station names via SQLAlchemy ORM.
  - `POST /departments/{dept}/defects` — Allows departments to submit new defect reports with schema validation and fallback criticality scoring.
- **COA Corridor Monitoring Endpoints (`backend/routes/coa.py`)**:
  - `GET /coa/stations` — Returns all 12 stations ordered sequentially from Visakhapatnam (`VSKP`) to Vijayawada (`BZA`).
  - `GET /coa/sections` — Returns all 22 directional block sections with track details, lengths, and station linkages.
  - `GET /coa/trains?date=YYYY-MM-DD` — Fetches all train movements and timetable forecasts for any selected date.
  - `GET /coa/blocks?date=YYYY-MM-DD` — Fetches all corridor maintenance blocks (both primary and shadow) joined with defect and department information.
- **Automated Verification Suite (`backend/tests/test_part1.py` & `verify_part1.py`)**:
  - 8 automated `pytest` tests verified against the live Supabase PostgreSQL database.

---

### 2. Architecture & File Structure

```
FINAL/
├── backend/
│   ├── __init__.py
│   ├── database.py             # SQLAlchemy engine, SessionLocal, get_db & health check
│   ├── models.py               # SQLAlchemy Declarative ORM models for all 12 tables
│   ├── schemas.py              # Pydantic request/response models & corridor enums
│   ├── main.py                 # FastAPI application, CORS, and lifespan setup
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── coa.py              # Stations, sections, trains, and blocks query endpoints
│   │   └── departments.py      # TMS, SMMS, and TDMS defect reporting & query endpoints
│   └── tests/
│       ├── __init__.py
│       └── test_part1.py       # Pytest suite testing all Part 1 endpoints
├── verify_part1.py             # Standalone verification runner with formatted output
├── README_PART_1.md            # Complete Part 1 documentation and debugging guide
├── .env                        # Supabase PostgreSQL connection string
├── database_schema_reference.sql # Verbatim SQL schema reference
└── antigravity_project_brief.md  # Complete project build specification
```

---

### 3. How to Run the Backend Server

To start the FastAPI development server with hot-reloading:

```powershell
# From the project root directory (c:\Users\chait\Desktop\FINAL):
.\myenv\Scripts\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload
```

Once running:
- **Interactive Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **Alternative ReDoc UI**: [http://localhost:8000/redoc](http://localhost:8000/redoc)
- **Root Info Endpoint**: [http://localhost:8000/](http://localhost:8000/)
- **Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

### 4. API Reference & Usage Examples

#### A. Health Check
- **Endpoint**: `GET /health`
- **Description**: Verifies Supabase connectivity via SQLAlchemy, returning database status, round-trip latency, and live table counts.
- **Example Response**:
```json
{
  "status": "healthy",
  "database": {
    "status": "healthy",
    "latency_ms": 138.2,
    "counts": {
      "stations": 12,
      "block_sections": 22,
      "trains": 29
    }
  },
  "timestamp": "2026-09-04T10:41:00Z"
}
```

#### B. Corridor Stations
- **Endpoint**: `GET /coa/stations`
- **Description**: Returns all 12 stations in corridor sequence (`VSKP` -> `DVD` -> `AKP` -> `TUNI` -> `ANV` -> `SLO` -> `APT` -> `RJY` -> `NDD` -> `TDD` -> `EE` -> `BZA`).

#### C. Corridor Block Sections
- **Endpoint**: `GET /coa/sections`
- **Description**: Returns all 22 directional sections (e.g. `VSKP-DVD-DN`, `DVD-AKP-DN`, `BZA-EE-UP`), complete with track IDs, track codes, and kilometer lengths.

#### D. Train Movements for Date
- **Endpoint**: `GET /coa/trains?date=2026-09-04`
- **Description**: Retrieves timetable forecasts for all trains moving across corridor sections on that day.
- **Query Parameter**: `date` (format: `YYYY-MM-DD`, default: `2026-09-04`).

#### E. Corridor Blocks (Primary & Shadow)
- **Endpoint**: `GET /coa/blocks?date=2026-09-04`
- **Description**: Returns active maintenance blocks, including duration in minutes, block type (`primary` or `shadow`), parent block ID (if shadow), and linked defect details.

#### F. Department Defect Queries
- **Endpoint**: `GET /departments/{dept}/defects`
- **Path Parameter**: `dept` (`TMS`, `SMMS`, or `TDMS`)
- **Query Parameter**: `status` (optional: `open`, `requested`, `allocated`, `resolved`)

#### G. Reporting a New Defect
- **Endpoint**: `POST /departments/{dept}/defects`
- **Path Parameter**: `dept` (`TMS`, `SMMS`, or `TDMS`)
- **Example Request Payload**:
```json
{
  "block_section_id": "8f8daeb1-6571-482a-9cb8-ba31d45da859",
  "defect_type": "Rail Surface Flaw",
  "description": "Detected minor crack on UP line km 142.4",
  "severity": "high",
  "estimated_duration_min": 90,
  "work_category": "defect",
  "input_source": "manual",
  "requires_block": true
}
```

---

### 5. How to Run Tests and Verification

#### Running the Pytest Suite
```powershell
.\myenv\Scripts\pytest.exe backend/tests/test_part1.py -v
```
Expected output:
```
======================== 8 passed in 11.79s ========================
```

#### Running the Standalone Verification Script
```powershell
.\myenv\Scripts\python.exe verify_part1.py
```
This script tests each endpoint end-to-end and prints formatted status reports for stations, sections, train movements, active blocks, and department defect queues.

---

### 6. Troubleshooting & Debugging Guide

#### Issue A: `OperationalError: connection failed` or Supabase pooler drops
- **Root Cause**: The database URL in `.env` is either missing, corrupted, or network dropped.
- **Fix**: Check `c:\Users\chait\Desktop\FINAL\.env`. Verify `DATABASE_URL` is correct.
- **SQLAlchemy Pool Check**: Notice that `backend/database.py` includes `pool_pre_ping=True`, which automatically recycles dead connections.

#### Issue B: `DetachedInstanceError` in SQLAlchemy
- **Root Cause**: Accessing an ORM relationship outside the session scope when lazy loading is triggered.
- **Fix**: Relationships are configured with `joinedload()` in queries, ensuring all necessary parent-child models are eagerly fetched before the session closes.

#### Issue C: `Address already in use` (Port 8000 Conflict)
- **Root Cause**: Another process (or an earlier uvicorn instance) is listening on port 8000.
- **Fix**:
  ```powershell
  Get-NetTCPConnection -LocalPort 8000 | Select-Object OwningProcess
  # Or start uvicorn on an alternate port:
  .\myenv\Scripts\python.exe -m uvicorn backend.main:app --port 8001 --reload
  ```

---

### 7. Readiness for Part 2

With the SQLAlchemy refactoring complete, verified, and benchmarked:
- Clean, idiomatic SQLAlchemy models and dependency-injected sessions are active.
- Eager loading eliminates N+1 latency issues.
- The system is fully prepared to proceed to **Part 2: Google OR-Tools CP-SAT Optimizer Core & `/coa/optimize` Endpoint**.
