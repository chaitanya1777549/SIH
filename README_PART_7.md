# SIH26027 — Part 7: Three Department Interfaces (TMS, SMMS, TDMS)

## Overview

Part 7 introduces the modern, production-grade departmental web application for Indian Railways field engineers and section controllers across the 350 km Visakhapatnam (VSKP) – Vijayawada (BZA) corridor.

The application unifies the three core maintenance departments:
- **TMS (Track Management System)** — Engineering / Permanent Way (P-Way), track geometry, rails, sleepers, ballast, welds.
- **SMMS (Signal & Telecom Maintenance Management System)** — Points, point machines, signals, track circuits, axel counters, relays.
- **TDMS (Traction Distribution Management System)** — 25 kV AC OHE, catenary, contact wire, droppers, neutral sections, substations.

---

## Key Architecture & Technology Stack

| Layer | Technologies Used | Key Responsibilities |
|---|---|---|
| **Frontend Framework** | React 18, Vite 5, TypeScript | Reactive, strongly-typed component architecture |
| **Styling & Icons** | Tailwind CSS 3.4, Lucide React | Modern dark-themed railway operations console |
| **Motion & Polish** | Framer Motion | Smooth tab transitions, visualizer pulses, score animations |
| **Audio Capture** | HTML5 MediaRecorder & Web Audio API | Live audio recording with duration timer & waveform pulses |
| **Reverse Proxy** | Vite Dev Server Proxy | Transparent proxying to FastAPI on `http://127.0.0.1:8000` |
| **Backend Integration** | FastAPI, SQLAlchemy 2.0, Supabase PostgreSQL | Direct database access, Whisper voice intake, ML scoring |

---

## Key Features Implemented

### 1. Unified Department Switcher
Operators can seamlessly switch between **TMS**, **SMMS**, and **TDMS** tabs. Each department features custom accent branding:
- **TMS**: Emerald/Green railway engineering theme (`#10b981`).
- **SMMS**: Amber/Yellow signaling & interlock theme (`#f59e0b`).
- **TDMS**: Cyan/Blue 25 kV OHE electrical theme (`#06b6d4`).

### 2. Live Operations Summary Badges
- **Supabase DB Live Connection Status**: Automatic heartbeat ping displaying green connection status and latency.
- **Total Open Defects**: Real-time counter of pending maintenance work.
- **Critical / Urgent Defects**: Highlighted counter of high-severity defects needing immediate intervention.
- **Average Criticality Score**: Live Phase C ML scoring average across open tasks.

### 3. Real-Time COA Notification Stream
- Displays incoming notifications generated during COA block scheduling and downstream train delay re-optimizations:
  - **GREEN Cards**: Work allocated or rescheduled to next optimal window.
  - **RED Cards**: Block revoked, deferred, or declared emergency due to conflicting train delays.

### 4. Rich Searchable & Filterable Defect Table
- Instant search bar filtering by defect code, description, section code, or defect type.
- Severity filters: `All`, `Critical`, `High`, `Medium`, `Low`.
- Status filters: `All`, `Open`, `Requested`, `Allocated`, `Resolved`.
- Duration display and block requirement tags (`Requires Track Block`, `Requires Signal Block`, `Requires Power Block`).
- Animated ML Criticality Score indicator bars:
  - **Score $\ge 75$**: Red (High/Critical risk)
  - **Score $50 - 74$**: Orange (Moderate risk)
  - **Score $30 - 49$**: Amber (Low-to-moderate risk)
  - **Score $< 30$**: Emerald (Routine maintenance)

### 5. Push-to-Talk Voice Defect Intake Modal
- Field engineers can record voice reports directly in the browser.
- Audio is transcribed via Groq Whisper large-v3.
- Key parameters are extracted via structured LLM (`openai/gpt-oss-120b`).
- **Interactive Corridor Section Selector / Override**:
  - *Directly solves user feedback*: Instead of solely guessing the section from colloquial station names or kilometer posts, the matched corridor section is pre-selected and can be confirmed or overridden with a single click across all 22 corridor sections.
- Live ML Criticality Score breakdown preview before submission:
  - Base Severity Points
  - Urgency Multiplier
  - Corridor Density Weight
  - Shadow Compatibility Bonus

### 6. Structured Manual Defect Report Modal
- Clean form for traditional keyboard input with automatic block section selection, estimated duration, target completion date, and block requirement flags.

---

## How to Launch and Test

### 1. Launch Backend (FastAPI)
In a PowerShell terminal:
```powershell
cd C:\Users\chait\Desktop\FINAL
.\myenv\Scripts\uvicorn.exe backend.main:app --reload --port 8000
```
Swagger UI is accessible at: `http://localhost:8000/docs`

### 2. Launch Frontend (Vite)
In a separate PowerShell terminal:
```powershell
cd C:\Users\chait\Desktop\FINAL\frontend
npm run dev
```
The application opens at: `http://localhost:5173`

---

## Step-by-Step UI Verification Walkthrough

### Test Case 1: Department Navigation & Live DB Sync
1. Open `http://localhost:5173` in any modern web browser.
2. Verify the top navigation bar displays:
   - Green pulse: **"Supabase Connected"**
   - Active Department: **TMS (Track Management)**
   - Defect count: **28 defects loaded**
3. Click the **SMMS (Signals & Telecom)** tab:
   - Observe table instantly switches to show 14 SMMS defects (e.g., `SMMS-SEP-001`, `SMMS-SEP-002`, point machines, track circuits).
4. Click the **TDMS (Traction / OHE)** tab:
   - Observe table switches to show 14 TDMS defects (e.g., `TDMS-SEP-001`, catenary wire, isolators).

### Test Case 2: Voice Defect Intake with Section Override
1. In the top navigation bar, click the **"Voice Intake"** button (microphone icon).
2. Click **"Start Recording"** (grant microphone permission if prompted) or switch to the **"Simulate Spoken Audio"** quick prompt.
3. Select the prompt:
   > *"Major rail fracture noticed on Up line between Samalkot and Annavaram near bridge 412, immediate track block needed for emergency clamp fixing."*
4. Click **"Transcribe & Extract Attributes"**.
5. Observe:
   - Whisper transcription appears in the transcript area.
   - Extracted Defect Type: `Rail fracture`
   - Severity: `critical`
   - Matched Section: `SLO-ANV-UP`
6. Test Section Override:
   - Open the **Corridor Section Dropdown** and change it to another section (e.g., `AKP-TUNI-DN`).
   - The ML Criticality Score immediately recalculates for the newly selected section!
7. Click **"Confirm & Submit Defect"**.
8. Notice the defect appears instantly in the department defect table with status `open` and input source `voice`.

### Test Case 3: Manual Defect Reporting
1. Click **"New Defect Report"** in the top navigation bar.
2. Fill in the form:
   - Defect Type: `Track switch defect`
   - Section: Select `VSKP-DVD-DN`
   - Severity: `High`
   - Work Category: `Defect`
   - Duration: `90` minutes
3. Click **"Register Defect"**.
4. The defect is saved to Supabase PostgreSQL and appears at the top of the table.

---

## Verification & Test Results
- **TypeScript & Vite Build**: Passed cleanly (`npm run build` exits code 0).
- **Backend Regression Suite**: **41 / 41 tests passing (100%)**.
- **Live Supabase PostgreSQL Integration**: Tested and verified across all 3 departments with 49 live records.
