import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)

convention = {
    'ix': 'ix_%(column_0_label)s',
    'uq': 'uq_%(table_name)s_%(column_0_name)s',
    'ck': 'ck_%(table_name)s_%(constraint_name)s',
    'fk': 'fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s',
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=convention)


# DEMOGRAPHIC / PATIENT
class Demographic(Base):
    __tablename__ = 'demographic'
    __table_args__ = (
        CheckConstraint('age BETWEEN 0 AND 120', name='age_check'),
        CheckConstraint(
            "gender IN ('male', 'female', 'other')", name='gender_check'
        ),
        CheckConstraint(
            "marital_status IN ('single', 'married', 'divorced', "
            "'widowed')",
            name='marital_status_check',
        ),
        CheckConstraint("location IN ('north', 'central', 'south')",
                        name='location_check'),
        CheckConstraint(
            "residence_type IN ('urban', 'rural', 'suburban')",
            name='residence_type_check',
        ),
        CheckConstraint(
            "income_level IN ('low', 'middle', 'high')",
            name='income_level_check',
        ),
    )

    demo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text('uuid_generate_v4()'),
    )
    age: Mapped[int] = mapped_column(Integer, nullable=False)
    gender: Mapped[str] = mapped_column(String(20), nullable=False)
    marital_status: Mapped[str | None] = mapped_column(String(30))
    location: Mapped[str | None] = mapped_column(String(20))
    occupation: Mapped[str | None] = mapped_column(String(100))
    residence_type: Mapped[str | None] = mapped_column(String(20))
    income_level: Mapped[str | None] = mapped_column(String(20))
    family_history_stroke: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text('FALSE')
    )
    family_history_cvd: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text('FALSE')
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    ehr_records: Mapped[list['EHR']] = relationship(
        back_populates='demographic', cascade='all, delete-orphan'
    )
    lifestyle_records: Mapped[list['Lifestyle']] = relationship(
        back_populates='demographic', cascade='all, delete-orphan'
    )
    vital_records: Mapped[list['VitalSigns']] = relationship(
        back_populates='demographic', cascade='all, delete-orphan'
    )
    sleep_records: Mapped[list['SleepCycle']] = relationship(
        back_populates='demographic', cascade='all, delete-orphan'
    )
    activity_records: Mapped[list['PhysicalActivity']] = relationship(
        back_populates='demographic', cascade='all, delete-orphan'
    )
    stroke_records: Mapped[list['StrokeHistory']] = relationship(
        back_populates='demographic', cascade='all, delete-orphan'
    )


# EHR
class EHR(Base):
    __tablename__ = 'ehr'
    __table_args__ = (
        CheckConstraint(
            'height_cm IS NULL OR height_cm BETWEEN 30 AND 250',
            name='height_cm_check',
        ),
        CheckConstraint(
            'weight_kg IS NULL OR weight_kg BETWEEN 1 AND 400',
            name='weight_kg_check',
        ),
        CheckConstraint(
            'fasting_glucose IS NULL OR fasting_glucose BETWEEN 40 AND 600',
            name='fasting_glucose_check',
        ),
        CheckConstraint(
            'hba1c IS NULL OR hba1c BETWEEN 3 AND 20', name='hba1c_check'
        ),
        CheckConstraint(
            'total_cholesterol IS NULL OR total_cholesterol '
            'BETWEEN 50 AND 500',
            name='total_cholesterol_check',
        ),
        CheckConstraint(
            'ldl IS NULL OR ldl BETWEEN 20 AND 400', name='ldl_check'
        ),
        CheckConstraint(
            'hdl IS NULL OR hdl BETWEEN 10 AND 150', name='hdl_check'
        ),
        Index(
            'idx_ehr_demo_encounter', 'demo_id', text('encounter_date DESC')
        ),
    )

    ehr_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text('uuid_generate_v4()'),
    )
    demo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('demographic.demo_id', ondelete='CASCADE'),
        nullable=False,
    )
    encounter_date: Mapped[datetime] = mapped_column(
        DateTime, nullable=False
    )
    height_cm: Mapped[float | None] = mapped_column(Numeric(5, 2))
    weight_kg: Mapped[float | None] = mapped_column(Numeric(6, 2))
    is_diabetes: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text('FALSE')
    )
    is_heart_disease: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text('FALSE')
    )
    is_kidney_disease: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text('FALSE')
    )
    fasting_glucose: Mapped[float | None] = mapped_column(Numeric(6, 2))
    hba1c: Mapped[float | None] = mapped_column(Numeric(4, 2))
    total_cholesterol: Mapped[float | None] = mapped_column(Numeric(6, 2))
    ldl: Mapped[float | None] = mapped_column(Numeric(6, 2))
    hdl: Mapped[float | None] = mapped_column(Numeric(6, 2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    demographic: Mapped['Demographic'] = relationship(
        back_populates='ehr_records'
    )


Index('idx_ehr_demo_id', EHR.demo_id)
Index('idx_ehr_encounter_date', EHR.encounter_date)


# LIFESTYLE
class Lifestyle(Base):
    __tablename__ = 'lifestyle'
    __table_args__ = (
        CheckConstraint(
            'alcohol_consumption_frequency IS NULL '
            'OR alcohol_consumption_frequency BETWEEN 0 AND 50',
            name='alcohol_consumption_frequency_check',
        ),
        CheckConstraint(
            "cooking_method IN ('fried_stir_fried', 'grilled', "
            "'boiled', 'steamed')",
            name='cooking_method_check',
        ),
        CheckConstraint(
            "diet_taste_preference IN ('salty', 'spicy', 'sour', "
            "'bitter', 'sweet', 'moderate')",
            name='diet_taste_preference_check',
        ),
        CheckConstraint(
            "diet_type IN ('vegetable', 'meat', 'seafood', 'balanced')",
            name='diet_type_check',
        ),
        Index('idx_lifestyle_demo_id', 'demo_id'),
        Index('idx_lifestyle_recorded_at', 'recorded_at'),
    )

    lifestyle_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text('uuid_generate_v4()'),
    )
    demo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('demographic.demo_id', ondelete='CASCADE'),
        nullable=False,
    )
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    smoking: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text('FALSE')
    )
    alcohol_consumption_frequency: Mapped[int | None] = mapped_column(Integer)
    cooking_method: Mapped[str | None] = mapped_column(String(30))
    diet_taste_preference: Mapped[str | None] = mapped_column(String(20))
    diet_type: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    demographic: Mapped['Demographic'] = relationship(
        back_populates='lifestyle_records'
    )


# VITAL SIGNS
class VitalSigns(Base):
    __tablename__ = 'vital_signs'
    __table_args__ = (
        CheckConstraint(
            'heart_rate IS NULL OR heart_rate BETWEEN 20 AND 250',
            name='heart_rate_check',
        ),
        CheckConstraint(
            'spo2 IS NULL OR spo2 BETWEEN 0 AND 100', name='spo2_check'
        ),
        CheckConstraint(
            'temperature IS NULL OR temperature BETWEEN 30 AND 45',
            name='temperature_check',
        ),
        Index('idx_vital_demo_time', 'demo_id', text('measured_at DESC')),
    )

    vital_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text('uuid_generate_v4()'),
    )
    demo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('demographic.demo_id', ondelete='CASCADE'),
        nullable=False,
    )
    measured_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    heart_rate: Mapped[int | None] = mapped_column(Integer)
    spo2: Mapped[float | None] = mapped_column(Numeric(5, 2))
    temperature: Mapped[float | None] = mapped_column(Numeric(4, 2))
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    demographic: Mapped['Demographic'] = relationship(
        back_populates='vital_records'
    )


Index('idx_vital_demo_id', VitalSigns.demo_id)
Index('idx_vital_measured_at', VitalSigns.measured_at)


# SLEEP CYCLE
class SleepCycle(Base):
    __tablename__ = 'sleep_cycle'
    __table_args__ = (
        CheckConstraint('sleep_end > sleep_start', name='sleep_time_check'),
        Index('idx_sleep_demo_id', 'demo_id'),
        Index('idx_sleep_start', 'sleep_start'),
    )

    sleep_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text('uuid_generate_v4()'),
    )
    demo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('demographic.demo_id', ondelete='CASCADE'),
        nullable=False,
    )
    sleep_start: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    sleep_end: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    is_wake_sudden: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text('FALSE')
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    demographic: Mapped['Demographic'] = relationship(
        back_populates='sleep_records'
    )


# PHYSICAL ACTIVITIES
class PhysicalActivity(Base):
    __tablename__ = 'physical_activities'
    __table_args__ = (
        CheckConstraint(
            'duration_minutes IS NULL OR duration_minutes BETWEEN 0 AND 1440',
            name='duration_minutes_check',
        ),
        CheckConstraint(
            'calories IS NULL OR calories >= 0', name='calories_check'
        ),
        CheckConstraint(
            'distance_km IS NULL OR distance_km >= 0',
            name='distance_km_check',
        ),
        CheckConstraint(
            "activity_type IN ('walking', 'running', 'cycling', "
            "'swimming', 'gym', 'yoga', 'football', 'other')",
            name='activity_type_check',
        ),
        Index('idx_activity_demo_id', 'demo_id'),
        Index('idx_activity_time', 'activity_time'),
    )

    activity_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text('uuid_generate_v4()'),
    )
    demo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('demographic.demo_id', ondelete='CASCADE'),
        nullable=False,
    )
    activity_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    calories: Mapped[float | None] = mapped_column(Numeric(8, 2))
    distance_km: Mapped[float | None] = mapped_column(Numeric(8, 3))
    activity_type: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    demographic: Mapped['Demographic'] = relationship(
        back_populates='activity_records'
    )


# STROKE HISTORY
class StrokeHistory(Base):
    __tablename__ = 'stroke_history'
    __table_args__ = (
        CheckConstraint('stroke_sequence >= 1', name='stroke_sequence_check'),
        UniqueConstraint(
            'demo_id', 'stroke_sequence', name='uq_patient_stroke_sequence'
        ),
        Index('idx_stroke_demo_id', 'demo_id'),
        Index('idx_stroke_time', 'stroke_time'),
    )

    stroke_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text('uuid_generate_v4()'),
    )
    demo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey('demographic.demo_id', ondelete='CASCADE'),
        nullable=False,
    )
    stroke_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    stroke_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )

    demographic: Mapped['Demographic'] = relationship(
        back_populates='stroke_records'
    )
