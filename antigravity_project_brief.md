# SIH26027 — AI-Powered Automatic Block Planning — Build Brief

Presentation date: **September 7, 2026**. This is a hackathon prototype, not a production system — prioritize a working, demoable core over completeness anywhere the two conflict.

## 0. How to use this document

This is the complete spec for everything still left to build. A separate file, `database_schema_reference.sql`, contains the exact, verbatim structure of the live Supabase database — every table, column, constraint, and index already created. **Attach or paste that file into this project's context before starting.** Do not redesign, rename, or restructure anything in it. Every instruction below assumes those tables exist exactly as written there.

The live database also already contains real seed data not shown in the schema file: a real Visakhapatnam–Vijayawada corridor (12 stations, 22 directional block sections), 29 trains with a full September 2026 timetable (~7,964 `train_schedule` rows), and 48 real department defect/maintenance records across `tms_defects`/`smms_defects`/`tdms_defects`. Query the live database to see actual examples — do not assume or invent what this data looks like.

**One pending migration must be run first**, if it hasn't been already: the SQL in `database_schema_reference.sql`'s last section (`blocks.block_type`, `blocks.parent_block_id`) adds shadow-block support. Confirm this ran before building anything that touches shadow blocks.

## 1. Tech stack (fixed, do not substitute)

- **Backend**: FastAPI (Python), connecting to the existing Supabase Postgres database via `psycopg2` or SQLAlchemy.
- **Optimizer**: Google OR-Tools CP-SAT, wrapped inside FastAPI endpoints (not a standalone script — every optimizer run must be triggerable over HTTP).
- **Frontend**: React + TypeScript, Tailwind CSS for UI, D3.js for the custom visualizations (track map, timeline), Framer Motion for animation/transitions.
- **ML criticality scorer**: scikit-learn (gradient-boosted trees), a separate small service or module the FastAPI backend calls.
- **Speech-to-text**: Whisper large-v3 via Groq's free tier API.
- **NL extraction**: an LLM (Qwen or gpt-oss class model) prompted to return strict JSON matching the defect schema.

## 2. What already exists (do not rebuild)

- Full Supabase schema: `stations`, `tracks`, `block_sections`, `trains`, `train_schedule`, `tms_defects`/`smms_defects`/`tdms_defects`, `block_requests`, `blocks`, `block_allocation_history`, `emergency_incidents`.
- Real corridor + train data for September 2026, as described above.
- 48 real defect/maintenance records, most still `status='pending'`/`'open'`, none yet turned into `block_requests` and none yet allocated.
- A working, tested reference implementation of the CP-SAT allocation logic (gap computation + solve + write-back + shadow-block attachment) — use it as the algorithmic reference for the FastAPI version, don't reinvent the approach from scratch.

## 3. Build order

### Phase A — FastAPI backend, wrapping the optimizer

Build a FastAPI service with, at minimum:

- `POST /coa/optimize` — body: `{start_date, end_date}`. Runs the full CP-SAT allocation pass over all currently `pending` `block_requests` within that horizon: fetch pending requests, fetch train occupancy (`train_schedule.forecast_entry/forecast_exit`), fetch existing active blocks, compute free gaps per section (pad every occupied interval by a safety buffer, e.g. 10 minutes, before computing gaps), solve with CP-SAT (maximize total scheduled `criticality_score`, respecting no-overlap per section and each request's deadline), write results to `blocks` + `block_allocation_history`, flip `block_requests.status` to `'allocated'`, and mirror that status onto the originating defect row. Returns a summary: how many requests were scheduled vs. left pending, and the list of new allocations.
- `POST /coa/shadow-check` — given a specific `block_id`, find other still-`pending` requests on the same section whose duration fits inside that block's window and whose deadline still holds; return candidates (don't auto-attach — see the approval flow in Phase E).
- `GET /coa/blocks?date=` — all blocks (primary and shadow) active on a given date, joined with section, department, and defect info, for the map/timeline/table views.
- `GET /coa/trains?date=` — all train movements for a given date, per section, for the map view.
- `GET /departments/{dept}/defects` — a department's own defect list with current status.
- `POST /departments/{dept}/defects` — create a new defect record (used by both the manual form and the NL-intake flow after parsing).
- Emergency-mode endpoints as specified in section 6 below.

### Phase B — Allocate the existing 48 defects (one-time batch)

Not every defect needs a block. Before running the optimizer:

1. Review the 48 existing defect records. Those with `requires_track_block`/`requires_signal_block`/`requires_power_block = true` are candidates; the rest never get a `block_requests` row at all.
2. Among the candidates, not all need to happen this month — some (e.g. low-severity `scheduled_maintenance` with a `required_by` well into next month, or low-criticality items with no near-term deadline) can legitimately stay `pending` and simply not be scheduled in this run, or be explicitly deferred. Use judgment based on `severity`, `work_category`, and `required_by` — don't force every eligible defect into a `block_requests` row if it doesn't make sense to plan it yet.
3. For the ones that should be planned now: create the `block_requests` rows (copying `criticality_score`, `required_by`, `estimated_duration_min`, block-type flags from the defect at that moment — a snapshot, not a live reference).
4. Run `POST /coa/optimize` over the September horizon and inspect the results before moving on. This is your first real end-to-end proof the system works — verify it before building anything else on top.

### Phase C — Criticality scoring model (build this with full explainability — the person operating this needs complete understanding and control of it, not a black box)

No historical outcome data exists to train a real supervised model on (no past defects paired with what actually happened if ignored) — so build it this way, and explain each step clearly as you go:

1. **Define a scoring formula by hand first**, encoding domain judgment explicitly, e.g.:
   `score = 35% x severity + 25% x urgency(time until required_by) + 20% x section_traffic_density + 10% x section_recurrence_count (how many other open defects, any department, on the same section recently) + 10% x whether a block is required`.
   `section_traffic_density` should be computed from real `train_schedule` counts per section — this is what actually represents "impact on asset availability" from the PS. `section_recurrence_count` should be computed from real defect counts. Weights are a judgment call — document them clearly so they can be explained and defended.
2. **Generate a large synthetic training set** by sampling realistic combinations of these features across their plausible ranges and labeling each with the formula above plus a small amount of random noise (so the model isn't just memorizing a deterministic function).
3. **Train a scikit-learn `GradientBoostingRegressor` (or `RandomForestRegressor`)** on that synthetic set — not a neural network; this data size and shape doesn't need one, and a tree model gives interpretable `feature_importances_` for free.
4. **Validate against the 48 real defect records** as a held-out sanity check — the trained model's scores should roughly track what the hand-written formula would say for real cases. Report this comparison clearly.
5. **Expose it as a function** the backend calls whenever a defect is created: `predict_criticality(features) -> score`. This becomes the only thing that changes in the pipeline — `block_requests.criticality_score` still gets snapshotted from the defect exactly as before, just sourced from this model instead of a fixed/manual number.

Document the whole pipeline (formula, synthetic data generation, training script, feature importances, validation results) somewhere the person can review and understand fully — this must not be a black box.

### Phase D — Live pipeline for new defects

Once Phase C is integrated, a new defect (from any department, via manual form or NL intake) triggers, in order:

1. Criticality score assigned by the model (Phase C).
2. If it requires a block, create a `block_requests` row and attempt a normal CP-SAT allocation pass (check `/coa/optimize` logic against current free gaps first).
3. If no normal slot is found, check whether a **shadow block** is possible (an existing block on the same/nearby section it can piggyback on).
4. If neither works and the score/deadline indicate genuine urgency, escalate to **Emergency Mode** (section 6).

## 4. Frontend — three department interfaces

Each department (TMS, SMMS, TDMS) gets its own small, focused interface:

- A list/dashboard of that department's own defects and their current status (open, requested, allocated, resolved), pulled live from the backend.
- A "report new issue" form matching the defect schema fields, plus a prominent, visually distinct **voice/NL intake** button (see section 7).
- A live notification area: when COA approves/creates a block for one of their requests, or resolves a shadow-block or emergency-block decision affecting them, show it as a clear **green (approved) or red (declined/rejected)** message/banner in that department's interface.
- Approve/discard actions for shadow-block or emergency-option proposals happen on the COA side (section 5), but the *result* of that decision must appear back here, in the originating department's interface, in that same green/red language.

## 5. Frontend — the COA interface (the heart of the project)

This is the main event — it needs to make the entire system legible at a glance, to someone with no technical background, not just function correctly.

**Track/corridor map view**: a large, visual, map-like representation of the Visakhapatnam-Vijayawada corridor — stations as recognizable nodes (symbols/emoji-style icons are welcome, e.g. a station icon, a train icon), sections as connecting lines, with:
- A day selector — changing the day re-queries `GET /coa/trains?date=` and `GET /coa/blocks?date=` and updates which trains and blocks are shown on the map for that specific day, live from the database, not hardcoded.
- Trains shown moving through sections at their scheduled/forecast times for the selected day.
- Blocked sections shown with a clear red line/highlight, with the block's time window visible on hover or inline.
- Zoom in/out on the corridor.

**Timeline view**: a Gantt-style chart (D3) of all sections against time, showing every block (primary and shadow, visually distinguished) and train movement for the selected day/week — this is where someone can see conflicts and allocations at a glance across the whole corridor, not just one section.

**Tabular view**: a plain table cross-referencing block, defect, department, time window, and section, and a second table of trains, section, and time, for anyone who wants the precise data rather than the visual.

**Pending requests panel**: every `block_requests` row still `pending` shown as a clear "awaiting allocation" card. When the backend determines a shadow-block opportunity exists for one, surface it as a specific, actionable proposal (not just a status change) that the controller can approve or discard with a single click — approving/discarding should immediately trigger the green/red notification back to the originating department's interface (section 4).

**Emergency panel**: see section 6 — this needs its own clearly separated, urgent-feeling space in the COA interface, not buried among routine pending requests.

Use Framer Motion for meaningful transitions (a block appearing on the map after allocation, a pending card moving to allocated, an emergency option being selected) — motion should communicate state change, not just decorate.

## 6. Emergency Mode — complete flow and the multi-option decision UI

Full flow, matching exactly what's already been designed at the database level (`emergency_incidents` table, `block_requests.is_emergency`):

```
Defect detected
  -> Create emergency incident
  -> Automatically identify affected track/section/assets
  -> Check current & upcoming trains
  -> Detect conflicts with trains + existing blocks
  -> Analyze possible actions
  -> Recommend best action (Hold / Divert / Block / Notify)
  -> Controller reviews & confirms
  -> Automatically notify concerned departments
  -> Defect repair
  -> Safety confirmation
  -> Emergency block released
```

The "analyze possible actions" and "recommend best action" step is a rule-based heuristic (if a fast-enough gap exists, recommend Block; if not, recommend Hold/Divert), not a second CP-SAT model — keep this simple and explainable, not another optimizer.

**When the recommended/chosen action is "Block," the controller must be shown multiple concrete options to choose between, not a single answer.** Example, matching exactly what's wanted: TMS requests an emergency 2-hour block as soon as possible. The backend should evaluate multiple candidate windows and present each with its real trade-offs computed from actual data, e.g.:

- **Option 1**: Block 2:00-4:00 PM — 3 trains diverted/delayed, X minutes of total delay caused, requires a full new resource allocation.
- **Option 2**: Block 8:00-10:00 PM — 5 trains affected, Y minutes of delay, but a shadow-block opportunity exists (another department already has a block allocated in that window on the same section), reducing extra resource allocation and maximizing overall asset availability.

Each option's numbers (trains affected, delay minutes, shadow-block availability) must be computed live from `train_schedule` and `blocks`, not fabricated — this is the same gap/conflict logic as the normal optimizer, just applied to a short list of candidate emergency windows instead of solved as one big CP-SAT problem. Present these as clear, comparable cards in the COA interface; the controller picks one with a single click, which then creates the actual `block_requests`/`blocks` rows for the chosen option and triggers notification back to the requesting department (green confirmation) — and implicitly, the unchosen option's implications never happen.

## 7. Natural-language / voice defect intake

Pipeline: operator speaks (or types) a report in a department's interface -> audio sent to **Whisper large-v3 via Groq's free tier API** for transcription -> resulting text sent to an LLM (Qwen or gpt-oss class) with a tightly constrained prompt instructing it to return **strict JSON only**, matching the defect schema fields exactly (`defect_type`, `description`, `severity`, `work_category`, location text, urgency indication, estimated duration) -> location text gets matched to an actual `block_section_id` using the real corridor's known station-to-station distances (a deterministic lookup, not another LLM guess) -> show the operator a confirmation preview of the parsed fields before saving -> on confirm, insert as a normal defect record via `POST /departments/{dept}/defects`, tagged with its input source. This exists specifically so someone with no technical background can report an issue in plain language and have it become a correctly structured record.

## 8. Non-negotiable constraints

- Do not redesign or rename any existing table or column.
- Do not have any component write directly to `blocks` except through the optimizer/emergency-decision logic — never let the frontend or a manual form insert a block directly.
- `block_requests.criticality_score` is always a snapshot taken at request-creation time, never a live reference back to the defect.
- Every block allocation, shadow attachment, and emergency decision must produce a row in `block_allocation_history` — this table is the audit trail and the source of the explainability the project depends on.
- Shadow blocks and emergency blocks are not a third table — they use the existing `blocks` table with `block_type`/`parent_block_id`, and `emergency_incidents` respectively, exactly as already designed.

## 9. Deliverable checklist

- [ ] FastAPI backend with all endpoints in section 3
- [ ] Phase B batch allocation run against the real 48 defects, verified
- [ ] Criticality model built, documented, and integrated (Phase C), fully explainable
- [ ] Live new-defect pipeline (Phase D)
- [ ] Three department interfaces (section 4)
- [ ] COA interface: map, timeline, table, pending panel, emergency panel (section 5)
- [ ] Emergency mode full flow + multi-option decision UI (section 6)
- [ ] Voice/NL intake (section 7)
- [ ] Green/red approval notifications flowing back to department interfaces
