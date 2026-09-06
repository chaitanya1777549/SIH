"""
SQLAlchemy ORM models mirroring database_schema_reference.sql exactly.
No modification of existing tables or columns.
"""
import uuid
from sqlalchemy import (
    Column,
    String,
    Integer,
    Numeric,
    Boolean,
    Text,
    DateTime,
    Date,
    ForeignKey,
    CheckConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from backend.database import Base

class Station(Base):
    __tablename__ = "stations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    station_code = Column(String(10), unique=True, nullable=False)
    station_name = Column(String(100), nullable=False)
    sequence_on_corridor = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class Track(Base):
    __tablename__ = "tracks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    track_code = Column(String(20), unique=True, nullable=False)
    description = Column(String(100))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    gauge_mm = Column(Integer)
    electrified = Column(Boolean, default=True)
    max_speed_kmph = Column(Integer)
    line_class = Column(String(10))

class BlockSection(Base):
    __tablename__ = "block_sections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    section_code = Column(String(30), unique=True, nullable=False)
    from_station_id = Column(UUID(as_uuid=True), ForeignKey("stations.id"), nullable=False)
    to_station_id = Column(UUID(as_uuid=True), ForeignKey("stations.id"), nullable=False)
    track_id = Column(UUID(as_uuid=True), ForeignKey("tracks.id"), nullable=False)
    length_km = Column(Numeric(6, 2))
    sequence_order = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    from_station = relationship("Station", foreign_keys=[from_station_id])
    to_station = relationship("Station", foreign_keys=[to_station_id])
    track = relationship("Track")

class Train(Base):
    __tablename__ = "trains"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    train_number = Column(String(10), unique=True, nullable=False)
    train_name = Column(String(100))
    train_type = Column(String(20))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

class TrainSchedule(Base):
    __tablename__ = "train_schedule"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    train_id = Column(UUID(as_uuid=True), ForeignKey("trains.id"), nullable=False)
    block_section_id = Column(UUID(as_uuid=True), ForeignKey("block_sections.id"), nullable=False)
    service_date = Column(Date, nullable=False)
    scheduled_entry = Column(DateTime(timezone=True), nullable=False)
    scheduled_exit = Column(DateTime(timezone=True), nullable=False)
    forecast_entry = Column(DateTime(timezone=True), nullable=False)
    forecast_exit = Column(DateTime(timezone=True), nullable=False)
    delay_minutes = Column(Integer, default=0, nullable=False)
    status = Column(String(20), default="scheduled", nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    train = relationship("Train")
    block_section = relationship("BlockSection")

class TMSDefect(Base):
    __tablename__ = "tms_defects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    defect_code = Column(String(30), unique=True, nullable=False)
    block_section_id = Column(UUID(as_uuid=True), ForeignKey("block_sections.id"), nullable=False)
    defect_type = Column(String(50), nullable=False)
    description = Column(Text)
    severity = Column(String(20))
    criticality_score = Column(Integer, nullable=False)
    detected_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    required_by = Column(DateTime(timezone=True))
    estimated_duration_min = Column(Integer, nullable=False)
    requires_track_block = Column(Boolean, default=True, nullable=False)
    status = Column(String(20), default="open", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    work_category = Column(String(20), default="defect", nullable=False)
    input_source = Column(String(20), default="manual", nullable=False)
    raw_report_text = Column(Text)

    block_section = relationship("BlockSection")

class SMMSDefect(Base):
    __tablename__ = "smms_defects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    defect_code = Column(String(30), unique=True, nullable=False)
    block_section_id = Column(UUID(as_uuid=True), ForeignKey("block_sections.id"), nullable=False)
    defect_type = Column(String(50), nullable=False)
    description = Column(Text)
    severity = Column(String(20))
    criticality_score = Column(Integer, nullable=False)
    detected_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    required_by = Column(DateTime(timezone=True))
    estimated_duration_min = Column(Integer, nullable=False)
    requires_signal_block = Column(Boolean, default=True, nullable=False)
    status = Column(String(20), default="open", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    work_category = Column(String(20), default="defect", nullable=False)
    input_source = Column(String(20), default="manual", nullable=False)
    raw_report_text = Column(Text)

    block_section = relationship("BlockSection")

class TDMSDefect(Base):
    __tablename__ = "tdms_defects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    defect_code = Column(String(30), unique=True, nullable=False)
    block_section_id = Column(UUID(as_uuid=True), ForeignKey("block_sections.id"), nullable=False)
    defect_type = Column(String(50), nullable=False)
    description = Column(Text)
    severity = Column(String(20))
    criticality_score = Column(Integer, nullable=False)
    detected_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    required_by = Column(DateTime(timezone=True))
    estimated_duration_min = Column(Integer, nullable=False)
    requires_power_block = Column(Boolean, default=True, nullable=False)
    status = Column(String(20), default="open", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    work_category = Column(String(20), default="defect", nullable=False)
    input_source = Column(String(20), default="manual", nullable=False)
    raw_report_text = Column(Text)

    block_section = relationship("BlockSection")

class BlockRequest(Base):
    __tablename__ = "block_requests"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_system = Column(String(10), nullable=False)
    tms_defect_id = Column(UUID(as_uuid=True), ForeignKey("tms_defects.id"))
    smms_defect_id = Column(UUID(as_uuid=True), ForeignKey("smms_defects.id"))
    tdms_defect_id = Column(UUID(as_uuid=True), ForeignKey("tdms_defects.id"))
    block_section_id = Column(UUID(as_uuid=True), ForeignKey("block_sections.id"), nullable=False)
    criticality_score = Column(Integer, nullable=False)
    required_by = Column(DateTime(timezone=True))
    estimated_duration_min = Column(Integer, nullable=False)
    requires_power_block = Column(Boolean, default=False, nullable=False)
    requires_signal_block = Column(Boolean, default=False, nullable=False)
    status = Column(String(20), default="pending", nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    is_emergency = Column(Boolean, default=False, nullable=False)

    block_section = relationship("BlockSection")
    tms_defect = relationship("TMSDefect")
    smms_defect = relationship("SMMSDefect")
    tdms_defect = relationship("TDMSDefect")

class Block(Base):
    __tablename__ = "blocks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    block_request_id = Column(UUID(as_uuid=True), ForeignKey("block_requests.id"), nullable=False)
    block_section_id = Column(UUID(as_uuid=True), ForeignKey("block_sections.id"), nullable=False)
    planned_start = Column(DateTime(timezone=True), nullable=False)
    planned_end = Column(DateTime(timezone=True), nullable=False)
    status = Column(String(20), default="active", nullable=False)
    optimization_run_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    block_type = Column(String(10), default="primary", nullable=False)
    parent_block_id = Column(UUID(as_uuid=True), ForeignKey("blocks.id"))

    block_request = relationship("BlockRequest")
    block_section = relationship("BlockSection")
    parent_block = relationship("Block", remote_side=[id])

class BlockAllocationHistory(Base):
    __tablename__ = "block_allocation_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    block_id = Column(UUID(as_uuid=True), ForeignKey("blocks.id"))
    block_request_id = Column(UUID(as_uuid=True), ForeignKey("block_requests.id"), nullable=False)
    block_section_id = Column(UUID(as_uuid=True), ForeignKey("block_sections.id"), nullable=False)
    previous_start = Column(DateTime(timezone=True))
    previous_end = Column(DateTime(timezone=True))
    new_start = Column(DateTime(timezone=True))
    new_end = Column(DateTime(timezone=True))
    reason = Column(String(50), nullable=False)
    changed_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    block = relationship("Block")
    block_request = relationship("BlockRequest")
    block_section = relationship("BlockSection")

class EmergencyIncident(Base):
    __tablename__ = "emergency_incidents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_system = Column(String(10), nullable=False)
    tms_defect_id = Column(UUID(as_uuid=True), ForeignKey("tms_defects.id"))
    smms_defect_id = Column(UUID(as_uuid=True), ForeignKey("smms_defects.id"))
    tdms_defect_id = Column(UUID(as_uuid=True), ForeignKey("tdms_defects.id"))
    block_section_id = Column(UUID(as_uuid=True), ForeignKey("block_sections.id"), nullable=False)
    reported_text = Column(Text, nullable=False)
    status = Column(String(20), default="reported", nullable=False)
    recommended_action = Column(String(20))
    controller_decision = Column(String(20))
    block_request_id = Column(UUID(as_uuid=True), ForeignKey("block_requests.id"))
    confirmed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    block_section = relationship("BlockSection")
    block_request = relationship("BlockRequest")

