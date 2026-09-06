-- ============================================================
-- SIH26027 — Block Planning Prototype
-- Trimmed schema for Supabase (Postgres)
-- Corridor: Visakhapatnam (VSKP) -> Vijayawada (BZA)
-- Run this whole file in Supabase SQL Editor, top to bottom.
-- ============================================================

create extension if not exists pgcrypto; -- gives us gen_random_uuid()

-- ------------------------------------------------------------
-- 1. stations
-- ------------------------------------------------------------
create table stations (
  id                    uuid primary key default gen_random_uuid(),
  station_code          varchar(10) unique not null,
  station_name          varchar(100) not null,
  sequence_on_corridor  int not null,             -- 1,2,3... order along the corridor
  created_at            timestamptz not null default now()
);

-- ------------------------------------------------------------
-- 2. tracks
-- ------------------------------------------------------------
create table tracks (
  id            uuid primary key default gen_random_uuid(),
  track_code    varchar(20) unique not null,      -- e.g. 'UP_MAIN', 'DN_MAIN'
  description   varchar(100),
  created_at    timestamptz not null default now()
);

-- ------------------------------------------------------------
-- 3. block_sections  (the atomic unit everything else hangs off)
-- ------------------------------------------------------------
create table block_sections (
  id                uuid primary key default gen_random_uuid(),
  section_code      varchar(30) unique not null,  -- e.g. 'VSKP-DVD'
  from_station_id   uuid not null references stations(id),
  to_station_id     uuid not null references stations(id),
  track_id          uuid not null references tracks(id),
  length_km         numeric(6,2),
  sequence_order    int not null,                 -- order along the corridor, for timeline rendering
  created_at        timestamptz not null default now()
);
create index idx_block_sections_from  on block_sections(from_station_id);
create index idx_block_sections_to    on block_sections(to_station_id);
create index idx_block_sections_track on block_sections(track_id);

-- ------------------------------------------------------------
-- 4. trains
-- ------------------------------------------------------------
create table trains (
  id             uuid primary key default gen_random_uuid(),
  train_number   varchar(10) unique not null,
  train_name     varchar(100),
  train_type     varchar(20) check (train_type in ('express','passenger','goods','mail')),
  created_at     timestamptz not null default now()
);

-- ------------------------------------------------------------
-- 5. train_schedule
-- One row per (train, section, service_date). Holds BOTH the
-- immutable scheduled times AND the current live forecast.
-- Delay handling = update forecast_entry/forecast_exit/delay_minutes
-- on this row. scheduled_entry/scheduled_exit never change.
-- ------------------------------------------------------------
create table train_schedule (
  id                uuid primary key default gen_random_uuid(),
  train_id          uuid not null references trains(id),
  block_section_id  uuid not null references block_sections(id),
  service_date      date not null,
  scheduled_entry   timestamptz not null,
  scheduled_exit    timestamptz not null,
  forecast_entry    timestamptz not null,          -- = scheduled_* at seed time
  forecast_exit     timestamptz not null,
  delay_minutes     int not null default 0,
  status            varchar(20) not null default 'scheduled'
                      check (status in ('scheduled','running','completed','cancelled','diverted')),
  updated_at        timestamptz not null default now(),
  unique (train_id, block_section_id, service_date)
);
create index idx_train_schedule_section_date on train_schedule(block_section_id, service_date);
create index idx_train_schedule_train        on train_schedule(train_id);

-- ------------------------------------------------------------
-- 6/7/8. Department defect tables (TMS / SMMS / TDMS)
-- Same shape on purpose — keeps the department origin obvious
-- (separate tables) while keeping each one simple.
-- ------------------------------------------------------------
create table tms_defects (
  id                     uuid primary key default gen_random_uuid(),
  defect_code            varchar(30) unique not null,
  block_section_id       uuid not null references block_sections(id),
  defect_type            varchar(50) not null,
  description            text,
  severity               varchar(20) check (severity in ('low','medium','high','critical')),
  criticality_score      int not null check (criticality_score between 0 and 100),
  detected_at            timestamptz not null default now(),
  required_by            timestamptz,
  estimated_duration_min int not null,
  requires_track_block   boolean not null default true,
  status                 varchar(20) not null default 'open'
                           check (status in ('open','requested','allocated','resolved')),
  created_at             timestamptz not null default now()
);

create table smms_defects (
  id                     uuid primary key default gen_random_uuid(),
  defect_code            varchar(30) unique not null,
  block_section_id       uuid not null references block_sections(id),
  defect_type            varchar(50) not null,
  description            text,
  severity               varchar(20) check (severity in ('low','medium','high','critical')),
  criticality_score      int not null check (criticality_score between 0 and 100),
  detected_at            timestamptz not null default now(),
  required_by            timestamptz,
  estimated_duration_min int not null,
  requires_signal_block  boolean not null default true,
  status                 varchar(20) not null default 'open'
                           check (status in ('open','requested','allocated','resolved')),
  created_at             timestamptz not null default now()
);

create table tdms_defects (
  id                     uuid primary key default gen_random_uuid(),
  defect_code            varchar(30) unique not null,
  block_section_id       uuid not null references block_sections(id),
  defect_type            varchar(50) not null,
  description            text,
  severity               varchar(20) check (severity in ('low','medium','high','critical')),
  criticality_score      int not null check (criticality_score between 0 and 100),
  detected_at            timestamptz not null default now(),
  required_by            timestamptz,
  estimated_duration_min int not null,
  requires_power_block   boolean not null default true,
  status                 varchar(20) not null default 'open'
                           check (status in ('open','requested','allocated','resolved')),
  created_at             timestamptz not null default now()
);

create index idx_tms_defects_section  on tms_defects(block_section_id);
create index idx_smms_defects_section on smms_defects(block_section_id);
create index idx_tdms_defects_section on tdms_defects(block_section_id);

-- ------------------------------------------------------------
-- 9. block_requests
-- One row = one defect turned into a request the optimizer sees.
-- Exactly one of tms/smms/tdms_defect_id must be set (enforced below).
-- ------------------------------------------------------------
create table block_requests (
  id                      uuid primary key default gen_random_uuid(),
  source_system           varchar(10) not null check (source_system in ('TMS','SMMS','TDMS')),
  tms_defect_id           uuid references tms_defects(id),
  smms_defect_id          uuid references smms_defects(id),
  tdms_defect_id          uuid references tdms_defects(id),
  block_section_id        uuid not null references block_sections(id),
  criticality_score       int not null check (criticality_score between 0 and 100),
  required_by             timestamptz,
  estimated_duration_min  int not null,
  requires_power_block    boolean not null default false,
  requires_signal_block   boolean not null default false,
  status                  varchar(20) not null default 'pending'
                             check (status in ('pending','allocated','rejected')),
  created_at              timestamptz not null default now(),
  constraint chk_single_source check (
    (tms_defect_id  is not null)::int +
    (smms_defect_id is not null)::int +
    (tdms_defect_id is not null)::int = 1
  )
);
create index idx_block_requests_section on block_requests(block_section_id);
create index idx_block_requests_status  on block_requests(status);

-- ------------------------------------------------------------
-- 10. blocks — the live, currently-allocated plan
-- ------------------------------------------------------------
create table blocks (
  id                    uuid primary key default gen_random_uuid(),
  block_request_id      uuid not null references block_requests(id),
  block_section_id      uuid not null references block_sections(id),
  planned_start         timestamptz not null,
  planned_end           timestamptz not null,
  status                varchar(20) not null default 'active'
                           check (status in ('active','completed','cancelled','superseded')),
  optimization_run_at   timestamptz not null default now(),
  created_at            timestamptz not null default now(),
  check (planned_end > planned_start)
);
create index idx_blocks_section on blocks(block_section_id);
create index idx_blocks_status  on blocks(status);

-- ------------------------------------------------------------
-- 11. block_allocation_history — append-only, never updated/deleted
-- This is what makes "show old vs new allocation" possible.
-- ------------------------------------------------------------
create table block_allocation_history (
  id                 uuid primary key default gen_random_uuid(),
  block_id           uuid references blocks(id),
  block_request_id   uuid not null references block_requests(id),
  block_section_id   uuid not null references block_sections(id),
  previous_start     timestamptz,
  previous_end       timestamptz,
  new_start          timestamptz,
  new_end            timestamptz,
  reason             varchar(50) not null,   -- 'initial_allocation' | 'reoptimized_due_to_delay' | 'reoptimized_due_to_new_critical_defect'
  changed_at         timestamptz not null default now()
);
create index idx_history_request on block_allocation_history(block_request_id);

-- ============================================================
-- Done. 11 tables total.
-- ============================================================
-- ============================================================
-- Adds real route-classification attributes to the tracks table.
-- Run this once, after schema.sql, before the real-data seed below.
-- ============================================================

alter table tracks
  add column if not exists gauge_mm         int,               -- 1676 = Indian broad gauge
  add column if not exists electrified      boolean default true,
  add column if not exists max_speed_kmph   int,
  add column if not exists line_class       varchar(10);        -- IR route category: 'A','B','C','D','E'
-- ============================================================
-- PHASE 1 -- idempotent. Safe to run even if partially applied
-- already, or run twice. Nothing here touches trains, schedule,
-- stations, tracks, or block_sections.
-- ============================================================

-- ------------------------------------------------------------
-- 1. work_category on the three department tables
-- ------------------------------------------------------------
alter table tms_defects  add column if not exists work_category varchar(20) not null default 'defect';
alter table smms_defects add column if not exists work_category varchar(20) not null default 'defect';
alter table tdms_defects add column if not exists work_category varchar(20) not null default 'defect';

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'chk_tms_work_category') then
    alter table tms_defects add constraint chk_tms_work_category
      check (work_category in ('defect','scheduled_maintenance','overdue_task'));
  end if;
  if not exists (select 1 from pg_constraint where conname = 'chk_smms_work_category') then
    alter table smms_defects add constraint chk_smms_work_category
      check (work_category in ('defect','scheduled_maintenance','overdue_task'));
  end if;
  if not exists (select 1 from pg_constraint where conname = 'chk_tdms_work_category') then
    alter table tdms_defects add constraint chk_tdms_work_category
      check (work_category in ('defect','scheduled_maintenance','overdue_task'));
  end if;
end $$;

-- ------------------------------------------------------------
-- 2. Indexes on block_requests FK columns
-- ------------------------------------------------------------
create index if not exists idx_block_requests_tms_defect  on block_requests(tms_defect_id);
create index if not exists idx_block_requests_smms_defect on block_requests(smms_defect_id);
create index if not exists idx_block_requests_tdms_defect on block_requests(tdms_defect_id);

-- ------------------------------------------------------------
-- 3. Composite index on blocks
-- ------------------------------------------------------------
create index if not exists idx_blocks_request_status on blocks(block_request_id, status);

-- ------------------------------------------------------------
-- 4. Emergency structure
-- ------------------------------------------------------------
alter table block_requests add column if not exists is_emergency boolean not null default false;

create table if not exists emergency_incidents (
  id                   uuid primary key default gen_random_uuid(),
  source_system        varchar(10) not null check (source_system in ('TMS','SMMS','TDMS')),
  tms_defect_id        uuid references tms_defects(id),
  smms_defect_id       uuid references smms_defects(id),
  tdms_defect_id       uuid references tdms_defects(id),
  block_section_id     uuid not null references block_sections(id),
  reported_text        text not null,
  status               varchar(20) not null default 'reported'
                          check (status in ('reported','analyzing','action_recommended','confirmed','notified','repairing','safety_confirmed','released')),
  recommended_action   varchar(20) check (recommended_action in ('hold','divert','block','notify')),
  controller_decision  varchar(20) check (controller_decision in ('hold','divert','block','notify')),
  block_request_id     uuid references block_requests(id),
  confirmed_at         timestamptz,
  created_at           timestamptz not null default now(),
  constraint chk_emergency_single_source check (
    (tms_defect_id  is not null)::int +
    (smms_defect_id is not null)::int +
    (tdms_defect_id is not null)::int = 1
  )
);
create index if not exists idx_emergency_incidents_section        on emergency_incidents(block_section_id);
create index if not exists idx_emergency_incidents_status         on emergency_incidents(status);
create index if not exists idx_emergency_incidents_block_request  on emergency_incidents(block_request_id);

-- ------------------------------------------------------------
-- 5. Optional traceability columns
-- ------------------------------------------------------------
alter table tms_defects  add column if not exists input_source varchar(20) not null default 'manual';
alter table smms_defects add column if not exists input_source varchar(20) not null default 'manual';
alter table tdms_defects add column if not exists input_source varchar(20) not null default 'manual';
alter table tms_defects  add column if not exists raw_report_text text;
alter table smms_defects add column if not exists raw_report_text text;
alter table tdms_defects add column if not exists raw_report_text text;

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'chk_tms_input_source') then
    alter table tms_defects add constraint chk_tms_input_source
      check (input_source in ('manual','nl_intake','emergency'));
  end if;
  if not exists (select 1 from pg_constraint where conname = 'chk_smms_input_source') then
    alter table smms_defects add constraint chk_smms_input_source
      check (input_source in ('manual','nl_intake','emergency'));
  end if;
  if not exists (select 1 from pg_constraint where conname = 'chk_tdms_input_source') then
    alter table tdms_defects add constraint chk_tdms_input_source
      check (input_source in ('manual','nl_intake','emergency'));
  end if;
end $$;
-- ============================================================
-- Adds shadow-block support. Idempotent. Run after phase1/phase2.
-- ============================================================

alter table blocks add column if not exists block_type varchar(10) not null default 'primary'
  check (block_type in ('primary','shadow'));
alter table blocks add column if not exists parent_block_id uuid references blocks(id);

create index if not exists idx_blocks_parent on blocks(parent_block_id);
-- NOTE: this file is schema/structure only. It does not include
-- seed data (stations, trains, train_schedule, defect records),
-- which already exists in the live Supabase database.
