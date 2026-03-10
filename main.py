from fastapi import FastAPI, Depends, HTTPException, Security, status
from fastapi.security.api_key import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine, text, Column, Integer, String, Float, Boolean, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, Session
import datetime
from typing import List, Optional

# ---------------------------------------------------------
# FASTAPI APP INITIALIZATION
# ---------------------------------------------------------
app = FastAPI(title="DWF Banking System API")

# Allow CORS for frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this to your specific frontend URL in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------
# SECURITY
# ---------------------------------------------------------
API_KEY = "DWF_SECRET_KEY_2026"  # Make sure this matches the frontend
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

def get_api_key(api_key: str = Security(api_key_header)):
    if api_key == API_KEY:
        return api_key
    raise HTTPException(status_code=403, detail="Could not validate credentials")

# ---------------------------------------------------------
# DATABASE SETUP (Supabase)
# ---------------------------------------------------------
DATABASE_URL = "postgresql://postgres.yzvjutqqujbpvalelbld:jorsavantcally15@aws-1-eu-central-1.pooler.supabase.com:5432/postgres"

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- Dependency to get DB session ---
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ---------------------------------------------------------
# SQLALCHEMY MODELS (Database Tables)
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
    month = Column(String, nullable=False) # e.g., "Jan", "Feb"
    year = Column(Integer, nullable=False)
    date_paid = Column(String, nullable=True) # YYYY-MM-DD
    amount = Column(Float, default=0.0)
    fine = Column(Float, default=0.0)
    fine_paid = Column(Boolean, default=False)

class DWFLoanRequest(Base):
    __tablename__ = "dwf_loan_requests"
    id = Column(Integer, primary_key=True, index=True)
    member_name = Column(String, nullable=False)
    amount = Column(Float, nullable=False)
    date_requested = Column(String, nullable=False)
    status = Column(String, default="PENDING") # PENDING, APPROVED, REJECTED

class DWFLoan(Base):
    __tablename__ = "dwf_loans"
    id = Column(Integer, primary_key=True, index=True)
    member_name = Column(String, nullable=False)
    principal = Column(Float, nullable=False)
    interest_rate = Column(Float, nullable=False)
    date_issued = Column(String, nullable=False)
    status = Column(String, default="ACTIVE") # ACTIVE, REPAID

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

# Create tables if they don't exist
Base.metadata.create_all(bind=engine)

# Initialize settings and default members if empty
def init_db_defaults():
    db = SessionLocal()
    # Check Settings
    if not db.query(DWFSettings).first():
        default_settings = DWFSettings()
        db.add(default_settings)
    
    # Check Members
    if db.query(DWFMember).count() == 0:
        default_members = ["Josephine", "Joram", "Belkia", "Rehema", "Jackie"]
        for name in default_members:
            db.add(DWFMember(name=name))
    
    db.commit()
    db.close()

init_db_defaults()

# ---------------------------------------------------------
# PYDANTIC SCHEMAS (API Input/Output)
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

@app.get("/test-db")
def test_db_connection():
    return {"status": "SUCCESS", "message": "DWF Backend is online."}

# --- MEMBERS ---
@app.get("/api/members")
def get_members(db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
    members = db.query(DWFMember).filter(DWFMember.status == "Active").all()
    return [{"name": m.name} for m in members]

@app.post("/api/members")
def add_member(member: MemberSchema, db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
    if db.query(DWFMember).filter(DWFMember.name == member.name).first():
        raise HTTPException(status_code=400, detail="Member already exists")
    new_member = DWFMember(name=member.name)
    db.add(new_member)
    
    log = DWFLog(timestamp=datetime.datetime.now().strftime("%m/%d/%Y %H:%M:%S"), message=f"Admin: Added new member {member.name}")
    db.add(log)
    db.commit()
    return {"message": "Member added successfully"}

@app.delete("/api/members/{name}")
def remove_member(name: str, db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
    member = db.query(DWFMember).filter(DWFMember.name == name).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    member.status = "Removed"
    
    log = DWFLog(timestamp=datetime.datetime.now().strftime("%m/%d/%Y %H:%M:%S"), message=f"Admin: Removed member {name}")
    db.add(log)
    db.commit()
    return {"message": "Member removed"}

# --- CONTRIBUTIONS ---
@app.get("/api/contributions")
def get_contributions(year: int, month: str, db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
    contribs = db.query(DWFContribution).filter(DWFContribution.year == year, DWFContribution.month == month).all()
    return contribs

@app.post("/api/contributions")
def update_contribution(data: ContributionSchema, db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
    contrib = db.query(DWFContribution).filter(
        DWFContribution.member_name == data.member_name,
        DWFContribution.month == data.month,
        DWFContribution.year == data.year
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

# --- LOAN REQUESTS ---
@app.get("/api/loan-requests")
def get_loan_requests(db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
    requests = db.query(DWFLoanRequest).filter(DWFLoanRequest.status == "PENDING").all()
    return requests

@app.post("/api/loan-requests")
def create_loan_request(data: LoanRequestSchema, db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
    new_req = DWFLoanRequest(
        member_name=data.member_name,
        amount=data.amount,
        date_requested=datetime.datetime.now().strftime("%m/%d/%Y")
    )
    db.add(new_req)
    db.commit()
    return {"message": "Loan request submitted"}

@app.put("/api/loan-requests/{req_id}/approve")
def approve_loan_request(req_id: int, db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
    req = db.query(DWFLoanRequest).filter(DWFLoanRequest.id == req_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    req.status = "APPROVED"
    db.commit()
    return {"message": "Request approved"}

# --- ACTIVE LOANS ---
@app.get("/api/loans")
def get_loans(db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
    loans = db.query(DWFLoan).filter(DWFLoan.status == "ACTIVE").all()
    return loans

@app.post("/api/loans")
def issue_loan(data: LoanSchema, db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
    new_loan = DWFLoan(
        member_name=data.member_name,
        principal=data.principal,
        interest_rate=data.interest_rate,
        date_issued=datetime.datetime.now().strftime("%m/%d/%Y")
    )
    db.add(new_loan)
    
    log = DWFLog(timestamp=datetime.datetime.now().strftime("%m/%d/%Y %H:%M:%S"), message=f"Credit Creation: Issued loan of {data.principal} to {data.member_name}.")
    db.add(log)
    
    db.commit()
    return {"message": "Loan issued"}

@app.put("/api/loans/{loan_id}/repay")
def repay_loan(loan_id: int, db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
    loan = db.query(DWFLoan).filter(DWFLoan.id == loan_id).first()
    if not loan:
        raise HTTPException(status_code=404, detail="Loan not found")
    loan.status = "REPAID"
    
    log = DWFLog(timestamp=datetime.datetime.now().strftime("%m/%d/%Y %H:%M:%S"), message=f"Repayment: {loan.member_name} cleared loan.")
    db.add(log)
    
    db.commit()
    return {"message": "Loan repaid"}

# --- LOGS ---
@app.get("/api/logs")
def get_logs(limit: int = 50, db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
    logs = db.query(DWFLog).order_by(DWFLog.id.desc()).limit(limit).all()
    return logs

@app.post("/api/logs")
def add_log(data: LogSchema, db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
    new_log = DWFLog(
        timestamp=datetime.datetime.now().strftime("%m/%d/%Y %H:%M:%S"),
        message=data.message
    )
    db.add(new_log)
    db.commit()
    return {"message": "Logged"}

# --- SETTINGS ---
@app.get("/api/settings")
def get_settings(db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
    settings = db.query(DWFSettings).first()
    return settings

@app.post("/api/settings")
def update_settings(data: SettingsSchema, db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
    settings = db.query(DWFSettings).first()
    if settings:
        settings.multiplier = data.multiplier
        settings.cutoff_day = data.cutoff_day
        settings.fine_amount = data.fine_amount
        settings.interest_rate = data.interest_rate
        settings.reserve_ratio = data.reserve_ratio
    
    log = DWFLog(timestamp=datetime.datetime.now().strftime("%m/%d/%Y %H:%M:%S"), message="Configuration: Settings updated by Admin")
    db.add(log)
    
    db.commit()
    return {"message": "Settings updated"}

# --- FULL SYNC (For Frontend initialization) ---
@app.get("/api/sync")
def sync_all_data(year: int, db: Session = Depends(get_db), api_key: str = Depends(get_api_key)):
    members = db.query(DWFMember).filter(DWFMember.status == "Active").all()
    member_names = [m.name for m in members]
    
    settings = db.query(DWFSettings).first()
    
    contribs_data = db.query(DWFContribution).filter(DWFContribution.year == year).all()
    # Format contribs into the nested dictionary structure expected by the frontend: {member: {month: data}}
    contribs_dict = {name: {} for name in member_names}
    for c in contribs_data:
        if c.member_name in contribs_dict:
            contribs_dict[c.member_name][c.month] = {
                "amount": c.amount,
                "fine": c.fine,
                "date": c.date_paid,
                "finePaid": c.fine_paid
            }
            
    loans = db.query(DWFLoan).filter(DWFLoan.status == "ACTIVE").all()
    requests = db.query(DWFLoanRequest).filter(DWFLoanRequest.status == "PENDING").all()
    logs = db.query(DWFLog).order_by(DWFLog.id.desc()).limit(100).all()

    return {
        "members": member_names,
        "settings": {
            "multiplier": settings.multiplier,
            "cutoffDay": settings.cutoff_day,
            "fineAmt": settings.fine_amount,
            "interest": settings.interest_rate,
            "reserveRatio": settings.reserve_ratio
        },
        "contribs": contribs_dict,
        "loans": [{"id": l.id, "member": l.member_name, "amt": l.principal} for l in loans],
        "requests": [{"id": r.id, "member": r.member_name, "amount": r.amount, "date": r.date_requested, "status": r.status} for r in requests],
        "logs": [{"time": l.timestamp, "msg": l.message} for l in logs]
    }
