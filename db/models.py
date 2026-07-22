"""
Heuristic Shadow Agent - Database Models
SQLAlchemy ORM models matching the PRD schema.
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Text, Boolean, DateTime, ForeignKey, create_engine
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

Base = declarative_base()


class RawEvent(Base):
    """Captured OS interaction events (mouse clicks, keypresses, app switches)."""

    __tablename__ = "raw_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    event_type = Column(String(32), nullable=False, index=True)
    process_name = Column(String(256), nullable=True)
    window_title = Column(String(512), nullable=True)
    x_coord = Column(Integer, nullable=True)
    y_coord = Column(Integer, nullable=True)
    key_name = Column(String(64), nullable=True)
    ocr_text = Column(Text, nullable=True)
    is_sensitive = Column(Boolean, default=False)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "event_type": self.event_type,
            "process_name": self.process_name,
            "window_title": self.window_title,
            "x_coord": self.x_coord,
            "y_coord": self.y_coord,
            "key_name": self.key_name,
            "ocr_text": self.ocr_text,
            "is_sensitive": self.is_sensitive,
        }

    def __repr__(self) -> str:
        return (
            f"<RawEvent(id={self.id}, type={self.event_type}, "
            f"process={self.process_name}, ts={self.timestamp})>"
        )


class DetectedPattern(Base):
    """Detected repetitive user workflow patterns with confidence scoring."""

    __tablename__ = "detected_patterns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pattern_hash = Column(String(64), unique=True, nullable=False, index=True)
    pattern_name = Column(String(256), nullable=True)
    frequency_count = Column(Integer, default=1)
    confidence_score = Column(Float, default=0.0)
    sequence_json = Column(Text, nullable=False)
    status = Column(
        String(32), default="discovered", index=True
    )
    discovered_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    scripts = relationship("AutomationScript", back_populates="pattern", cascade="all, delete-orphan")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "pattern_hash": self.pattern_hash,
            "pattern_name": self.pattern_name,
            "frequency_count": self.frequency_count,
            "confidence_score": self.confidence_score,
            "sequence_json": self.sequence_json,
            "status": self.status,
            "discovered_at": self.discovered_at.isoformat() if self.discovered_at else None,
        }

    def __repr__(self) -> str:
        return (
            f"<DetectedPattern(id={self.id}, hash={self.pattern_hash}, "
            f"confidence={self.confidence_score:.2f}, status={self.status})>"
        )


class AutomationScript(Base):
    """Generated automation scripts from detected patterns."""

    __tablename__ = "automation_scripts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    pattern_id = Column(Integer, ForeignKey("detected_patterns.id"), nullable=False)
    script_name = Column(String(256), nullable=False)
    script_description = Column(Text, nullable=True)
    python_code = Column(Text, nullable=False)
    assigned_hotkey = Column(String(64), nullable=True)
    execution_count = Column(Integer, default=0)
    is_active = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_executed = Column(DateTime, nullable=True)

    pattern = relationship("DetectedPattern", back_populates="scripts")

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "pattern_id": self.pattern_id,
            "script_name": self.script_name,
            "script_description": self.script_description,
            "python_code": self.python_code,
            "assigned_hotkey": self.assigned_hotkey,
            "execution_count": self.execution_count,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_executed": self.last_executed.isoformat() if self.last_executed else None,
        }

    def __repr__(self) -> str:
        return (
            f"<AutomationScript(id={self.id}, name={self.script_name}, "
            f"active={self.is_active}, executions={self.execution_count})>"
        )


class AppSetting(Base):
    """Application settings key-value store."""

    __tablename__ = "settings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(128), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    description = Column(String(512), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
