# SIH26027 — Automatic Block Planning System
## Part 6: Natural Language & Voice Defect Intake (Section 7 & Phase D)

---

### 1. Executive Summary & What Was Built

In **Part 6**, we implemented the complete **Natural Language & Voice Defect Intake Pipeline** (`backend/nl_intake/`).

In real railway operations, track patrolmen, signal technicians, and OHE maintenance staff communicate urgent issues using spoken walkie-talkie messages, voice memos, or quick informal text messages (e.g. *"severe rail fracture near Anakapalle towards Tuni around km 52, need 90 minutes right now"*). They do not have time or technical background to look up foreign key UUIDs or calculate corridor chainages.

Part 6 solves this by translating unstructured spoken or typed reports into fully qualified, verified, and scored railway defects through four specialized layers:
1. **Whisper large-v3 Speech-to-Text**: Converts operator audio files into high-accuracy transcripts using Groq's high-speed inference cloud (`whisper-large-v3` with fallback to `whisper-large-v3-turbo`).
2. **Constrained LLM Information Extraction**: Uses flagship open-weights intelligence (`openai/gpt-oss-120b` or `qwen/qwen3.8-27b` on Groq) with a strict JSON system schema to extract domain attributes (`defect_type`, `description`, `severity`, `work_category`, `estimated_duration_min`, `urgency_hours`, `direction`, `requires_block`).
3. **Deterministic Corridor Location Matcher (Zero LLM Hallucination)**: Deterministically resolves kilometer markers (`km 52`, `km 124/8`), station pairs (*"between Anakapalle and Tuni"*), and directional cues (*"towards Vijayawada" / DN*) into the exact PostgreSQL `block_section_id` using the real 350 km Visakhapatnam–Vijayawada corridor geometry.
4. **Interactive Confirmation Preview with ML Criticality Scoring**: Before inserting into the database, generates a complete operator draft showing the matched section, predicted ML score (via Phase C Gradient Boosting model), baseline comparison, and plain-English justification.
5. **Direct 1-Click Database Insertion**: On operator approval, seamlessly inserts into `tms_defects`, `smms_defects`, or `tdms_defects` tagged with `input_source='voice'` or `'nl_intake'`.

---

### 2. End-to-End Pipeline Architecture

```
   [ Operator Speaks / Audio Memo ] ──> POST /departments/voice-intake
                 │
                 ▼
     [ Groq Whisper large-v3 ]      ──> Accurate Text Transcription
                 │
                 ▼
   [ Operator Types Text (or Voice) ] ──> POST /departments/parse-defect
                 │
                 ▼
  [ Constrained LLM: gpt-oss-120b ]  ──> Strict JSON Schema Extraction
                 │
                 ▼
 [ Deterministic Corridor Matcher ]  ──> Mathematical Chainage & Station-Pair Match (Zero Hallucinations)
                 │
                 ▼
   [ Phase C ML Criticality Scorer ] ──> Computes Score (0-100) + Feature Contributions + Justification
                 │
                 ▼
   [ Operator Confirmation Preview ] ──> Human-in-the-loop review card
                 │
                 ▼
 [ POST /departments/{dept}/defects ]──> Atomic DB Insert (input_source='nl_intake' / 'voice')
```

---

### 3. Mathematical Corridor Geometry & Station Catalog

The Visakhapatnam to Vijayawada corridor spans **350.0 km** across 12 primary stations and 22 directional block sections:

| Sequence | Station Code | Station Name | Cumulative Chainage (km) | Outbound Down Section (DN) | Outbound Up Section (UP) |
| :---: | :---: | :---: | :---: | :---: | :---: |
| 1 | **VSKP** | Visakhapatnam | 0.0 km | `VSKP-DVD-DN` (17.0 km) | `DVD-VSKP-UP` (17.0 km) |
| 2 | **DVD** | Duvvada | 17.0 km | `DVD-AKP-DN` (16.0 km) | `AKP-DVD-UP` (16.0 km) |
| 3 | **AKP** | Anakapalle | 33.0 km | `AKP-TUNI-DN` (63.0 km) | `TUNI-AKP-UP` (63.0 km) |
| 4 | **TUNI** | Tuni | 96.0 km | `TUNI-ANV-DN` (17.0 km) | `ANV-TUNI-UP` (17.0 km) |
| 5 | **ANV** | Annavaram | 113.0 km | `ANV-SLO-DN` (37.0 km) | `SLO-ANV-UP` (37.0 km) |
| 6 | **SLO** | Samalkot Junction | 150.0 km | `SLO-APT-DN` (27.0 km) | `APT-SLO-UP` (27.0 km) |
| 7 | **APT** | Anaparti | 177.0 km | `APT-RJY-DN` (23.0 km) | `RJY-APT-UP` (23.0 km) |
| 8 | **RJY** | Rajahmundry | 200.0 km | `RJY-NDD-DN` (23.0 km) | `NDD-RJY-UP` (23.0 km) |
| 9 | **NDD** | Nidadavolu Junction | 223.0 km | `NDD-TDD-DN` (19.0 km) | `TDD-NDD-UP` (19.0 km) |
| 10 | **TDD** | Tadepalligudem | 242.0 km | `TDD-EE-DN` (48.0 km) | `EE-TDD-UP` (48.0 km) |
| 11 | **EE** | Eluru | 290.0 km | `EE-BZA-DN` (60.0 km) | `BZA-EE-UP` (60.0 km) |
| 12 | **BZA** | Vijayawada Junction | 350.0 km | Corridor Terminus | Corridor Origin |

#### How Deterministic Resolution Works
1. **Chainage Mapping**: If report mentions `"km 52"`, since $33.0 \le 52.0 \le 96.0$, it deterministically binds to `AKP-TUNI-DN` (or `TUNI-AKP-UP` if UP line specified).
2. **Telegraph Post Notation**: Parses `"km 124/8"` as $124 + \frac{8}{10} = 124.8\text{ km}$, matching `ANV-SLO-DN` ($113.0 \le 124.8 \le 150.0$).
3. **Station-Pairs**: Mentions of *"between Anakapalle and Tuni"* bind directly to adjacent interval `AKP-TUNI`.
4. **Directional Inferences**: Words like *"towards Vijayawada"*, *"down line"*, *"DN"* set direction to DN; *"towards Visakhapatnam"*, *"up line"*, *"UP"* set direction to UP.

---

### 4. Step-by-Step Swagger UI Testing Guide (`/docs`)

To test the system interactively and observe accurate performance:

#### Step 4.1: Start the Backend
```powershell
.\myenv\Scripts\uvicorn.exe backend.main:app --reload
```
Open your browser and navigate to **`http://127.0.0.1:8000/docs`**.

#### Step 4.2: Test Natural Language Parsing (`POST /departments/parse-defect`)
1. In Swagger UI, expand **`POST /departments/parse-defect`**.
2. Click **"Try it out"**.
3. In the Request body, paste this realistic operator report:
   ```json
   {
     "text": "Observed severe rail fracture near Anakapalle towards Tuni around km 52, needs urgent 90 minute block before 4 PM today.",
     "department": "TMS"
   }
   ```
4. Click **"Execute"**.
5. **Inspect the Response**:
   - `draft_defect.defect_type`: `"Rail Fracture"`
   - `draft_defect.section_code`: `"AKP-TUNI-DN"`
   - `draft_defect.severity`: `"critical"`
   - `draft_defect.estimated_duration_min`: `90`
   - `location_match.match_method`: `"station_pair"` or `"chainage_km"` (Confidence $\ge 0.95$)
   - `preview_criticality.predicted_score`: $\ge 88$ (`CRITICAL PRIORITY`)
   - `preview_criticality.justification`: Plain-English explanation showing Defect Severity as the dominant factor.

#### Step 4.3: Test Voice Audio Intake (`POST /departments/voice-intake`)
1. In Swagger UI, expand **`POST /departments/voice-intake`**.
2. Click **"Try it out"**.
3. Upload any audio recording (`.wav`, `.mp3`, `.m4a`, or `.webm`).
4. Click **"Execute"**.
5. **Inspect the Response**:
   - Returns `{ "status": "success", "transcription": "...", "detected_language": "en", "model_used": "whisper-large-v3" }`.

#### Step 4.4: Test 1-Click Voice to Defect Preview (`POST /departments/voice-intake-and-parse`)
1. In Swagger UI, expand **`POST /departments/voice-intake-and-parse`**.
2. Click **"Try it out"**.
3. Upload your audio recording, optionally select department (e.g. `TMS`).
4. Click **"Execute"**.
5. Returns the transcribed voice text PLUS the complete drafted defect card ready for confirmation!

#### Step 4.5: Confirm and Save the Defect
1. Copy the `draft_defect` JSON returned by step 4.2 or 4.4.
2. In Swagger UI, expand **`POST /departments/{department}/defects`**.
3. Select department `TMS`, paste the payload, and click **"Execute"**.
4. The defect is officially recorded in the database with status `open`, `input_source='nl_intake'` (or `'voice'`), and immediately triggers Phase C scoring and optimizer scheduling!

---

### 5. Curl & Python API Examples

#### Curl: Natural Language Parse
```bash
curl -X POST "http://127.0.0.1:8000/departments/parse-defect" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "OHE catenary wire sag noticed at km 124 near Samalkot, urgent 60 minute power block required.",
    "department": "TDMS"
  }'
```

#### Curl: Voice Intake Upload
```bash
curl -X POST "http://127.0.0.1:8000/departments/voice-intake" \
  -F "file=@memo.wav;type=audio/wav"
```

---

### 6. Verification & Automated Test Suites

```powershell
# 1. Run Part 6 unit & integration tests (7/7 passed)
.\myenv\Scripts\pytest.exe backend/tests/test_part6.py -v

# 2. Run standalone interactive CLI demonstration
.\myenv\Scripts\python.exe verify_part6.py

# 3. Run full regression test suite across ALL parts (41/41 passed)
.\myenv\Scripts\pytest.exe backend/tests/ -v
```

---

### 7. Files Created in Part 6

| File | Purpose |
| :--- | :--- |
| `backend/nl_intake/corridor_matcher.py` | Mathematical corridor location matcher (stations, chainage km, directions). |
| `backend/nl_intake/transcriber.py` | Audio transcription service using Groq Whisper large-v3. |
| `backend/nl_intake/extractor.py` | Constrained LLM JSON extractor (`openai/gpt-oss-120b`). |
| `backend/nl_intake/service.py` | Unified intake service uniting Whisper, LLM, matcher, and ML scoring. |
| `backend/routes/nl_intake.py` | API endpoints: `/voice-intake`, `/parse-defect`, `/voice-intake-and-parse`. |
| `backend/tests/test_part6.py` | Automated test suite (7 comprehensive test cases). |
| `verify_part6.py` | Interactive verification script with live Groq execution. |
| `README_PART_6.md` | Full documentation and Swagger UI step-by-step testing guide. |
