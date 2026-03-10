from fastapi import FastAPI, Depends, HTTPException, Security, status
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, text, Column, Integer, String, Float, Boolean
from sqlalchemy.orm import declarative_base, sessionmaker, Session
import datetime
from typing import List, Optional

# ---------------------------------------------------------
# FASTAPI APP INITIALIZATION
# ---------------------------------------------------------
app = FastAPI(title="DWF Banking System API")

# Allow Frontend to communicate with Backend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------
# SECURITY
# ---------------------------------------------------------
API_KEY = "DWF_SECRET_KEY_2026" 
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

def get_api_key(api_key: str = Security(api_key_header)):
    if api_key == API_KEY:
        return api_key
    raise HTTPException(status_code=403, detail="Could not validate credentials")

# ---------------------------------------------------------
# DATABASE SETUP (Connecting to your Supabase!)
# ---------------------------------------------------------
# This is where your backend connects to Supabase
DATABASE_URL = "postgresql://postgres.yzvjutqqujbpvalelbld:jorsavantcally15@aws-1-eu-central-1.pooler.supabase.com:5432/postgres"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------------------------------------------------------
# SQL DATABASE TABLES
# ---------------------------------------------------------
class DWFMember(Base):
    __tablename__ = "dwf_members"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    status = Column(String, default="Active")

class DWFContribution(Base):
    __tablename__ = "dwf_contributions"
    id = Column(Integer, primary_key=True, index=True)
    member_name = Column(String, nullable=False)
    month = Column(String, nullable=False) 
    year = Column(Integer, nullable=False)
    date_paid = Column(String, nullable=True) 
    amount = Column(Float, default=0.0)
    fine = Column(Float, default=0.0)
    fine_paid = Column(Boolean, default=False)

class DWFLoanRequest(Base):
    __tablename__ = "dwf_loan_requests"
    id = Column(Integer, primary_key=True, index=True)
    member_name = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    date_requested = Column(String, nullable=False)
    status = Column(String, default="PENDING") 

class DWFLoan(Base):
    __tablename__ = "dwf_loans"
    id = Column(Integer, primary_key=True, index=True)
    member_name = Column(String, nullable=False)
    principal = Column(Float, nullable=False)
    interest_rate = Column(Float, nullable=False)
    date_issued = Column(String, nullable=False)
    status = Column(String, default="ACTIVE") 

class DWFLog(Base):
    __tablename__ = "dwf_logs"
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(String, nullable=False)
    message = Column(String, nullable=False)

class DWFSettings(Base):
    __tablename__ = "dwf_settings"
    id = Column(Integer, primary_key=True, index=True)
    multiplier = Column(Float, default=3.0)
    cutoff_day = Column(Integer, default=28)
    fine_amount = Column(Float, default=5000.0)
    interest_rate = Column(Float, default=0.1)
    reserve_ratio = Column(Float, default=0.2)

# Automatically create tables in Supabase if they don't exist
Base.metadata.create_all(bind=engine)

def init_db_defaults():
    db = SessionLocal()
    if not db.query(DWFSettings).first():
        db.add(DWFSettings())
    if db.query(DWFMember).count() == 0:
        for name in ["Josephine", "Joram", "Belkia", "Rehema", "Jackie"]:
            db.add(DWFMember(name=name))
    db.commit()
    db.close()

init_db_defaults()

# ---------------------------------------------------------
# DATA SCHEMAS
# ---------------------------------------------------------
class MemberSchema(BaseModel):
    name: str

class ContributionSchema(BaseModel):
    member_name: str
    month: str
    year: int
    date_paid: Optional[str] = None
    amount: float
    fine: float
    fine_paid: bool

class LoanRequestSchema(BaseModel):
    member_name: str
    amount: float

class LoanSchema(BaseModel):
    member_name: str
    principal: float
    interest_rate: float

class SettingsSchema(BaseModel):
    multiplier: float
    cutoff_day: int
    fine_amount: float
    interest_rate: float
    reserve_ratio: float

class LogSchema(BaseModel):
    message: str

# ---------------------------------------------------------
# API ENDPOINTS
# ---------------------------------------------------------
@app.get("/")
def read_root():
    return {"message": "DWF Backend is Live and Connected to Supabase"}

@app.get("/api/sync")
def sync_all_data(year: int = 2026, db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
    members = db.query(DWFMember).filter(DWFMember.status == "Active").all()
    member_names = [m.name for m in members]
    settings = db.query(DWFSettings).first()
    contribs_data = db.query(DWFContribution).filter(DWFContribution.year == year).all()
    
    contribs_dict = {name: {} for name in member_names}
    for c in contribs_data:
        if c.member_name in contribs_dict:
            contribs_dict[c.member_name][c.month] = {
                "amount": c.amount, "fine": c.fine, "date": c.date_paid, "finePaid": c.fine_paid
            }
            
    loans = db.query(DWFLoan).filter(DWFLoan.status == "ACTIVE").all()
    requests = db.query(DWFLoanRequest).filter(DWFLoanRequest.status == "PENDING").all()
    logs = db.query(DWFLog).order_by(DWFLog.id.desc()).limit(100).all()

    return {
        "members": member_names,
        "settings": {
            "multiplier": settings.multiplier, "cutoffDay": settings.cutoff_day,
            "fineAmt": settings.fine_amount, "interest": settings.interest_rate, "reserveRatio": settings.reserve_ratio
        },
        "contribs": contribs_dict,
        "loans": [{"id": l.id, "member": l.member_name, "amt": l.principal} for l in loans],
        "requests": [{"id": r.id, "member": r.member_name, "amount": r.amount, "date": r.date_requested, "status": r.status} for r in requests],
        "logs": [{"time": l.timestamp, "msg": l.message} for l in logs]
    }

@app.post("/api/contributions")
def update_contribution(data: ContributionSchema, db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
    contrib = db.query(DWFContribution).filter(
        DWFContribution.member_name == data.member_name, DWFContribution.month == data.month, DWFContribution.year == data.year
    ).first()

    if contrib:
        contrib.date_paid = data.date_paid
        contrib.amount = data.amount
        contrib.fine = data.fine
        contrib.fine_paid = data.fine_paid
    else:
        new_contrib = DWFContribution(**data.dict())
        db.add(new_contrib)
    db.commit()
    return {"message": "Contribution updated"}

@app.post("/api/logs")
def add_log(data: LogSchema, db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
    new_log = DWFLog(timestamp=datetime.datetime.now().strftime("%m/%d/%Y %H:%M:%S"), message=data.message)
    db.add(new_log)
    db.commit()
    return {"message": "Logged"}
