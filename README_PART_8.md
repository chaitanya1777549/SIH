# SIH26027 — Part 8: The COA Master Interface

## Overview

Part 8 delivers **The COA Master Interface** — the crown jewel of the AI-Powered Automatic Block Planning System for the Visakhapatnam (VSKP) to Vijayawada (BZA) 350 km corridor.

Operating directly on live Supabase PostgreSQL data via SQLAlchemy 2.0 and integrated with React 18, Vite, Tailwind CSS, and D3, the COA Master Interface unifies all three railway engineering departments (**TMS Track**, **SMMS Signal**, **TDMS Traction/OHE**) under a single central operational cockpit.

---

## Key Features & Architecture

```
                                    +-------------------------------------------------------------+
                                    |                 COA Master Control Cockpit                  |
                                    +-------------------------------------------------------------+
                                     /             |              |             |               \
                                    /              |              |             |                \
                     +-------------+  +------------+  +-----------+  +----------+  +--------------+
                     | Track Map   |  | D3 Gantt   |  | Tabular   |  | Shadow   |  | Emergency    |
                     | 24h Scrubber|  | Timeline   |  | Records   |  | Piggyback|  | EOC Console  |
                     +-------------+  +------------+  +-----------+  +----------+  +--------------+
                            |                |              |             |               |
                            +----------------+--------------+-------------+---------------+
                                                            |
                                           +--------------------------------+
                                           |  FastAPI + SQLAlchemy 2.0 ORM  |
                                           +--------------------------------+
                                                            |
                                           +--------------------------------+
                                           |   Live Supabase PostgreSQL     |
                                           +--------------------------------+
```

### 1. Interactive Corridor Track Diagram Map (`CorridorTrackMap.tsx`)
- **12 Sequential Stations**: VSKP (km 0) $\to$ DVD $\to$ AKP $\to$ TUNI $\to$ ANV $\to$ SLO $\to$ APT $\to$ RJY $\to$ NDD $\to$ TDD $\to$ EE $\to$ BZA (km 350).
- **Dual-Track Schematic**: Explicit UP and DN track alignments across all 22 block sections.
- **24-Hour Time Scrubber**: Continuous slider from `00:00` to `23:59` with Play/Pause animation ($5\times$ real-time simulation).
- **Live Train Occupancy Badges**: Train icons moving along sections at the selected time, color-coded by on-time (blue) vs. delayed (rose) status.
- **Active Block Possession Overlays**: Sections under active primary maintenance render amber glows; sections with active shadow piggybacks render dual-hued purple rings.

### 2. D3 / SVG 24-Hour Gantt Timeline View (`GanttTimeline.tsx`)
- **22 Corridor Section Rows**: Vertically stacked in corridor sequence order with track badges (`UP` / `DN`) and section mileage.
- **24-Hour Horizontal Time Axis**: Complete timeline ruler marking every hour from `00:00` to `24:00`.
- **Certified Free Gap Highlight Zones ($\ge 60$ min)**: Green grid-patterned windows indicating certified collision-free slots between train paths.
- **Multi-Layer Possession & Movement Rendering**:
  - **Train Paths**: Blue/cyan bars spanning `forecast_entry` to `forecast_exit`, turning rose if delayed.
  - **Primary Maintenance Blocks**: Solid amber blocks (`#d97706`) with department badge and defect ID.
  - **Shadow Blocks**: Diagonal-hatched purple blocks (`#9333ea`) rendered directly within parent possessions.
- **Interactive Tooltip**: Hovering over any element reveals complete operational metadata (scheduled vs. forecast times, delay minutes, ML criticality scores).

### 3. Operational Records Tabular View (`TabularView.tsx`)
- **Sub-Tab Switcher**: Seamlessly toggle between **Corridor Blocks** and **Train Timetable**.
- **Corridor Blocks View**: Filter by block type (`Primary` vs `Shadow`) and department (`TMS`, `SMMS`, `TDMS`), showing planned start/end, duration, defect codes, and ML criticality scores.
- **Train Timetable View**: Filter by on-time vs. delayed movements, displaying scheduled vs. forecast times and real-time station delays.
- **Instant Full-Text Search**: Filter by section code, train number, or defect description in real time.

### 4. 1-Click Shadow Block Piggyback Center (`ShadowApprovalPanel.tsx`)
- **Multi-Department Co-Possession**: Scans all active primary blocks to discover pending maintenance defects on the exact same block section.
- **Zero-Delay Fit Analysis**: Displays window fit ratio progress bars (e.g. `100m needed / 180m primary window = 56% consumed`).
- **1-Click Actions**:
  - **Approve & Attach**: Atomically creates child shadow block, updates defect status to `allocated`, and dispatches a green approval notification to the concerned department.
  - **Discard**: Dismisses the recommendation and dispatches a red notification to the originating department.

### 5. Emergency Operations Center (EOC) (`EmergencyOperationsCenter.tsx`)
- **Incident Intake**: Rapid modal to report critical track fractures, signal cable cuts, or OHE sag incidents.
- **Heuristic Action Recommendation**: Automatically advises `HOLD`, `DIVERT`, `BLOCK`, or `NOTIFY` with explainable justification.
- **4-Option Decision Matrix**:
  1. *Option A: Immediate Emergency Block* (trains held / regulated).
  2. *Option B: Shadow Piggyback* (if existing block viable).
  3. *Option C: Regulated Single Train Window* (tested against sustainable defect safety deadline).
  4. *Option D: Divert / Caution Order* (speed restriction 20 km/h).
- **Sustainable Deadline Enforcement**: Automatically flags options that exceed the defect's sustainable safety limit.
- **Closed-Loop Safety Release Lifecycle**: 4-step stepper advancing from `confirmed` $\to$ `repairing` (ground crew active) $\to$ `safety_confirmed` (track certified safe) $\to$ `released` (corridor reopened).

### 6. Cascading Delay Simulation & Re-Optimizer (`DelayReoptimizeModal.tsx`)
- Senior controller selects train number, station, and injected delay minutes (e.g. $+45$ min).
- Downstream cascade propagation updates all subsequent station calls.
- Detects conflicts with active maintenance blocks and executes two-tier resolution:
  - *High Criticality ($\ge 70$)*: Train is diverted; maintenance block preserved.
  - *Normal/Low Criticality ($< 70$)*: Block is revoked and rescheduled into a free gap.

### 7. Google OR-Tools CP-SAT Optimizer (`OptimizerRunModal.tsx`)
- Triggers the full mathematical constraint solver for corridor block requests over configurable horizons.
- Solves multi-track non-overlapping constraints, headway safety buffers, and ML-weighted objective functions.

---

## Live Execution & Verification

### Running the Application

1. **FastAPI Backend**:
   ```powershell
   .\myenv\Scripts\uvicorn.exe backend.main:app --host 127.0.0.1 --port 8000
   ```
   API Docs: `http://127.0.0.1:8000/docs`

2. **Frontend React Application**:
   ```powershell
   cd frontend
   npm run dev -- --host 127.0.0.1
   ```
   Interface URL: `http://127.0.0.1:5173/`

### Automated Test Suite
Run all 41 end-to-end tests:
```powershell
.\myenv\Scripts\pytest.exe backend/tests/ -v
```
**Result**: `41 passed in 136s (100% success rate)`
