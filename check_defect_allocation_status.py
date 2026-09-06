r"""
Corridor Defect & Block Allocation Audit Script.
Provides a clear, tabular view of:
1. Total defects across TMS, SMMS, TDMS.
2. Defects already allocated with blocks.
3. Defects that do NOT need blocks (requires_block = False).
4. Eligible open defects that can be turned into block_requests and scheduled.

Run with:
    .\myenv\Scripts\python.exe check_defect_allocation_status.py
"""
from backend.database import SessionLocal
from backend.models import TMSDefect, SMMSDefect, TDMSDefect, BlockRequest, Block

def main():
    db = SessionLocal()
    print("=" * 80)
    print("SIH26027 — Defect & Block Allocation Audit Report")
    print("=" * 80)

    dept_configs = [
        ("TMS", TMSDefect, "requires_track_block"),
        ("SMMS", SMMSDefect, "requires_signal_block"),
        ("TDMS", TDMSDefect, "requires_power_block"),
    ]

    total_all = 0
    total_allocated = 0
    total_open_no_block = 0
    total_open_eligible = 0

    eligible_candidates = []

    for dept_name, Model, block_flag in dept_configs:
        records = db.query(Model).all()
        total_all += len(records)
        print(f"\n--- {dept_name} ({len(records)} records) ---")

        for r in records:
            needs_block = getattr(r, block_flag)
            req_by_str = r.required_by.strftime('%Y-%m-%d') if r.required_by else "No deadline"

            if r.status == "allocated":
                total_allocated += 1
                # Find matching block
                blk = (
                    db.query(Block)
                    .join(BlockRequest)
                    .filter(
                        (BlockRequest.tms_defect_id == r.id) |
                        (BlockRequest.smms_defect_id == r.id) |
                        (BlockRequest.tdms_defect_id == r.id)
                    )
                    .first()
                )
                time_str = f"{blk.planned_start.strftime('%d-%b %H:%M')} to {blk.planned_end.strftime('%H:%M')}" if blk else "Allocated"
                print(f"  [ALLOCATED] {r.defect_code:<14} | Score: {r.criticality_score:>2} | {time_str} | {r.defect_type}")
            else:
                if not needs_block:
                    total_open_no_block += 1
                    print(f"  [OPEN-NO-BLOCK] {r.defect_code:<14} | Score: {r.criticality_score:>2} | (No block needed) | {r.defect_type}")
                else:
                    total_open_eligible += 1
                    eligible_candidates.append((dept_name, r, block_flag))
                    print(f"  [OPEN-ELIGIBLE] {r.defect_code:<14} | Score: {r.criticality_score:>2} | Deadline: {req_by_str} | Dur: {r.estimated_duration_min}m | {r.defect_type}")

    print("\n" + "=" * 80)
    print("EXECUTIVE AUDIT SUMMARY:")
    print(f"  Total Defect Records:                 {total_all}")
    print(f"  Already Allocated with Blocks:        {total_allocated}")
    print(f"  Open - Do NOT Require Block:          {total_open_no_block} (off-track work)")
    print(f"  Open - Require Block (Eligible):      {total_open_eligible} (can be scheduled)")
    print("=" * 80)

    if eligible_candidates:
        print("\nEligible Open Defects Ready for Block Request Creation:")
        for dept, defect, flag in eligible_candidates:
            print(f"  - {dept}: {defect.defect_code} ({defect.defect_type}, Dur: {defect.estimated_duration_min}m, Criticality: {defect.criticality_score})")

    db.close()

if __name__ == "__main__":
    main()
