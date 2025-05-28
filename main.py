from fastapi import FastAPI, Request, Form, UploadFile, File, Depends, HTTPException, Header
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import uvicorn
from typing import List, Optional
import aiofiles
import os
import uuid
from pydantic import BaseModel, EmailStr, Field, validator
from datetime import datetime, timedelta
from passlib.context import CryptContext
import jwt
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from enum import Enum

# MySQL imports
import mysql.connector
from mysql.connector import Error
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text, ForeignKey, Float
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session
from sqlalchemy.pool import QueuePool

# Create directory structure if it doesn't exist
if not os.path.exists("static"):
    os.makedirs("static")
if not os.path.exists("static/uploads"):
    os.makedirs("static/uploads")

app = FastAPI()

# CORS middleware - Updated to handle specific frontend requirements
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:5500",
        "http://127.0.0.1:5500",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "*"  # Allow all origins for development - remove in production
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["*"],
)

# Static files and templates setup
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Authentication setup
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = "your_secret_key_change_this_in_production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 1440  # 24 hours to match frontend expectations
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

# Database configuration
DATABASE_URL = "mysql+mysqlconnector://root:Arceus123Mewtow@localhost/foodlinker_db"

# SQLAlchemy setup
Base = declarative_base()

# Define database models
class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    full_name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=False)
    password = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    
    # Relationship with donations
    donations = relationship("FoodDonation", back_populates="donor")
    food_requests = relationship("FoodRequest", back_populates="requester")

class FoodDonation(Base):
    __tablename__ = "food_donations"
    
    id = Column(String(36), primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    pickup_date = Column(String(50), nullable=False)
    expiry_date = Column(String(50), nullable=False)
    pickup_time = Column(String(50), nullable=False)
    pickup_address = Column(Text, nullable=False)
    contact_email = Column(String(255), nullable=False)
    contact_phone = Column(String(50), nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    is_active = Column(Boolean, default=True)
    image_path = Column(String(255), nullable=True)
    
    # Relationships
    items = relationship("FoodItem", back_populates="donation", cascade="all, delete-orphan")
    donor = relationship("User", back_populates="donations")

class FoodItem(Base):
    __tablename__ = "food_items"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    donation_id = Column(String(36), ForeignKey("food_donations.id"), nullable=False)
    name = Column(String(255), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit = Column(String(50), nullable=False)
    
    # Relationship with FoodDonation
    donation = relationship("FoodDonation", back_populates="items")

class RequestStatus(str, Enum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"

class FoodRequest(Base):
    __tablename__ = "food_requests"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    donation_id = Column(String(36), ForeignKey("food_donations.id"), nullable=False)
    requester_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    requester_name = Column(String(255), nullable=False)
    requester_email = Column(String(255), nullable=False)
    requester_phone = Column(String(50), nullable=True)
    pickup_date = Column(String(50), nullable=False)
    pickup_address = Column(Text, nullable=False)
    message = Column(Text, nullable=True)
    status = Column(String(20), default=RequestStatus.PENDING, nullable=False)
    created_at = Column(DateTime, default=datetime.now)
    
    # Relationships
    donation = relationship("FoodDonation")
    requester = relationship("User")

# Create engine and session with better error handling
try:
    engine = create_engine(
        DATABASE_URL,
        pool_size=10,
        max_overflow=20,
        pool_recycle=3600,
        pool_pre_ping=True,
        echo=False  # Set to True for SQL debugging
    )
except Exception as e:
    print(f"Database connection error: {e}")
    # Fallback to SQLite for development if MySQL is not available
    engine = create_engine("sqlite:///./foodlinker.db", connect_args={"check_same_thread": False})

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Authentication helper functions
def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def get_user_by_email(email: str, db: Session):
    return db.query(User).filter(User.email == email).first()

def get_user_by_id(user_id: int, db: Session):
    return db.query(User).filter(User.id == user_id).first()

# Updated authentication function to handle frontend authorization format
async def get_current_user(authorization: str = Header(None), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=401,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    if not authorization:
        raise credentials_exception
    
    try:
        # Handle both "Bearer <token>" and just "<token>" formats
        if authorization.startswith("Bearer "):
            token = authorization.split(" ")[1]
        else:
            token = authorization
            
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise credentials_exception
            
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=401,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (jwt.PyJWTError, IndexError, AttributeError):
        raise credentials_exception
    
    user = get_user_by_email(email=email, db=db)
    if user is None:
        raise credentials_exception
    return user

# Pydantic models
class UserCreate(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    password: str = Field(..., min_length=8)
    
    @validator('full_name')
    def name_must_contain_space(cls, v):
        if len(v.split()) < 2:
            raise ValueError('Full name should contain at least first and last name')
        return v
    
    @validator('password')
    def password_strength(cls, v):
        if not re.search(r'[A-Z]', v):
            raise ValueError('Password must contain at least one uppercase letter')
        if not re.search(r'[a-z]', v):
            raise ValueError('Password must contain at least one lowercase letter')
        if not re.search(r'[0-9]', v):
            raise ValueError('Password must contain at least one digit')
        if not re.search(r'[^A-Za-z0-9]', v):
            raise ValueError('Password must contain at least one special character')
        return v

class UserResponse(BaseModel):
    id: int
    full_name: str
    email: str
    created_at: datetime
    
    class Config:
        orm_mode = True

class FoodItemCreate(BaseModel):
    name: str = Field(..., min_length=1)
    quantity: int = Field(..., gt=0)
    unit: str

class DonationCreate(BaseModel):
    title: str = Field(..., min_length=1)
    description: str = Field(..., min_length=1)
    pickup_date: str
    expiry_date: str
    pickup_time: str
    pickup_address: str = Field(..., min_length=1)
    contact_email: EmailStr
    contact_phone: str = Field(..., min_length=1)
    items: List[FoodItemCreate] = Field(..., min_items=1)

class RequestCreate(BaseModel):
    donation_id: str
    requester_name: str = Field(..., min_length=1)
    requester_email: EmailStr
    requester_phone: Optional[str] = None
    pickup_date: str
    pickup_address: str = Field(..., min_length=1)
    message: Optional[str] = None

class RequestUpdate(BaseModel):
    status: RequestStatus

class Token(BaseModel):
    access_token: str
    token_type: str

# Add OPTIONS handler for preflight requests
@app.options("/{full_path:path}")
async def options_handler():
    return JSONResponse(
        content={},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        }
    )

# Create tables on app startup
@app.on_event("startup")
async def startup_event():
    try:
        Base.metadata.create_all(bind=engine)
        print("Database tables created successfully")
    except Exception as e:
        print(f"Error creating database tables: {e}")

# Authentication Routes
@app.post("/register", response_model=UserResponse)
async def register_user(
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    db: Session = Depends(get_db)
):
    if password != confirm_password:
        raise HTTPException(status_code=400, detail="Passwords do not match")
    
    try:
        user_data = UserCreate(full_name=full_name, email=email, password=password)
        
        existing_user = get_user_by_email(email, db)
        if existing_user:
            raise HTTPException(status_code=400, detail="Email already registered")
        
        hashed_password = get_password_hash(user_data.password)
        
        db_user = User(
            full_name=user_data.full_name,
            email=user_data.email,
            password=hashed_password,
            created_at=datetime.now()
        )
        
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        
        return db_user
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail="Registration failed")

@app.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = get_user_by_email(form_data.username, db)
    if not user:
        raise HTTPException(
            status_code=401, 
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    if not verify_password(form_data.password, user.password):
        raise HTTPException(
            status_code=401, 
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/user/me", response_model=UserResponse)
async def get_user_info(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "full_name": current_user.full_name,
        "email": current_user.email,
        "created_at": current_user.created_at
    }

# Main Routes
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return HTMLResponse(content="""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Annadan - Food Donation Platform</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 40px; }
            .container { max-width: 800px; margin: 0 auto; }
            .btn { padding: 10px 20px; margin: 10px; background: #007bff; color: white; text-decoration: none; border-radius: 5px; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>Welcome to Annadan</h1>
            <p>Food Donation Platform API is running successfully!</p>
            <p>Available endpoints:</p>
            <ul>
                <li><strong>POST /register</strong> - Register a new user</li>
                <li><strong>POST /login</strong> - Login user</li>
                <li><strong>GET /user/me</strong> - Get current user info (requires auth)</li>
                <li><strong>POST /api/donations/</strong> - Create donation (requires auth)</li>
                <li><strong>GET /api/donations/</strong> - Get all donations (requires auth)</li>
                <li><strong>GET /docs</strong> - API Documentation</li>
            </ul>
            <a href="/docs" class="btn">View API Documentation</a>
        </div>
    </body>
    </html>
    """)

@app.post("/api/donations/")
async def create_donation(
    donation: DonationCreate, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        # Validate dates
        try:
            pickup_date_obj = datetime.strptime(donation.pickup_date, "%Y-%m-%d")
            expiry_date_obj = datetime.strptime(donation.expiry_date, "%Y-%m-%d")
            today = datetime.now().date()
            
            if pickup_date_obj.date() < today:
                raise HTTPException(status_code=400, detail="Pickup date cannot be in the past")
            
            if expiry_date_obj.date() <= pickup_date_obj.date():
                raise HTTPException(status_code=400, detail="Expiry date must be after pickup date")
                
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
        
        # Create donation record
        donation_id = str(uuid.uuid4())
        
        db_donation = FoodDonation(
            id=donation_id,
            user_id=current_user.id,
            title=donation.title,
            description=donation.description,
            pickup_date=donation.pickup_date,
            expiry_date=donation.expiry_date,
            pickup_time=donation.pickup_time,
            pickup_address=donation.pickup_address,
            contact_email=donation.contact_email,
            contact_phone=donation.contact_phone,
            created_at=datetime.now(),
            is_active=True,
            image_path=None
        )
        
        db.add(db_donation)
        
        # Create food items
        for item in donation.items:
            db_item = FoodItem(
                donation_id=donation_id,
                name=item.name.strip(),
                quantity=item.quantity,
                unit=item.unit
            )
            db.add(db_item)
        
        # Commit changes
        db.commit()
        db.refresh(db_donation)
        
        # Prepare response
        response_dict = {
            "id": db_donation.id,
            "user_id": db_donation.user_id,
            "title": db_donation.title,
            "description": db_donation.description,
            "pickup_date": db_donation.pickup_date,
            "expiry_date": db_donation.expiry_date,
            "pickup_time": db_donation.pickup_time,
            "pickup_address": db_donation.pickup_address,
            "contact_email": db_donation.contact_email,
            "contact_phone": db_donation.contact_phone,
            "created_at": db_donation.created_at.isoformat(),
            "is_active": db_donation.is_active,
            "image_path": db_donation.image_path,
            "items": [
                {"name": item.name, "quantity": item.quantity, "unit": item.unit}
                for item in db_donation.items
            ]
        }
        
        return response_dict
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        print(f"Error creating donation: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create donation: {str(e)}")

@app.post("/api/donations/{donation_id}/upload-image")
async def upload_image(
    donation_id: str, 
    file: UploadFile = File(...), 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Validate file typeA
    allowed_types = ["image/jpeg", "image/png", "image/gif", "image/webp"]
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail="Only image files are allowed")
    
    # Find the donation and verify ownership
    donation = db.query(FoodDonation).filter(
        FoodDonation.id == donation_id,
        FoodDonation.user_id == current_user.id
    ).first()
    
    if not donation:
        raise HTTPException(status_code=404, detail="Donation not found or access denied")
    
    # Process the uploaded file
    file_extension = os.path.splitext(file.filename)[1].lower()
    if not file_extension:
        file_extension = ".jpg"  # Default extension
        
    new_filename = f"{donation_id}_{uuid.uuid4().hex[:8]}{file_extension}"
    file_path = f"static/uploads/{new_filename}"
    
    try:
        # Ensure uploads directory exists
        os.makedirs("static/uploads", exist_ok=True)
        
        # Save the file
        async with aiofiles.open(file_path, "wb") as out_file:
            content = await file.read()
            await out_file.write(content)
        
        # Update the database with the image path
        image_url = f"/static/uploads/{new_filename}"
        donation.image_path = image_url
        db.commit()
        
        return {"filename": new_filename, "image_url": image_url}
        
    except Exception as e:
        db.rollback()
        print(f"Error uploading file: {e}")
        raise HTTPException(status_code=500, detail=f"Error uploading file: {str(e)}")

@app.get("/api/donations/")
async def get_donations(
    active_only: bool = True, 
    my_donations: bool = False,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        # Query donations
        query = db.query(FoodDonation)
        
        if my_donations:
            query = query.filter(FoodDonation.user_id == current_user.id)
        
        if active_only:
            query = query.filter(FoodDonation.is_active == True)
        
        # Order by creation date (newest first)
        donations = query.order_by(FoodDonation.created_at.desc()).all()
        
        # Format response
        result = []
        for donation in donations:
            result.append({
                "id": donation.id,
                "user_id": donation.user_id,
                "donor_name": donation.donor.full_name,
                "title": donation.title,
                "description": donation.description,
                "pickup_date": donation.pickup_date,
                "expiry_date": donation.expiry_date,
                "pickup_time": donation.pickup_time,
                "pickup_address": donation.pickup_address,
                "contact_email": donation.contact_email,
                "contact_phone": donation.contact_phone,
                "created_at": donation.created_at.isoformat(),
                "is_active": donation.is_active,
                "image_path": donation.image_path,
                "items": [
                    {"name": item.name, "quantity": item.quantity, "unit": item.unit}
                    for item in donation.items
                ]
            })
        
        return result
        
    except Exception as e:
        print(f"Error fetching donations: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch donations: {str(e)}")

@app.get("/api/donations/{donation_id}")
async def get_donation(
    donation_id: str, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        donation = db.query(FoodDonation).filter(FoodDonation.id == donation_id).first()
        
        if not donation:
            raise HTTPException(status_code=404, detail="Donation not found")
        
        result = {
            "id": donation.id,
            "user_id": donation.user_id,
            "donor_name": donation.donor.full_name,
            "title": donation.title,
            "description": donation.description,
            "pickup_date": donation.pickup_date,
            "expiry_date": donation.expiry_date,
            "pickup_time": donation.pickup_time, 
            "pickup_address": donation.pickup_address,
            "contact_email": donation.contact_email,
            "contact_phone": donation.contact_phone,
            "created_at": donation.created_at.isoformat(),
            "is_active": donation.is_active,
            "image_path": donation.image_path,
            "items": [
                {"name": item.name, "quantity": item.quantity, "unit": item.unit}
                for item in donation.items
            ]
        }
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error fetching donation: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch donation: {str(e)}")

@app.delete("/api/donations/{donation_id}")
async def delete_donation(
    donation_id: str, 
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        donation = db.query(FoodDonation).filter(
            FoodDonation.id == donation_id,
            FoodDonation.user_id == current_user.id
        ).first()
        
        if not donation:
            raise HTTPException(status_code=404, detail="Donation not found or access denied")
        
        # Delete associated image file if it exists
        if donation.image_path:
            try:
                file_path = donation.image_path.replace("/static/", "static/")
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                print(f"Error deleting image file: {e}")
        
        # Delete the donation (items will be deleted automatically due to cascade)
        db.delete(donation)
        db.commit()
        
        return {"message": "Donation deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        print(f"Error deleting donation: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to delete donation: {str(e)}")

@app.post("/api/requests/")
async def create_request(
    request_data: RequestCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        # Validate that the donation exists and is active
        donation = db.query(FoodDonation).filter(
            FoodDonation.id == request_data.donation_id,
            FoodDonation.is_active == True
        ).first()
        
        if not donation:
            raise HTTPException(status_code=404, detail="Donation not found or no longer available")
        
        # Prevent users from requesting their own donations
        if donation.user_id == current_user.id:
            raise HTTPException(status_code=400, detail="You cannot request your own donation")
        
        # Check if user has already requested this donation
        existing_request = db.query(FoodRequest).filter(
            FoodRequest.donation_id == request_data.donation_id,
            FoodRequest.requester_id == current_user.id
        ).first()
        
        if existing_request:
            raise HTTPException(status_code=400, detail="You have already requested this donation")
        
        # Validate pickup date
        try:
            pickup_date_obj = datetime.strptime(request_data.pickup_date, "%Y-%m-%d")
            today = datetime.now().date()
            
            if pickup_date_obj.date() < today:
                raise HTTPException(status_code=400, detail="Pickup date cannot be in the past")
                
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")
        
        # Create the request
        db_request = FoodRequest(
            donation_id=request_data.donation_id,
            requester_id=current_user.id,
            requester_name=request_data.requester_name,
            requester_email=request_data.requester_email,
            requester_phone=request_data.requester_phone,
            pickup_date=request_data.pickup_date,
            pickup_address=request_data.pickup_address,
            message=request_data.message,
            status=RequestStatus.PENDING,
            created_at=datetime.now()
        )
        
        db.add(db_request)
        db.commit()
        db.refresh(db_request)
        
        return {
            "id": db_request.id,
            "donation_id": db_request.donation_id,
            "donation_title": donation.title,
            "requester_name": db_request.requester_name,
            "requester_email": db_request.requester_email,
            "requester_phone": db_request.requester_phone,
            "pickup_date": db_request.pickup_date,
            "pickup_address": db_request.pickup_address,
            "message": db_request.message,
            "status": db_request.status,
            "created_at": db_request.created_at.isoformat()
        }
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        print(f"Error creating request: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create request: {str(e)}")

@app.get("/api/requests/")
async def get_requests(
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        # Get requests for donations owned by the current user
        query = db.query(FoodRequest).join(FoodDonation).filter(
            FoodDonation.user_id == current_user.id
        )
        
        # Filter by status if provided
        if status and status != "all":
            if status == "new":
                query = query.filter(FoodRequest.status == RequestStatus.PENDING)
            elif status == "completed":
                query = query.filter(FoodRequest.status == RequestStatus.ACCEPTED)
            elif status == "rejected":
                query = query.filter(FoodRequest.status == RequestStatus.REJECTED)
        
        # Order by creation date (newest first)
        requests = query.order_by(FoodRequest.created_at.desc()).all()
        
        # Format response
        result = []
        for request in requests:
            result.append({
                "id": request.id,
                "donation_id": request.donation_id,
                "donation_title": request.donation.title,
                "requester_name": request.requester_name,
                "requester_email": request.requester_email,
                "requester_phone": request.requester_phone,
                "pickup_date": request.pickup_date,
                "pickup_address": request.pickup_address,
                "message": request.message,
                "status": request.status,
                "created_at": request.created_at.isoformat()
            })
        
        return result
        
    except Exception as e:
        print(f"Error fetching requests: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch requests: {str(e)}")

@app.patch("/api/requests/{request_id}")
async def update_request(
    request_id: int,
    request_update: RequestUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        # Find the request and verify that the current user owns the associated donation
        request = db.query(FoodRequest).join(FoodDonation).filter(
            FoodRequest.id == request_id,
            FoodDonation.user_id == current_user.id
        ).first()
        
        if not request:
            raise HTTPException(status_code=404, detail="Request not found or access denied")
        
        # Update the request status
        request.status = request_update.status
        db.commit()
        db.refresh(request)
        
        return {
            "id": request.id,
            "donation_id": request.donation_id,
            "donation_title": request.donation.title,
            "requester_name": request.requester_name,
            "requester_email": request.requester_email,
            "requester_phone": request.requester_phone,
            "pickup_date": request.pickup_date,
            "pickup_address": request.pickup_address,
            "message": request.message,
            "status": request.status,
            "created_at": request.created_at.isoformat()
        }
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        print(f"Error updating request: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to update request: {str(e)}")

@app.get("/api/my-requests/")
async def get_my_requests(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    try:
        # Get requests made by the current user
        requests = db.query(FoodRequest).filter(
            FoodRequest.requester_id == current_user.id
        ).order_by(FoodRequest.created_at.desc()).all()
        
        # Format response
        result = []
        for request in requests:
            result.append({
                "id": request.id,
                "donation_id": request.donation_id,
                "donation_title": request.donation.title,
                "donor_name": request.donation.donor.full_name,
                "pickup_date": request.pickup_date,
                "pickup_address": request.pickup_address,
                "message": request.message,
                "status": request.status,
                "created_at": request.created_at.isoformat()
            })
        
        return result
        
    except Exception as e:
        print(f"Error fetching my requests: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch requests: {str(e)}")

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)