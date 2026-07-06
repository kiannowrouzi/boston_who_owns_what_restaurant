"""Ownership-graph schema (spec §2).

All six entities exist from day one so later milestones (brand clustering,
research pipeline, likelihood engine) need no migrations. Only cross-DB
column types are used — this schema must run identically on SQLite and
Postgres (spec §7: Stage 1 → Stage 2 carries the DB over intact).
"""

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    String,
    Table,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class ParentType(enum.Enum):
    independent = "independent"
    restaurant_group = "restaurant_group"
    private_equity = "private_equity"
    strategic = "strategic"
    public_co = "public_co"
    unknown = "unknown"


class InvestorType(enum.Enum):
    pe = "pe"
    vc = "vc"
    growth_equity = "growth_equity"
    family_office = "family_office"
    strategic = "strategic"


class SubjectType(enum.Enum):
    location = "location"
    brand = "brand"


class AssessmentStatus(enum.Enum):
    confirmed_pe = "confirmed_pe"
    confirmed_independent = "confirmed_independent"
    estimated = "estimated"


location_sources = Table(
    "location_sources",
    Base.metadata,
    Column("location_id", ForeignKey("locations.id"), primary_key=True),
    Column("source_id", ForeignKey("sources.id"), primary_key=True),
)

assessment_evidence = Table(
    "assessment_evidence",
    Base.metadata,
    Column("assessment_id", ForeignKey("assessments.id"), primary_key=True),
    Column("source_id", ForeignKey("sources.id"), primary_key=True),
)


class Location(Base):
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, index=True)
    address = Column(String(255))
    lat = Column(Float)
    lng = Column(Float)
    neighborhood = Column(String(100), index=True)
    cuisine = Column(String(100))
    price_tier = Column(String(20))
    brand_id = Column(ForeignKey("brands.id"), index=True)
    # From the city licensing data; property_id + name is the seed upsert key.
    license_category = Column(String(100))
    property_id = Column(String(50), index=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    brand = relationship("Brand", back_populates="locations")
    sources = relationship("Source", secondary=location_sources, back_populates="locations")


class Brand(Base):
    __tablename__ = "brands"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, index=True)
    location_count = Column(Integer, default=1)
    founded_year = Column(Integer)
    website = Column(String(255))
    parent_id = Column(ForeignKey("parents.id"))
    group_id = Column(String(50))

    locations = relationship("Location", back_populates="brand")
    parent = relationship("Parent", back_populates="brands")


class Parent(Base):
    __tablename__ = "parents"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    type = Column(Enum(ParentType, native_enum=False), default=ParentType.unknown, nullable=False)
    notes = Column(Text)

    brands = relationship("Brand", back_populates="parent")
    investors = relationship("Investor", secondary="parent_investors", back_populates="parents")


parent_investors = Table(
    "parent_investors",
    Base.metadata,
    Column("parent_id", ForeignKey("parents.id"), primary_key=True),
    Column("investor_id", ForeignKey("investors.id"), primary_key=True),
)


class Investor(Base):
    __tablename__ = "investors"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    type = Column(Enum(InvestorType, native_enum=False), nullable=False)
    website = Column(String(255))

    parents = relationship("Parent", secondary=parent_investors, back_populates="investors")


class Assessment(Base):
    __tablename__ = "assessments"

    id = Column(Integer, primary_key=True)
    subject_id = Column(Integer, nullable=False, index=True)
    subject_type = Column(Enum(SubjectType, native_enum=False), nullable=False)
    status = Column(Enum(AssessmentStatus, native_enum=False), nullable=False)
    likelihood_low = Column(Float)
    likelihood_high = Column(Float)
    label = Column(String(20))  # Confirmed | Likely | Possible | Unlikely
    reasoning = Column(JSON, default=list)  # list of human-readable signal strings
    model_version = Column(String(20), nullable=False)
    computed_at = Column(DateTime, default=utcnow, nullable=False)

    evidence = relationship("Source", secondary=assessment_evidence, back_populates="assessments")


class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True)
    url = Column(String(2000), nullable=False)
    publisher = Column(String(255))
    title = Column(String(500))
    excerpt = Column(Text)
    retrieved_at = Column(DateTime)
    verified_by_human = Column(Boolean, default=False, nullable=False)
    verified_at = Column(DateTime)

    locations = relationship("Location", secondary=location_sources, back_populates="sources")
    assessments = relationship("Assessment", secondary=assessment_evidence, back_populates="evidence")
