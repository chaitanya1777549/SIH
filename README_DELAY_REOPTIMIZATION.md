# SIH26027 — Automatic Block Planning System
## Dynamic Train Delay Propagation & Corridor Re-Optimization Feature

---

### 1. Feature Overview & Problem Statement

In real-world Indian Railways corridor operations, trains frequently experience unexpected delays. When a train is delayed:
1. **Delay Propagation**: The delay doesn't just affect one station—it propagates downstream to subsequent block sections along the train's journey.
2. **Maintenance Conflicts**: The delayed train's new occupancy window may collide with an already allocated maintenance block (`Block`).
3. **Safety vs. Throughput Dilemma**:
   - If the conflicting maintenance block addresses a **critical, safety-threatening defect** (e.g. rail fracture, broken OHE line, signal interlocking defect), allowing train passage could cause a catastrophic derailment. The **block must be preserved**, and the conflicting train must be **diverted** or held.
   - If the conflicting maintenance block is **routine/low-criticality** maintenance (e.g. cess cleaning, routine lubrication, ballast profiling), train punctuality and commercial throughput take precedence. The maintenance block must be **revoked**, and immediately **rescheduled** into another slot (via an immediate shadow block on an existing window or the next free gap before its deadline).

This feature integrates this end-to-end operational intelligence into the COA Controller and Department interfaces.

---

### 2. Architecture & Decision Matrix

```
                      [ Train Delay Reported at Station ]
                                      │
                                      ▼
                        [ Propagate Downstream Delay ]
             (forecast_entry/exit updated in train_schedule)
                                      │
                                      ▼
                      [ Detect Temporal Conflicts ]
                (forecast window overlaps block ± 10m buffer)
                                      │
                 ┌────────────────────┴────────────────────┐
                 │                                         │
        [ Criticality >= 70 ]                     [ Criticality < 70 ]
      (or severity = 'critical')                 (Routine Maintenance)
                 │                                         │
                 ▼                                         ▼
         [ DIVERT TRAIN ]                          [ REVOKE BLOCK ]
    - train_schedule.status = 'diverted'      - block.status = 'cancelled'
    - Block PRESERVED                         - History logged: 'reoptimized_due_to_delay'
    - BLUE alert notification                 - RED notification to department
                                                           │
                                                           ▼
                                            [ ATTEMPT IMMEDIATE RESCHEDULING ]
                                                           │
                                      ┌────────────────────┴────────────────────┐
                                      │                                         │
                         [ Immediate Shadow Block? ]                     [ Next Free Gap? ]
                         - Same section, fits duration                   - Free gap with duration >= required
                         - planned_end <= required_by                    - planned_end <= required_by
                         - Attached as block_type='shadow'               - Allocated as block_type='primary'
                         - GREEN Notification                            - GREEN Notification
                                      │                                         │
                                      └────────────────────┬────────────────────┘
                                                           │ (if neither available)
                                                           ▼
                                               [ DEFER TO NEXT CYCLE ]
                                               - request.status = 'pending'
                                               - AMBER Notification to Controller
```

---

### 3. Database Updates

To cleanly support marking conflicting trains as diverted when maintenance is safety-critical, the `train_schedule` check constraint was expanded:

```sql
ALTER TABLE train_schedule DROP CONSTRAINT IF EXISTS train_schedule_status_check;
ALTER TABLE train_schedule ADD CONSTRAINT train_schedule_status_check 
  CHECK (status IN ('scheduled', 'running', 'completed', 'cancelled', 'diverted'));
```

All other tables (`blocks`, `block_requests`, `block_allocation_history`) already natively support:
- `Block.status`: `'cancelled'`, `'active'`
- `BlockAllocationHistory.reason`: `'reoptimized_due_to_delay'`, `'shadow_block_attached'`

---

### 4. API Reference

#### 4.1 Update Train Delay at a Station
- **Endpoint**: `POST /coa/trains/update-delay`
- **Description**: Updates the delay in minutes for a specific train at a given station and shifts forecast times for all downstream sections on the corridor.
- **Request Body**:
  ```json
  {
    "train_number": "12717",
    "service_date": "2026-09-05",
    "station_code": "AKP",
    "delay_minutes": 30
  }
  ```
- **Response**:
  ```json
  {
    "status": "success",
    "train_number": "12717",
    "service_date": "2026-09-05",
    "reported_station": "AKP",
    "delay_minutes": 30,
    "updated_sections_count": 9,
    "updated_sections": [ ... ]
  }
  ```

#### 4.2 Dynamic Corridor Re-Optimization
- **Endpoint**: `POST /coa/reoptimize`
- **Description**: Scans for conflicts between updated train timetables and active blocks, executing the intelligent decision matrix.
- **Request Body**:
  ```json
  {
    "service_date": "2026-09-05",
    "section_code": null,
    "criticality_threshold": 70
  }
  ```
- **Response**:
  ```json
  {
    "status": "success",
    "service_date": "2026-09-05",
    "conflicts_detected": 1,
    "trains_diverted_count": 0,
    "blocks_revoked_count": 1,
    "blocks_rescheduled_count": 1,
    "details": [
      {
        "conflict_type": "train_vs_block",
        "section_code": "DVD-AKP-DN",
        "train_number": "12717",
        "defect_code": "TMS-SEP-010",
        "criticality_score": 50,
        "decision": "block_revoked_and_rescheduled",
        "rescheduled_slot": {
          "type": "gap",
          "block_id": "9a38f712-...",
          "planned_start": "2026-09-05T03:00:00Z",
          "planned_end": "2026-09-05T05:10:00Z"
        },
        "notes": "Block revoked due to Train 12717 delay. Successfully rescheduled into next available free gap."
      }
    ],
    "notifications": [ ... ]
  }
  ```

#### 4.3 Unified One-Click Action
- **Endpoint**: `POST /coa/trains/delay-and-reoptimize`
- **Description**: Allows the COA controller to report a delay and immediately re-optimize the corridor in a single click.

#### 4.4 Live Notification Stream
- **Endpoint**: `GET /coa/notifications?department=TMS&limit=50`
- **Description**: Streams live corridor notifications categorized as `GREEN` (approved/rescheduled), `RED` (revoked/delayed), `BLUE` (diverted), and `AMBER` (deferred).
- **Endpoint**: `GET /departments/{dept}/notifications`
- **Description**: Dedicated endpoint for TMS, SMMS, and TDMS departmental dashboards.

---

### 5. Verification & Testing

To verify this feature:

1. **Run Automated Test Suite**:
   ```powershell
   .\myenv\Scripts\pytest.exe backend/tests/test_delay_reoptimize.py -v
   ```
2. **Run Interactive Verification CLI**:
   ```powershell
   .\myenv\Scripts\python.exe verify_delay_reoptimize.py
   ```
3. **Full System Regression Suite**:
   ```powershell
   .\myenv\Scripts\pytest.exe backend/tests/ -v
   ```
