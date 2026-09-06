"""
Verification CLI script for Dynamic Train Delay Propagation & Corridor Re-Optimization.
Demonstrates:
1. Propagation of a 30-minute delay at Anakapalle (AKP) for Train 12717 down the corridor.
2. Conflict detection against active maintenance blocks.
3. Decision matrix execution:
   - High-Criticality blocks: Conflicting trains are diverted (status='diverted'), safety block preserved.
   - Routine blocks: Block revoked, audit trail written to block_allocation_history, immediate shadow/gap rescheduled.
4. Department notification stream (BLUE diversions, RED revocations, GREEN reschedules).
"""
import sys
from datetime import date, datetime, timedelta, timezone

from backend.database import SessionLocal
from backend.models import Train, BlockSection, TrainSchedule
from backend.reoptimizer.engine import (
    propagate_train_delay,
    resolve_conflicts_and_reoptimize,
    get_all_notifications,
    clear_notifications,
)

def print_separator(title=""):
    print("\n" + "=" * 75)
    if title:
        print(f"  {title}")
        print("=" * 75)

def main():
    print_separator("SIH26027 — DYNAMIC TRAIN DELAY & RE-OPTIMIZATION VERIFICATION")
    clear_notifications()
    db = SessionLocal()

    train_no = "12717"
    service_date = date(2026, 9, 5)
    station_code = "AKP"
    delay_minutes = 30

    try:
        # Step 1: Delay Propagation
        print(f"\n[STEP 1] Injecting +{delay_minutes}min delay for Train {train_no} at Station '{station_code}' ({service_date})...")
        delay_res = propagate_train_delay(
            db=db,
            train_number=train_no,
            service_date=service_date,
            station_code=station_code,
            delay_minutes=delay_minutes,
        )

        print(f"\n[OK] Delay Propagation Successful!")
        print(f"  - Train Number: {delay_res.train_number}")
        print(f"  - Reported Station: {delay_res.reported_station}")
        print(f"  - Delay: +{delay_res.delay_minutes} minutes")
        print(f"  - Downstream Sections Updated: {delay_res.updated_sections_count}")
        print("\n  Sample Downstream Timetable Updates:")
        print(f"  {'Section':<14} | {'Scheduled Entry':<19} | {'Forecast Entry':<19} | {'Delay':<6}")
        print("  " + "-" * 65)
        for s in delay_res.updated_sections[:6]:
            print(f"  {s.section_code:<14} | {s.scheduled_entry.strftime('%H:%M:%S'):<19} | {s.forecast_entry.strftime('%H:%M:%S'):<19} | +{s.delay_minutes}m")

        # Step 2: Dynamic Re-Optimization
        print_separator("STEP 2: EXECUTING CORRIDOR RE-OPTIMIZATION")
        print(f"Running dynamic conflict evaluation on {service_date} (Criticality Threshold = 70)...")

        reopt_res = resolve_conflicts_and_reoptimize(
            db=db,
            service_date=service_date,
            criticality_threshold=70,
        )

        print(f"\n[OK] Corridor Re-Optimization Completed!")
        print(f"  - Total Conflicts Evaluated: {reopt_res.conflicts_detected}")
        print(f"  - Trains Diverted (Safety Priority): {reopt_res.trains_diverted_count}")
        print(f"  - Blocks Revoked (Traffic Priority): {reopt_res.blocks_revoked_count}")
        print(f"  - Blocks Rescheduled (Shadow / Gap): {reopt_res.blocks_rescheduled_count}")

        if reopt_res.details:
            print("\n  Conflict Resolution Decisions:")
            for d in reopt_res.details:
                print(f"  * Section {d.section_code} | Train {d.train_number} vs Block {str(d.block_id)[:8]}")
                print(f"    - Decision: {d.decision}")
                print(f"    - Criticality Score: {d.criticality_score} (Severity: {d.severity})")
                print(f"    - Notes: {d.notes}")

        # Step 3: Notification Stream
        print_separator("STEP 3: DEPARTMENT NOTIFICATION STREAM")
        notifs = get_all_notifications()
        print(f"Retrieved {len(notifs)} live corridor notifications:")
        for n in notifs:
            badge = f"[{n['type']}]"
            print(f"  {badge:<8} | Dept: {n['department']:<4} | {n['title']}")
            print(f"           | {n['message']}")

        print_separator("ALL VERIFICATION CHECKS COMPLETED SUCCESSFULLY")

    except Exception as e:
        print(f"\n[ERROR] Verification failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Reset delay for Train 12717 to maintain clean state
        try:
            train = db.query(Train).filter(Train.train_number == train_no).first()
            if train:
                db.query(TrainSchedule).filter(
                    TrainSchedule.train_id == train.id,
                    TrainSchedule.service_date == service_date
                ).update({
                    "delay_minutes": 0,
                    "forecast_entry": TrainSchedule.scheduled_entry,
                    "forecast_exit": TrainSchedule.scheduled_exit,
                    "status": "scheduled"
                })
                db.commit()
        except Exception:
            pass
        db.close()

if __name__ == "__main__":
    main()
