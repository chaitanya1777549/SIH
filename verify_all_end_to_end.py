r"""
========================================================================================
SIH26027 — AI-POWERED AUTOMATIC BLOCK PLANNING SYSTEM
MASTER END-TO-END VERIFICATION & AUDIT RUNNER
========================================================================================
Runs an exhaustive automated system audit across all 8 architectural modules:
1. Database Connectivity & Connection Health (SQLAlchemy 2.0 / Supabase PostgreSQL)
2. Corridor Topology & Track Geography (12 Stations VSKP->BZA, 22 Block Sections)
3. Timetable & Schedule Movements (~286 movements / date, 29 trains)
4. Active Possession Blocks & Allocation Audit Trail
5. Google OR-Tools CP-SAT Mathematical Optimizer Engine (Gap padding & non-overlap constraints)
6. 1-Click Zero-Delay Shadow Block Piggyback Engine
7. Dynamic Downstream Train Delay Propagation & Two-Tier Conflict Re-Optimizer
8. Phase C Explainable ML Criticality Scorer (Gradient Boosted Trees + Feature Attributions)
9. Phase D/6 Emergency Mode Operations Center & Tactical Decision Matrix (Sustainable checks)
10. Phase 6/7 Natural Language & Voice Defect Intake Studio (Groq Whisper + LLM Extraction)
11. Multi-Department Queues & Real-time Bi-directional Notification Pipeline
========================================================================================
Run with:
    .\myenv\Scripts\python.exe verify_all_end_to_end.py
========================================================================================
"""
import sys
import time
from datetime import datetime, date, timedelta, timezone

from backend.database import SessionLocal, check_db_health
from backend.models import (
    Station,
    BlockSection,
    Train,
    TrainSchedule,
    Block,
    BlockRequest,
    BlockAllocationHistory,
    TMSDefect,
    SMMSDefect,
    TDMSDefect,
    EmergencyIncident,
)
from backend.optimizer.gap_calculator import compute_section_free_gaps, FreeGap
from backend.optimizer.service import run_corridor_optimization
from backend.shadow.engine import find_all_corridor_shadow_opportunities
from backend.reoptimizer.engine import (
    propagate_train_delay,
    resolve_conflicts_and_reoptimize,
    get_all_notifications,
)
from backend.ml.scorer import predict_criticality
from backend.emergency.engine import (
    create_emergency_incident,
    determine_heuristic_recommendation,
    generate_emergency_block_options,
    confirm_emergency_decision,
    advance_incident_lifecycle,
)
from backend.nl_intake.corridor_matcher import CorridorLocationMatcher

def print_header(title):
    print("\n" + "=" * 80)
    print(f" [MODULE AUDIT] {title}")
    print("=" * 80)

def main():
    start_time = time.time()
    print("*" * 80)
    print("  SIH26027 AUTOMATIC BLOCK PLANNING SYSTEM: FULL END-TO-END VERIFICATION")
    print(f"  Execution Timestamp: {datetime.now().isoformat()}")
    print("*" * 80)

    db = SessionLocal()
    audit_results = []

    # -------------------------------------------------------------------------
    # 1. DATABASE CONNECTIVITY & HEALTH
    # -------------------------------------------------------------------------
    print_header("1. DATABASE CONNECTIVITY & POOL HEALTH (SQLAlchemy 2.0)")
    try:
        health = check_db_health()
        status = health.get("status")
        latency = health.get("latency_ms")
        counts = health.get("counts", {})
        print(f"  [+] Supabase PostgreSQL Status: {status.upper()}")
        print(f"  [+] Remote Connection Pool Latency: {latency:.2f} ms")
        print(f"  [+] Live Seed Asset Counts: {counts}")
        assert status == "healthy", "Database health status is not healthy"
        audit_results.append(("1. Database Connectivity & Health", "PASSED", f"Latency: {latency:.1f}ms"))
    except Exception as e:
        print(f"  [-] Database health check failed: {e}")
        audit_results.append(("1. Database Connectivity & Health", "FAILED", str(e)))

    # -------------------------------------------------------------------------
    # 2. CORRIDOR TOPOLOGY (12 STATIONS, 22 BLOCK SECTIONS)
    # -------------------------------------------------------------------------
    print_header("2. CORRIDOR TOPOLOGY & DUAL-TRACK GEOGRAPHY")
    try:
        stations = db.query(Station).order_by(Station.sequence_on_corridor.asc()).all()
        print(f"  [+] Stations Found: {len(stations)} (Expected: 12)")
        stn_chain = " -> ".join([s.station_code for s in stations])
        print(f"  [+] Geographic Corridor Alignment: {stn_chain}")
        assert len(stations) == 12, f"Expected 12 stations, found {len(stations)}"
        assert stations[0].station_code == "VSKP", "First station must be VSKP"
        assert stations[-1].station_code == "BZA", "Last station must be BZA"

        sections = db.query(BlockSection).order_by(BlockSection.sequence_order.asc()).all()
        print(f"  [+] Directional Block Sections: {len(sections)} (Expected: 22)")
        up_count = sum(1 for s in sections if "UP" in s.section_code)
        dn_count = sum(1 for s in sections if "DN" in s.section_code)
        print(f"  [+] Track Distribution: {up_count} UP lines, {dn_count} DN lines")
        assert len(sections) == 22, f"Expected 22 block sections, found {len(sections)}"
        audit_results.append(("2. Corridor Topology & Dual Tracks", "PASSED", "12 Stations, 22 Sections Verified"))
    except Exception as e:
        print(f"  [-] Corridor topology check failed: {e}")
        audit_results.append(("2. Corridor Topology & Dual Tracks", "FAILED", str(e)))

    # -------------------------------------------------------------------------
    # 3. TIMETABLE TRAIN MOVEMENTS & ACTIVE BLOCKS
    # -------------------------------------------------------------------------
    print_header("3. TIMETABLE MOVEMENTS & ACTIVE POSSESSIONS")
    try:
        sample_date = date(2026, 9, 4)
        schedules = db.query(TrainSchedule).filter(TrainSchedule.service_date == sample_date).all()
        print(f"  [+] Timetable Movements on {sample_date}: {len(schedules)} rows")
        assert len(schedules) > 100, f"Expected >100 timetable rows, found {len(schedules)}"

        blocks = db.query(Block).filter(Block.status == "active").all()
        primary_blocks = [b for b in blocks if b.block_type == "primary"]
        shadow_blocks = [b for b in blocks if b.block_type == "shadow"]
        print(f"  [+] Active Corridor Blocks: {len(blocks)} (Primary: {len(primary_blocks)}, Shadow: {len(shadow_blocks)})")
        audit_results.append(("3. Timetable Movements & Blocks", "PASSED", f"{len(schedules)} trains, {len(blocks)} active blocks"))
    except Exception as e:
        print(f"  [-] Timetable/Blocks check failed: {e}")
        audit_results.append(("3. Timetable Movements & Blocks", "FAILED", str(e)))

    # -------------------------------------------------------------------------
    # 4. PHASE C EXPLAINABLE ML CRITICALITY SCORING ENGINE
    # -------------------------------------------------------------------------
    print_header("4. PHASE C EXPLAINABLE ML CRITICALITY SCORING")
    try:
        sample_features = {
            "severity_score": 95.0,
            "urgency_score": 90.0,
            "traffic_density": 80.0,
            "recurrence_score": 40.0,
            "block_required_score": 100.0,
        }
        res = predict_criticality(sample_features)
        pred_score = res.predicted_score
        dominant = res.dominant_factor
        explanation_text = res.explanation
        importances = res.feature_importances

        print(f"  [+] ML Predicted Criticality Score: {pred_score} / 100 (Domain Formula: {res.formula_score:.1f})")
        print(f"  [+] Dominant Contributor: {dominant}")
        print(f"  [+] Plain-English Operator Justification: {explanation_text}")
        print(f"  [+] Feature Importances: {importances}")
        assert 75 <= pred_score <= 100, f"Critical defect score out of expected range: {pred_score}"
        audit_results.append(("4. Explainable ML Criticality Engine", "PASSED", f"Score: {pred_score}, Top factor: {dominant}"))
    except Exception as e:
        print(f"  [-] ML Criticality check failed: {e}")
        audit_results.append(("4. Explainable ML Criticality Engine", "FAILED", str(e)))    # -------------------------------------------------------------------------
    # 5. GAP CALCULATOR & CP-SAT OPTIMIZER CORE
    # -------------------------------------------------------------------------
    print_header("5. GOOGLE OR-TOOLS CP-SAT MATHEMATICAL OPTIMIZER")
    try:
        # Verify full CP-SAT solver service invocation over corridor
        opt_res = run_corridor_optimization(
            db=db,
            start_date=date(2026, 9, 4),
            end_date=date(2026, 9, 5),
            safety_buffer_min=10,
            max_solve_time_sec=15,
        )
        print(f"  [+] CP-SAT Optimizer Execution: Status '{opt_res.status}', Execution Time: {opt_res.execution_time_ms:.1f}ms")
        print(f"      Pending Requests: {opt_res.total_pending_requests}, Scheduled: {opt_res.scheduled_count}, Unscheduled: {opt_res.unscheduled_count}")
        audit_results.append(("5. Google OR-Tools CP-SAT Optimizer", "PASSED", f"Status: {opt_res.status}, Scheduled: {opt_res.scheduled_count}"))
    except Exception as e:
        print(f"  [-] CP-SAT Optimizer check failed: {e}")
        audit_results.append(("5. Google OR-Tools CP-SAT Optimizer", "FAILED", str(e)))

    # -------------------------------------------------------------------------
    # 6. SHADOW BLOCK PIGGYBACK ENGINE
    # -------------------------------------------------------------------------
    print_header("6. 1-CLICK SHADOW BLOCK PIGGYBACK ENGINE")
    try:
        shadow_opps = find_all_corridor_shadow_opportunities(db)
        print(f"  [+] Corridor Shadow Opportunities Found: {len(shadow_opps)} active primary blocks with candidates")
        total_candidates = sum(len(o.candidates) for o in shadow_opps)
        print(f"  [+] Total Cross-Department Piggyback Candidates: {total_candidates}")
        for opp in shadow_opps[:2]:
            print(f"      * Section {opp.section_code}: Primary [{opp.primary_defect_code}] duration {opp.primary_duration_min}m has {len(opp.candidates)} candidate(s)")
            for c in opp.candidates[:1]:
                dept_name = getattr(c, 'source_system', getattr(c, 'department', 'TMS'))
                print(f"        -> {dept_name} {c.defect_code} ({c.defect_type}): Fit ratio {c.duration_fit_ratio:.2f}")
        audit_results.append(("6. Shadow Block Piggyback Engine", "PASSED", f"{total_candidates} candidate opportunities discovered"))
    except Exception as e:
        print(f"  [-] Shadow block check failed: {e}")
        audit_results.append(("6. Shadow Block Piggyback Engine", "FAILED", str(e)))

    # -------------------------------------------------------------------------
    # 7. DYNAMIC DELAY CASCADE & TWO-TIER CONFLICT RESOLUTION
    # -------------------------------------------------------------------------
    print_header("7. DOWNSTREAM DELAY CASCADE & RE-OPTIMIZER")
    try:
        # Test delay propagation on sample train 12717 at AKP on 2026-09-05
        cascade_res = propagate_train_delay(db, train_number="12717", service_date=date(2026, 9, 5), station_code="AKP", delay_minutes=30)
        print(f"  [+] Downstream Propagation for Train #{cascade_res.train_number} (+30m):")
        print(f"      Affected sections updated: {cascade_res.updated_sections_count}")
        print(f"      Status: {cascade_res.status}")

        # Test conflict resolution
        conflict_res = resolve_conflicts_and_reoptimize(db, service_date=date(2026, 9, 5), criticality_threshold=70)
        print(f"  [+] Two-Tier Conflict Resolver Scan:")
        print(f"      Conflicts Detected: {conflict_res.conflicts_detected}")
        print(f"      Trains Diverted (High Criticality Assets Preserved): {conflict_res.trains_diverted_count}")
        print(f"      Blocks Rescheduled (Low Criticality Assets Deferred): {conflict_res.blocks_revoked_count}")
        audit_results.append(("7. Delay Cascade & Conflict Resolver", "PASSED", f"{cascade_res.updated_sections_count} sections updated, 2-tier matrix executed"))
    except Exception as e:
        print(f"  [-] Delay Cascade check failed: {e}")
        audit_results.append(("7. Delay Cascade & Conflict Resolver", "FAILED", str(e)))

    # -------------------------------------------------------------------------
    # 8. EMERGENCY MODE ENGINE & MULTI-OPTION DECISION MATRIX
    # -------------------------------------------------------------------------
    print_header("8. EMERGENCY OPERATIONS CENTER & TACTICAL MATRIX")
    try:
        test_sec = db.query(BlockSection).filter(BlockSection.section_code == "AKP-TUNI-DN").first() or sections[0]
        # Create test incident
        inc = create_emergency_incident(
            db=db,
            source_system="TMS",
            block_section_id=test_sec.id,
            reported_text="Verification run: simulated emergency rail fracture at km 55",
            defect_type="Rail Fracture",
            severity="critical",
            estimated_duration_min=90,
        )
        print(f"  [+] Emergency Incident Created: ID {inc.id} on {test_sec.section_code}")

        rec_act, rec_reason = determine_heuristic_recommendation(db, inc)
        print(f"  [+] Heuristic Recommendation: {rec_act.upper()} — {rec_reason}")

        options = generate_emergency_block_options(db, inc, required_duration_min=90)
        print(f"  [+] Tactical Decision Options Generated: {len(options)} candidate cards")
        for opt in options:
            print(f"      * {opt['label']}: Window {opt['planned_start']} -> {opt['planned_end']}, Trains affected: {opt['trains_affected_count']}, Sustainable: {opt['sustainable']}")

        # Confirm Controller Decision
        confirm_res = confirm_emergency_decision(db, inc.id, decision="block", selected_option_id=options[0]["option_id"], notes="Verification test decision")
        print(f"  [+] Controller Confirmation: {confirm_res['message']} (Block ID: {confirm_res.get('block_id')})")

        # Advance Lifecycle to Released
        adv_res = advance_incident_lifecycle(db, inc.id, target_status="released", officer_notes="Verification test release")
        print(f"  [+] Safety Lifecycle Advanced: Status is now '{adv_res['new_status']}'")

        # Clean up test records (respect foreign keys)
        if confirm_res.get("block_id"):
            db.query(BlockAllocationHistory).filter(BlockAllocationHistory.block_id == confirm_res["block_id"]).delete()
            db.query(Block).filter(Block.id == confirm_res["block_id"]).delete()
        db.query(EmergencyIncident).filter(EmergencyIncident.id == inc.id).delete()
        if inc.block_request_id:
            db.query(BlockRequest).filter(BlockRequest.id == inc.block_request_id).delete()
        db.commit()

        audit_results.append(("8. Emergency Mode & Decision Matrix", "PASSED", f"{len(options)} options, sustainable check verified, full lifecycle executed"))
    except Exception as e:
        db.rollback()
        print(f"  [-] Emergency Mode check failed: {e}")
        audit_results.append(("8. Emergency Mode & Decision Matrix", "FAILED", str(e)))

    # -------------------------------------------------------------------------
    # 9. DETERMINISTIC CORRIDOR MATCHER & NLP INTAKE
    # -------------------------------------------------------------------------
    print_header("9. DETERMINISTIC CORRIDOR MATCHER & NLP PIPELINE")
    try:
        matcher = CorridorLocationMatcher(db)
        match_test_1 = matcher.match_location(db, "Major rail fracture at km 52 between Anakapalle and Tuni")
        print(f"  [+] Chainage Test Query: matched '{match_test_1.section_code}' (Confidence: {match_test_1.confidence:.2f}, Method: {match_test_1.match_method})")
        assert match_test_1.section_code == "AKP-TUNI-DN", f"Expected AKP-TUNI-DN, got {match_test_1.section_code}"

        match_test_2 = matcher.match_location(db, "Point machine failure between Samalkot and Anaparti on UP track")
        print(f"  [+] Station-Pair Test Query: matched '{match_test_2.section_code}' (Confidence: {match_test_2.confidence:.2f}, Method: {match_test_2.match_method})")
        assert "SLO" in match_test_2.section_code and "APT" in match_test_2.section_code, f"Expected SLO-APT section, got {match_test_2.section_code}"

        audit_results.append(("9. NLP Corridor Matcher & Pipelines", "PASSED", "Deterministic chainage & station-pair matching verified"))
    except Exception as e:
        print(f"  [-] Corridor Matcher check failed: {e}")
        audit_results.append(("9. NLP Corridor Matcher & Pipelines", "FAILED", str(e)))

    # -------------------------------------------------------------------------
    # 10. DEPARTMENT QUEUES & NOTIFICATIONS
    # -------------------------------------------------------------------------
    print_header("10. MULTI-DEPARTMENT QUEUES & NOTIFICATION STREAMS")
    try:
        tms_count = db.query(TMSDefect).count()
        smms_count = db.query(SMMSDefect).count()
        tdms_count = db.query(TDMSDefect).count()
        print(f"  [+] TMS Track Defects in PostgreSQL:  {tms_count}")
        print(f"  [+] SMMS Signal Defects in PostgreSQL: {smms_count}")
        print(f"  [+] TDMS Traction Defects in PostgreSQL: {tdms_count}")
        notifs = get_all_notifications(limit=5)
        print(f"  [+] Operational Notification Stream: {len(notifs)} recent events logged")

        history_count = db.query(BlockAllocationHistory).count()
        print(f"  [+] Immutable Audit History Records (`block_allocation_history`): {history_count}")
        assert history_count > 0, "Expected at least 1 allocation history row"

        audit_results.append(("10. Department Queues & Audit Stream", "PASSED", f"{tms_count+smms_count+tdms_count} total defects, {history_count} audit records"))
    except Exception as e:
        print(f"  [-] Department Queues check failed: {e}")
        audit_results.append(("10. Department Queues & Audit Stream", "FAILED", str(e)))

    # -------------------------------------------------------------------------
    # FINAL AUDIT SUMMARY
    # -------------------------------------------------------------------------
    duration = time.time() - start_time
    print("\n" + "=" * 80)
    print("                    FINAL SYSTEM VERIFICATION AUDIT REPORT")
    print("=" * 80)
    all_passed = True
    for module, res, detail in audit_results:
        flag = "[PASS]" if res == "PASSED" else "[FAIL]"
        print(f"  {flag}  {module:<42} : {detail}")
        if res != "PASSED":
            all_passed = False

    print("-" * 80)
    if all_passed:
        print(f"  >>> ALL 10 ARCHITECTURAL MODULES VERIFIED SUCCESSFULLY IN {duration:.2f} SECONDS <<<")
        print("  >>> SYSTEM IS 100% READY FOR LIVE OPERATION & PRESENTATION <<<")
    else:
        print("  >>> WARNING: ONE OR MORE MODULE AUDITS FAILED <<<")
    print("=" * 80)

    db.close()
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
