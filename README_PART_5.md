# SIH26027 — Automatic Block Planning System
## Part 5: Emergency Mode Engine & Multi-Option Decision Matrix (Section 6 & Phase D)

---

### 1. Executive Summary & What Was Built

In **Part 5**, we implemented the **Emergency Mode Engine and Multi-Option Decision Matrix** (`backend/emergency/`).

When critical, unexpected railway infrastructure defects occur (e.g. rail fractures, broken OHE catenary wires, signal interlocking dropouts), operations cannot wait for the routine daily or weekly optimization run. The Emergency Mode Engine provides:
1. **Rapid Incident Ingestion**: Tracks originating department (TMS, SMMS, TDMS) and automatically maps location to the affected corridor block section and tracks.
2. **Real-Time Train Conflict & Approach Analysis**: Scans live `train_schedule` forecasts to identify approaching trains within 60–120 minutes.
3. **Explainable Heuristic Action Recommendation**: Recommends **`hold`**, **`divert`**, **`block`**, or **`notify`** based on safety criticality and train proximity.
4. **Multi-Option Block Comparison Cards (No Fabricated Data)**:
   - Evaluates real options directly from `train_schedule` and `blocks`.
   - **Enforces Maximum Sustainable Defect Time**: Disqualifies shadow blocks or natural gaps that begin after the defect's safety tolerance.
   - Computes exact trade-offs: trains delayed, minutes of delay, train numbers, and resource impact.
5. **Controller Decision Confirmation**: Single-click approval creating an emergency block (`is_emergency=True`), writing an audit trail in `block_allocation_history`, and streaming live green/red/blue/amber notifications.
6. **Field Repair & Safety Release Lifecycle**: Structured governance progressing from field mobilization (`repairing`) to ultrasonic/electrical safety certification (`safety_confirmed`) to corridor reopening (`released`).

---

### 2. Emergency Incident Lifecycle

```
    [ Defect Detected / Reported ]
                 │
                 ▼
        [ Action Recommended ]  <─── Heuristic analysis of approaching trains
                 │
                 ▼
        [ Controller Decision ] ───> Hold / Divert / Notify / Block (Selects Option Card)
                 │
                 ▼
       [ Emergency Block Active ] ───> Atomically creates BlockRequest (is_emergency=True)
                 │                   and Block (status='active')
                 ▼
            [ Repairing ]       ───> Field maintenance team on track
                 │
                 ▼
       [ Safety Confirmed ]     ───> Field engineer certifies track geometry/safety
                 │
                 ▼
           [ Released ]         ───> Block marked 'completed'; corridor reopened
```

---

### 3. Heuristic Action Recommendation Matrix

| Proximity & Condition | Recommended Action | Operational Rationale |
| :--- | :--- | :--- |
| Train entering section in $\le 15$ min | **`HOLD`** | Hold approaching train at upstream station loop to avert immediate collision or derailment risk. |
| $> 2$ trains approaching within 60 min, alternate track available | **`DIVERT`** | Heavy corridor traffic; reroute commercial trains via loop or parallel line while mobilizing repair crew. |
| Track/Power/Signal isolation required; safe window feasible | **`BLOCK`** | Immediate track possession required. Candidate block options generated for officer review. |
| Off-track defect, minor wear, no line isolation needed | **`NOTIFY`** | Issue cautionary speed restriction (caution order) without line closure. |

---

### 4. Multi-Option Block Proposals & Sustainable Time Rules

When the action is or can be **`block`**, the engine evaluates multiple candidate options:

#### Strict Sustainable Time Enforcement
An emergency defect cannot wait indefinitely. Every candidate option (Shadow or Deferred Gap) is validated against the defect's **maximum sustainable time** (`required_by` or emergency deadline, e.g. $\le 4$ hours for safety-critical incidents). If a candidate block or gap starts *after* this deadline, it is **strictly disqualified** and never offered.

#### The 4 Option Architectures
1. **Option 1: Immediate Emergency Closure**
   - Starts immediately (+15 min).
   - Full line possession; halts or diverts any conflicting trains.
   - High operational impact, but guarantees zero delay to defect repair.
2. **Option 2: Targeted Single-Train Hold / Delay Trade-Off**
   - Examines approaching trains in the next 2 hours.
   - If holding or delaying a single train (e.g. Train 17239 by 20–35 min) unlocks an uninterrupted 90–120 min repair window, it is surfaced explicitly.
   - Gives the officer an surgical operational choice rather than shutting down the entire corridor.
3. **Option 3: Shadow Block Piggyback (Zero Additional Delay)**
   - Checks active primary blocks on the same section.
   - **Condition**: Must start *well before* the emergency defect's maximum sustainable deadline.
   - Consumes zero extra corridor capacity and causes zero additional train delays.
4. **Option 4: Earliest Sustainable Natural Gap**
   - Natural free gap between train movements occurring before the emergency deadline.
   - Zero train delays and clean scheduled execution.

---

### 5. API Reference

#### 5.1 Report Emergency Incident
- **Endpoint**: `POST /coa/emergency/incidents`
- **Request Body**:
  ```json
  {
    "source_system": "TMS",
    "block_section_id": "d5ebfbe6-4bf1-4d70-9899-d6408729da5d",
    "reported_text": "Emergency rail web shear detected at km 124/8.",
    "defect_type": "Rail Web Shear",
    "severity": "critical",
    "estimated_duration_min": 90
  }
  ```
- **Response**:
  ```json
  {
    "status": "success",
    "incident_id": "5811af29-...",
    "source_system": "TMS",
    "section_code": "VSKP-DVD-DN",
    "incident_status": "action_recommended",
    "recommended_action": "block",
    "recommendation_reason": "Track possession (BLOCK) recommended...",
    "options": [
      {
        "option_id": "opt-immediate",
        "label": "Option 1: Immediate Emergency Closure",
        "planned_start": "2026-09-04T11:01:00Z",
        "planned_end": "2026-09-04T12:31:00Z",
        "duration_min": 90,
        "trains_affected_count": 1,
        "affected_train_numbers": ["17239"],
        "total_delay_minutes": 15,
        "is_shadow": false,
        "resource_impact": "Full emergency maintenance crew required immediately.",
        "sustainable": true,
        "description": "Immediate line possession starting in 15m..."
      },
      {
        "option_id": "opt-single-train-hold",
        "label": "Option 2: Targeted Hold on Train 17239",
        "planned_start": "2026-09-04T11:06:00Z",
        "planned_end": "2026-09-04T12:36:00Z",
        "duration_min": 90,
        "trains_affected_count": 1,
        "affected_train_numbers": ["17239"],
        "total_delay_minutes": 20,
        "is_shadow": false,
        "resource_impact": "Holds Train 17239 at upstream loop line.",
        "sustainable": true,
        "description": "Targeted intervention: Hold Train 17239 by 20m..."
      }
    ]
  }
  ```

#### 5.2 Confirm Action / Select Option Card
- **Endpoint**: `POST /coa/emergency/incidents/{incident_id}/confirm`
- **Request Body**:
  ```json
  {
    "decision": "block",
    "selected_option_id": "opt-immediate",
    "notes": "Authorized emergency track possession by Chief Controller."
  }
  ```

#### 5.3 Advance Incident Lifecycle
- **Endpoint**: `POST /coa/emergency/incidents/{incident_id}/advance`
- **Request Body**:
  ```json
  {
    "target_status": "safety_confirmed",
    "notes": "Weld ultrasonic testing passed."
  }
  ```

---

### 6. Verification & Testing

```powershell
# 1. Run Emergency Mode unit & integration tests
.\myenv\Scripts\pytest.exe backend/tests/test_part5.py -v

# 2. Run standalone interactive CLI demonstration
.\myenv\Scripts\python.exe verify_part5.py

# 3. Run full regression test suite (Parts 1 to 5)
.\myenv\Scripts\pytest.exe backend/tests/ -v
```
