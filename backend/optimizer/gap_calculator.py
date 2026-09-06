"""
Gap calculation engine for corridor block sections.
Computes train occupancies with safety buffers, merges overlapping windows,
and determines free time gaps per block section.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Tuple
from uuid import UUID

@dataclass
class FreeGap:
    gap_id: int
    section_id: UUID
    start_min: int
    end_min: int
    duration_min: int
    start_dt: datetime
    end_dt: datetime

def merge_intervals(intervals: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """
    Merges overlapping or abutting [start, end] intervals.
    Intervals must be in minutes.
    """
    if not intervals:
        return []

    # Sort by start time, then end time
    sorted_intervals = sorted(intervals, key=lambda x: (x[0], x[1]))
    merged = [sorted_intervals[0]]

    for current in sorted_intervals[1:]:
        prev_start, prev_end = merged[-1]
        if current[0] <= prev_end:
            # Overlapping or adjacent: extend previous
            merged[-1] = (prev_start, max(prev_end, current[1]))
        else:
            merged.append(current)

    return merged

def compute_section_free_gaps(
    section_id: UUID,
    horizon_start: datetime,
    horizon_end: datetime,
    train_movements: List[Tuple[datetime, datetime]],
    existing_blocks: List[Tuple[datetime, datetime]],
    safety_buffer_min: int = 10,
) -> List[FreeGap]:
    """
    Computes all free time intervals for a single block section within [horizon_start, horizon_end].
    - Pads train movements by safety_buffer_min on both sides.
    - Includes existing active maintenance blocks without additional buffer.
    - Merges all occupied intervals and inverts to obtain free gaps.
    """
    t0 = horizon_start
    total_minutes = int((horizon_end - t0).total_seconds() // 60)
    if total_minutes <= 0:
        return []

    occupied_intervals: List[Tuple[int, int]] = []

    # 1. Train occupancies with safety buffer
    for entry_dt, exit_dt in train_movements:
        # Ensure UTC timezone awareness
        if entry_dt.tzinfo is None:
            entry_dt = entry_dt.replace(tzinfo=timezone.utc)
        if exit_dt.tzinfo is None:
            exit_dt = exit_dt.replace(tzinfo=timezone.utc)

        start_m = int((entry_dt - t0).total_seconds() // 60) - safety_buffer_min
        end_m = int((exit_dt - t0).total_seconds() // 60) + safety_buffer_min

        # Clamp to horizon
        clamped_start = max(0, start_m)
        clamped_end = min(total_minutes, end_m)

        if clamped_end > clamped_start:
            occupied_intervals.append((clamped_start, clamped_end))

    # 2. Existing active blocks (exact duration)
    for blk_start_dt, blk_end_dt in existing_blocks:
        if blk_start_dt.tzinfo is None:
            blk_start_dt = blk_start_dt.replace(tzinfo=timezone.utc)
        if blk_end_dt.tzinfo is None:
            blk_end_dt = blk_end_dt.replace(tzinfo=timezone.utc)

        start_m = int((blk_start_dt - t0).total_seconds() // 60)
        end_m = int((blk_end_dt - t0).total_seconds() // 60)

        clamped_start = max(0, start_m)
        clamped_end = min(total_minutes, end_m)

        if clamped_end > clamped_start:
            occupied_intervals.append((clamped_start, clamped_end))

    # 3. Merge occupied intervals
    merged_occupied = merge_intervals(occupied_intervals)

    # 4. Invert occupied intervals to find free gaps
    gaps: List[FreeGap] = []
    cursor = 0
    gap_id_counter = 1

    for occ_start, occ_end in merged_occupied:
        if occ_start > cursor:
            gap_duration = occ_start - cursor
            gap_start_dt = t0 + timedelta(minutes=cursor)
            gap_end_dt = t0 + timedelta(minutes=occ_start)
            gaps.append(FreeGap(
                gap_id=gap_id_counter,
                section_id=section_id,
                start_min=cursor,
                end_min=occ_start,
                duration_min=gap_duration,
                start_dt=gap_start_dt,
                end_dt=gap_end_dt,
            ))
            gap_id_counter += 1
        cursor = max(cursor, occ_end)

    if cursor < total_minutes:
        gap_duration = total_minutes - cursor
        gap_start_dt = t0 + timedelta(minutes=cursor)
        gap_end_dt = t0 + timedelta(minutes=total_minutes)
        gaps.append(FreeGap(
            gap_id=gap_id_counter,
            section_id=section_id,
            start_min=cursor,
            end_min=total_minutes,
            duration_min=gap_duration,
            start_dt=gap_start_dt,
            end_dt=gap_end_dt,
        ))

    return gaps
