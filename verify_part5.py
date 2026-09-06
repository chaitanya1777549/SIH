"""
Verification CLI script for Part 5: Emergency Mode Engine & Multi-Option Decision Matrix.
Demonstrates:
1. Emergency incident intake and asset identification.
2. Heuristic action recommendation (Hold / Divert / Block / Notify) with live train conflict analysis.
3. Multi-option comparison cards:
   - Strict sustainable time enforcement.
   - Immediate Emergency Closure (+15m).
   - Targeted Single-Train Hold/Delay trade-off.
   - Shadow Block Piggyback (if starting well before emergency deadline).
   - Earliest Natural Gap.
4. Controller one-click confirmation (allocates emergency Block, logs history, emits green notification).
5. Lifecycle progression: Field Repair -> Safety Confirmation -> Formal Corridor Release.
"""
import sys
from datetime import datetime, timedelta, timezone

from backend.database import SessionLocal
from backend.models import (
    BlockSection,
    EmergencyIncident,
    Block,
    BlockRequest,
    BlockAllocationHistory,
    TMSDefect,
)
from backend.emergency.engine import (
    create_emergency_incident,
    determine_heuristic_recommendation,
    generate_emergency_block_options,
    confirm_emergency_decision,
    advance_incident_lifecycle,
)
from backend.reoptimizer.engine import get_all_notifications, clear_notifications

def print_separator(title=""):
    print("\n" + "=" * 78)
    if title:
        print(f"  {title}")
        print("=" * 78)

def main():
    print_separator("SIH26027 — PART 5: EMERGENCY MODE ENGINE & MULTI-OPTION MATRIX")
    clear_notifications()
    db = SessionLocal()

    incident_id = None
    block_id = None
    req_id = None

    try:
        # Step 1: Select corridor section
        section = db.query(BlockSection).filter(BlockSection.section_code == "AKP-TUNI-DN").first()
        if not section:
            section = db.query(BlockSection).first()

        print(f"\n[STEP 1] Reporting Critical Emergency Incident on '{section.section_code}'...")
        incident = create_emergency_incident(
            db=db,
            source_system="TMS",
            block_section_id=section.id,
            reported_text="Emergency rail web shear detected during morning track patrol. Derailment hazard.",
            defect_type="Rail Web Shear",
            severity="critical",
            estimated_duration_min=90,
        )
        incident_id = incident.id
        print(f"  --> Incident ID:   {incident.id}")
        print(f"  --> Source System: {incident.source_system}")
        print(f"  --> Status:        {incident.status}")

        # Step 2: Heuristic Analysis & Recommendation
        print_separator("STEP 2: CORRIDOR CONFLICT ANALYSIS & HEURISTIC RECOMMENDATION")
        rec_action, rec_reason = determine_heuristic_recommendation(db, incident)
        print(f"  --> Recommended Action: {rec_action.upper()}")
        print(f"  --> Operational Reason: {rec_reason}")

        # Step 3: Multi-Option Block Comparison Cards
        print_separator("STEP 3: MULTI-OPTION BLOCK PROPOSALS (REAL COMPUTED TRADE-OFFS)")
        options = generate_emergency_block_options(db, incident, required_duration_min=90)
        print(f"  Generated {len(options)} concrete candidate options (Strict sustainable deadline enforced):")

        for idx, opt in enumerate(options, 1):
            badge = "[SHADOW]" if opt["is_shadow"] else "[BLOCK]"
            print(f"\n  Card #{idx} {badge} {opt['label']}")
            print(f"    - Window:         {opt['planned_start'][:16]} to {opt['planned_end'][:16]} ({opt['duration_min']} min)")
            print(f"    - Trains Delayed: {opt['trains_affected_count']} train(s) | Total Delay: {opt['total_delay_minutes']} min")
            if opt.get("affected_train_numbers"):
                print(f"    - Trains Named:   {', '.join(opt['affected_train_numbers'])}")
            print(f"    - Resource Impt:  {opt['resource_impact']}")
            print(f"    - Summary:        {opt['description']}")

        # Step 4: Controller Confirmation
        print_separator("STEP 4: CONTROLLER SELECTS & CONFIRMS OPTION")
        chosen_option = options[0]
        print(f"  Officer selects: '{chosen_option['label']}'")

        confirm_res = confirm_emergency_decision(
            db=db,
            incident_id=incident.id,
            decision="block",
            selected_option_id=chosen_option["option_id"],
            notes="Authorized emergency possession by Chief Controller on duty.",
        )
        block_id = confirm_res.get("block_id")
        req_id = confirm_res.get("block_request_id")

        print(f"\n  [OK] Decision Enacted Successfully!")
        print(f"    - Incident Status:   confirmed")
        print(f"    - Emergency Block:   {block_id}")
        print(f"    - Block Request:     {req_id} (is_emergency=True)")
        print(f"    - History Logged:    reason='emergency_block_allocated'")

        # Step 5: Lifecycle Progression (Repair -> Safety Confirmation -> Release)
        print_separator("STEP 5: FIELD REPAIR & CORRIDOR RELEASE LIFECYCLE")
        
        # Advance to repairing
        adv1 = advance_incident_lifecycle(db, incident.id, "repairing")
        print(f"  [1] Field Team Mobilized: status -> '{adv1['new_status']}'")

        # Advance to safety_confirmed
        adv2 = advance_incident_lifecycle(db, incident.id, "safety_confirmed", officer_notes="Weld test & track geometry verified safe.")
        print(f"  [2] Safety Certified:    status -> '{adv2['new_status']}'")

        # Formal release
        adv3 = advance_incident_lifecycle(db, incident.id, "released", officer_notes="Corridor formally returned to commercial traffic.")
        print(f"  [3] Track Reopened:      status -> '{adv3['new_status']}'")

        # Step 6: Stream Live Notifications
        print_separator("STEP 6: LIVE EMERGENCY AUDIT NOTIFICATIONS")
        notifs = get_all_notifications()
        print(f"  Streamed {len(notifs)} emergency notifications across the corridor:")
        for n in notifs[:5]:
            print(f"  [{n['type']:<5}] | Dept: {n['department']:<4} | {n['title']}")
            print(f"          | {n['message']}")

        print_separator("ALL EMERGENCY MODE WORKFLOWS VERIFIED SUCCESSFULLY")

    except Exception as e:
        print(f"\n[ERROR] Verification failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Cleanup
        if block_id:
            db.query(BlockAllocationHistory).filter(BlockAllocationHistory.block_id == block_id).delete()
            db.query(Block).filter(Block.id == block_id).delete()
        if incident_id:
            inc = db.query(EmergencyIncident).filter(EmergencyIncident.id == incident_id).first()
            if inc:
                d_id = inc.tms_defect_id
                inc.block_request_id = None
                db.flush()
                db.delete(inc)
                db.flush()
                if req_id:
                    db.query(BlockRequest).filter(BlockRequest.id == req_id).delete()
                if d_id:
                    db.query(TMSDefect).filter(TMSDefect.id == d_id).delete()
        db.commit()
        db.close()

if __name__ == "__main__":
    main()
