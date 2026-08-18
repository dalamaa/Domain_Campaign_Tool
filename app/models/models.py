from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Enum, ForeignKey, Integer, String, Date, Boolean, DateTime, UniqueConstraint, Index
from sqlalchemy.orm import relationship, DeclarativeBase
import enum
from datetime import datetime

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

class DomainStatus(enum.Enum):
    AVAILABLE = "AVAILABLE"
    SOLD = "SOLD"
    EXPIRED = "EXPIRED"

class CampaignStatus(enum.Enum):
    DORMANT = "DORMANT"
    ACTIVE = "ACTIVE"
    RESTING = "RESTING"

class ActionType(enum.Enum):
    FIRST_OUTREACH = "FIRST_OUTREACH"
    FIRST_FOLLOW_UP = "FIRST_FOLLOW_UP"
    FOLLOW_UP = "FOLLOW_UP"
    PRICE_REDUCTION = "PRICE_REDUCTION"
    REST_STARTED = "REST_STARTED"
    CAMPAIGN_RESTARTED = "CAMPAIGN_RESTARTED"
    CAMPAIGN_COMPLETED = "CAMPAIGN_COMPLETED"
    FORCE_OVERRIDE = "FORCE_OVERRIDE"
    PARTIAL_OVERRIDE = "PARTIAL_OVERRIDE"

class ReservationStatus(enum.Enum):
    RESERVED = "RESERVED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"

class Domain(db.Model):
    __tablename__ = 'domains'
    id = db.Column(Integer, primary_key=True)
    domain_name = db.Column(String, unique=True, nullable=False, index=True)
    expiry_date = db.Column(Date)
    status = db.Column(String, nullable=False, default="AVAILABLE")
    notes = db.Column(db.Text)
    created_at = db.Column(DateTime, default=datetime.utcnow)
    campaigns = relationship("Campaign", back_populates="domain")

class Campaign(db.Model):
    __tablename__ = 'campaigns'
    id = db.Column(Integer, primary_key=True)
    domain_id = db.Column(Integer, ForeignKey('domains.id'), nullable=False, index=True)
    status = db.Column(Enum(CampaignStatus), nullable=False, index=True)
    start_date = db.Column(Date, nullable=False)
    last_contact_date = db.Column(Date)
    current_price = db.Column(Integer, nullable=False)
    current_sequence = db.Column(Integer, nullable=False)
    rest_start_date = db.Column(Date)
    rest_end_date = db.Column(Date)
    handled_by = db.Column(String)
    last_action = db.Column(String)
    notes = db.Column(db.Text)
    created_at = db.Column(DateTime, default=datetime.utcnow)
    updated_at = db.Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    domain = relationship("Domain", back_populates="campaigns")
    email_blocks = relationship("CampaignEmailBlock", back_populates="campaign")
    reservations = relationship("Reservation", back_populates="campaign")
    history = relationship("CampaignHistory", back_populates="campaign")

class EmailAccount(db.Model):
    __tablename__ = 'email_accounts'
    code = db.Column(String, primary_key=True)
    group = db.Column(String, nullable=False, index=True)
    profile_order = db.Column(Integer, nullable=False, index=True)
    enabled = db.Column(Boolean, default=True)

class CampaignEmailBlock(db.Model):
    __tablename__ = 'campaign_email_blocks'
    id = db.Column(Integer, primary_key=True)
    campaign_id = db.Column(Integer, ForeignKey('campaigns.id'), nullable=False)
    email_code = db.Column(String, ForeignKey('email_accounts.code'), nullable=False)
    
    campaign = relationship("Campaign", back_populates="email_blocks")
    
    __table_args__ = (UniqueConstraint('campaign_id', 'email_code', name='uix_campaign_email'),)

class Reservation(db.Model):
    __tablename__ = 'reservations'
    id = db.Column(Integer, primary_key=True)
    campaign_id = db.Column(Integer, ForeignKey('campaigns.id'), nullable=False)
    date = db.Column(Date, nullable=False)
    status = db.Column(Enum(ReservationStatus), nullable=False)
    is_override = db.Column(Boolean, default=False)
    created_at = db.Column(DateTime, default=datetime.utcnow)
    updated_at = db.Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    campaign = relationship("Campaign", back_populates="reservations")
    email_links = relationship("ReservationEmailLink", back_populates="reservation")

    __table_args__ = (UniqueConstraint('date', 'campaign_id', name='uix_date_campaign'),)

class ReservationEmailLink(db.Model):
    __tablename__ = 'reservation_email_links'
    id = db.Column(Integer, primary_key=True)
    reservation_id = db.Column(Integer, ForeignKey('reservations.id'), nullable=False)
    email_code = db.Column(String, ForeignKey('email_accounts.code'), nullable=False)
    
    reservation = relationship("Reservation", back_populates="email_links")
    
    __table_args__ = (UniqueConstraint('reservation_id', 'email_code', name='uix_reservation_email'),)

class CampaignHistory(db.Model):
    __tablename__ = 'campaign_history'
    id = db.Column(Integer, primary_key=True)
    campaign_id = db.Column(Integer, ForeignKey('campaigns.id'), nullable=False, index=True)
    sequence = db.Column(Integer, index=True)
    action_type = db.Column(Enum(ActionType), nullable=False)
    action_date = db.Column(DateTime, default=datetime.utcnow, index=True)
    edited_at = db.Column(DateTime, nullable=True)
    price_before = db.Column(Integer)
    price_after = db.Column(Integer)
    sequence_before = db.Column(Integer)
    sequence_after = db.Column(Integer)
    notes = db.Column(db.Text)
    
    campaign = relationship("Campaign", back_populates="history")
    __table_args__ = (UniqueConstraint('campaign_id', 'sequence', name='uix_campaign_sequence'),)

class Setting(db.Model):
    __tablename__ = 'settings'
    key = db.Column(String, primary_key=True)
    value = db.Column(String)

