r"""
Interactive / Automated Verification Script for Part 1.
Tests FastAPI endpoints directly via TestClient and reports status.
Run with:
    .\myenv\Scripts\python.exe verify_part1.py
"""
import sys
from fastapi.testclient import TestClient
from backend.main import app

def main():
    print("=" * 70)
    print("SIH26027 — Automatic Block Planning Prototype: Part 1 Verification")
    print("=" * 70)
    
    client = TestClient(app)
    
    # 1. Health & DB Check
    print("\n[1/6] Checking API Health and Supabase PostgreSQL Connectivity...")
    resp = client.get("/health")
    if resp.status_code == 200 and resp.json()["status"] == "healthy":
        db_info = resp.json()["database"]
        print(f"  --> SUCCESS: Database is HEALTHY (Latency: {db_info['latency_ms']} ms)")
        print(f"      Corridor Stations: {db_info['counts']['stations']}")
        print(f"      Block Sections:    {db_info['counts']['block_sections']}")
        print(f"      Trains in Timetable: {db_info['counts']['trains']}")
    else:
        print(f"  --> FAILED: {resp.status_code} - {resp.text}")
        sys.exit(1)
        
    # 2. Corridor Stations
    print("\n[2/6] Verifying Corridor Stations (VSKP -> BZA)...")
    resp = client.get("/coa/stations")
    if resp.status_code == 200:
        stations = resp.json()
        print(f"  --> SUCCESS: {len(stations)} stations loaded in sequence:")
        codes = " -> ".join([s["station_code"] for s in stations])
        print(f"      {codes}")
    else:
        print(f"  --> FAILED: {resp.status_code}")
        sys.exit(1)
        
    # 3. Block Sections
    print("\n[3/6] Verifying Corridor Block Sections...")
    resp = client.get("/coa/sections")
    if resp.status_code == 200:
        sections = resp.json()
        print(f"  --> SUCCESS: {len(sections)} directional block sections loaded.")
        sample = sections[0]
        print(f"      Sample: {sample['section_code']} ({sample['from_station_code']} to {sample['to_station_code']}), Track: {sample['track_code']}, Length: {sample['length_km']} km")
    else:
        print(f"  --> FAILED: {resp.status_code}")
        sys.exit(1)

    # 4. Train Movements
    print("\n[4/6] Verifying Train Movements for Date (2026-09-04)...")
    resp = client.get("/coa/trains?date=2026-09-04")
    if resp.status_code == 200:
        trains = resp.json()
        print(f"  --> SUCCESS: {len(trains)} train section movements found for 2026-09-04.")
        if trains:
            t = trains[0]
            print(f"      Sample: Train #{t['train_number']} ({t['train_name']}) in section {t['section_code']}")
            print(f"              Entry: {t['forecast_entry']}, Exit: {t['forecast_exit']}")
    else:
        print(f"  --> FAILED: {resp.status_code}")
        sys.exit(1)
        
    # 5. Existing Corridor Blocks
    print("\n[5/6] Verifying Allocated Blocks on Corridor...")
    resp = client.get("/coa/blocks")
    if resp.status_code == 200:
        blocks = resp.json()
        print(f"  --> SUCCESS: {len(blocks)} active blocks found on the corridor.")
        if blocks:
            b = blocks[0]
            print(f"      Sample: Block on {b['section_code']} from {b['planned_start']} to {b['planned_end']}")
            print(f"              Dept: {b['source_system']}, Defect: {b['defect_code']} ({b['defect_type']}), Type: {b['block_type']}")
    else:
        print(f"  --> FAILED: {resp.status_code}")
        sys.exit(1)

    # 6. Department Defect Queries
    print("\n[6/6] Verifying Department Defect Queues (TMS, SMMS, TDMS)...")
    total_defects = 0
    for dept in ["TMS", "SMMS", "TDMS"]:
        resp = client.get(f"/departments/{dept}/defects")
        if resp.status_code == 200:
            defects = resp.json()
            total_defects += len(defects)
            open_cnt = sum(1 for d in defects if d["status"] == "open")
            alloc_cnt = sum(1 for d in defects if d["status"] == "allocated")
            print(f"  --> {dept}: {len(defects)} total records ({open_cnt} open, {alloc_cnt} allocated)")
        else:
            print(f"  --> FAILED for {dept}: {resp.status_code}")
            sys.exit(1)

    print("\n" + "=" * 70)
    print(f"ALL PART 1 CHECKS PASSED! ({total_defects} department defect records synced)")
    print("=" * 70)

if __name__ == "__main__":
    main()
