import os
from fastapi import FastAPI, HTTPException, Depends, Request, Form, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Text, ForeignKey, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta
import uuid
from fastapi.middleware.cors import CORSMiddleware
import shutil
from pathlib import Path

# Database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./foodlinker.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Models
class FoodItem(Base):
    __tablename__ = "food_items"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(Text)
    quantity = Column(String)
    location = Column(String)
    donor_id = Column(Integer, ForeignKey("users.id"))
    expiry_date = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    image_path = Column(String, nullable=True)
    status = Column(String, default="available")  # available, requested, completed, expired
    
    donor = relationship("User", back_populates="donations")
    requests = relationship("FoodRequest", back_populates="food_item")

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    full_name = Column(String)
    user_type = Column(String)  # donor, receiver
    created_at = Column(DateTime, default=datetime.utcnow)
    
    donations = relationship("FoodItem", back_populates="donor")
    requests = relationship("FoodRequest", back_populates="receiver")

class FoodRequest(Base):
    __tablename__ = "food_requests"
    
    id = Column(Integer, primary_key=True, index=True)
    food_id = Column(Integer, ForeignKey("food_items.id"))
    receiver_id = Column(Integer, ForeignKey("users.id"))
    status = Column(String, default="pending")  # pending, approved, rejected, completed
    created_at = Column(DateTime, default=datetime.utcnow)
    pickup_date = Column(DateTime, nullable=True)
    
    food_item = relationship("FoodItem", back_populates="requests")
    receiver = relationship("User", back_populates="requests")

# Create the database tables
Base.metadata.create_all(bind=engine)

# Dependency to get the database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Pydantic models for request/response
class FoodItemCreate(BaseModel):
    name: str
    description: str
    quantity: str
    location: str
    expiry_date: datetime
    
class FoodItemResponse(BaseModel):
    id: int
    name: str
    description: str
    quantity: str
    location: str
    expiry_date: datetime
    created_at: datetime
    image_path: Optional[str] = None
    status: str
    donor_name: str
    
    class Config:
        orm_mode = True

class DashboardStats(BaseModel):
    total_food_items: int
    total_requests: int
    completed_requests: int
    impact_meals: int
    
    class Config:
        orm_mode = True

app = FastAPI(title="FoodLinker API")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files configuration
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")

# Make sure the upload directory exists
UPLOAD_DIR = Path("static/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Routes for the backend API
@app.get("/")
async def root():
    return RedirectResponse(url="/donor-dashboard")

@app.get("/donor-dashboard", response_class=HTMLResponse)
async def get_donor_dashboard(request: Request, db: Session = Depends(get_db)):
    # Get dashboard stats
    stats = get_dashboard_stats(db)
    
    # Get latest food listings (past 7 days)
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    latest_foods = db.query(FoodItem).join(User).filter(
        FoodItem.created_at >= seven_days_ago
    ).order_by(FoodItem.created_at.desc()).limit(8).all()
    
    # Format food items for template
    food_items = []
    for food in latest_foods:
        days_remaining = (food.expiry_date - datetime.utcnow()).days
        
        # Format the expiry message
        if days_remaining < 0:
            expiry_message = "Expired"
        elif days_remaining == 0:
            expiry_message = "Expires today"
        elif days_remaining == 1:
            expiry_message = "Expires tomorrow"
        else:
            expiry_message = f"Expires in {days_remaining} days"
            
        # Format the date added
        days_since_added = (datetime.utcnow() - food.created_at).days
        if days_since_added == 0:
            date_added = "Today"
        elif days_since_added == 1:
            date_added = "Yesterday"
        else:
            date_added = f"{days_since_added} days ago"
        
        food_items.append({
            "id": food.id,
            "name": food.name,
            "description": food.description,
            "location": food.location,
            "date_added": date_added,
            "expiry_message": expiry_message,
            "image_path": food.image_path if food.image_path else "/static/placeholder.jpg"
        })
    
    # Return the HTML template with context data
    return templates.TemplateResponse(
        "donor_dashboard.html", 
        {
            "request": request, 
            "stats": stats,
            "food_items": food_items
        }
    )

@app.get("/api/dashboard/stats", response_model=DashboardStats)
async def dashboard_stats(db: Session = Depends(get_db)):
    return get_dashboard_stats(db)

def get_dashboard_stats(db: Session):
    # Calculate stats
    
    # Total food items - counting all food items in the database
    total_food_items = db.query(func.count(FoodItem.id)).scalar()
    
    # Count requests from the past 7 days
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    
    # Total requests in the past 7 days
    total_requests = db.query(func.count(FoodRequest.id)).filter(
        FoodRequest.created_at >= seven_days_ago
    ).scalar()
    
    # Completed requests in the past 7 days
    completed_requests = db.query(func.count(FoodRequest.id)).filter(
        FoodRequest.created_at >= seven_days_ago,
        FoodRequest.status == "completed"
    ).scalar()
    
    # Impact (estimate 3 meals per completed request)
    impact_meals = completed_requests * 3
    
    return {
        "total_food_items": total_food_items,
        "total_requests": total_requests,
        "completed_requests": completed_requests,
        "impact_meals": impact_meals
    }

@app.get("/api/food", response_model=List[FoodItemResponse])
async def get_all_food_items(db: Session = Depends(get_db)):
    foods = db.query(FoodItem).join(User).order_by(FoodItem.created_at.desc()).all()
    
    # Format the response
    result = []
    for food in foods:
        result.append({
            "id": food.id,
            "name": food.name,
            "description": food.description,
            "quantity": food.quantity,
            "location": food.location,
            "expiry_date": food.expiry_date,
            "created_at": food.created_at,
            "image_path": food.image_path,
            "status": food.status,
            "donor_name": food.donor.full_name
        })
    
    return result

@app.get("/api/food/latest", response_model=List[FoodItemResponse])
async def get_latest_food_items(db: Session = Depends(get_db)):
    # Get food items from last 7 days
    seven_days_ago = datetime.utcnow() - timedelta(days=7)
    foods = db.query(FoodItem).join(User).filter(
        FoodItem.created_at >= seven_days_ago
    ).order_by(FoodItem.created_at.desc()).all()
    
    # Format the response
    result = []
    for food in foods:
        result.append({
            "id": food.id,
            "name": food.name,
            "description": food.description,
            "quantity": food.quantity,
            "location": food.location,
            "expiry_date": food.expiry_date,
            "created_at": food.created_at,
            "image_path": food.image_path,
            "status": food.status,
            "donor_name": food.donor.full_name
        })
    
    return result

@app.post("/api/food", response_model=FoodItemResponse)
async def create_food_item(
    name: str = Form(...),
    description: str = Form(...),
    quantity: str = Form(...),
    location: str = Form(...),
    expiry_date: str = Form(...),
    donor_id: int = Form(...),
    image: UploadFile = File(None),
    db: Session = Depends(get_db)
):
    # Check if donor exists
    donor = db.query(User).filter(User.id == donor_id).first()
    if not donor:
        raise HTTPException(status_code=404, detail="Donor not found")
    
    # Convert expiry_date string to datetime
    try:
        expiry_date_dt = datetime.strptime(expiry_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format, use YYYY-MM-DD")
    
    # Create a new food item
    db_food_item = FoodItem(
        name=name,
        description=description,
        quantity=quantity,
        location=location,
        expiry_date=expiry_date_dt,
        donor_id=donor_id,
        created_at=datetime.utcnow(),  # Set the current time
        status="available"
    )
    
    # Handle image upload if provided
    if image:
        # Generate a unique filename
        file_extension = image.filename.split(".")[-1]
        file_name = f"{uuid.uuid4()}.{file_extension}"
        file_path = UPLOAD_DIR / file_name
        
        # Save the file
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(image.file, buffer)
        
        # Save the relative path in the database
        db_food_item.image_path = f"/static/uploads/{file_name}"
    
    # Save to database
    db.add(db_food_item)
    db.commit()
    db.refresh(db_food_item)
    
    # Return the newly created food item with donor name
    return {
        "id": db_food_item.id,
        "name": db_food_item.name,
        "description": db_food_item.description,
        "quantity": db_food_item.quantity,
        "location": db_food_item.location,
        "expiry_date": db_food_item.expiry_date,
        "created_at": db_food_item.created_at,
        "image_path": db_food_item.image_path,
        "status": db_food_item.status,
        "donor_name": donor.full_name
    }

@app.post("/api/food/request", status_code=201)
async def request_food(
    food_id: int = Form(...),
    receiver_id: int = Form(...),
    db: Session = Depends(get_db)
):
    # Check if food item exists and is available
    food_item = db.query(FoodItem).filter(FoodItem.id == food_id).first()
    if not food_item:
        raise HTTPException(status_code=404, detail="Food item not found")
    if food_item.status != "available":
        raise HTTPException(status_code=400, detail="Food item is not available")
    
    # Check if receiver exists
    receiver = db.query(User).filter(User.id == receiver_id).first()
    if not receiver:
        raise HTTPException(status_code=404, detail="Receiver not found")
    
    # Create a new request
    new_request = FoodRequest(
        food_id=food_id,
        receiver_id=receiver_id,
        status="pending",
        created_at=datetime.utcnow()
    )
    
    # Update food item status
    food_item.status = "requested"
    
    # Save to database
    db.add(new_request)
    db.commit()
    
    return {"message": "Food request created successfully"}

@app.post("/api/food/request/{request_id}/status", status_code=200)
async def update_request_status(
    request_id: int,
    status: str = Form(...),
    db: Session = Depends(get_db)
):
    # Valid status values
    valid_statuses = ["pending", "approved", "rejected", "completed"]
    if status not in valid_statuses:
        raise HTTPException(status_code=400, detail="Invalid status")
    
    # Find the request
    food_request = db.query(FoodRequest).filter(FoodRequest.id == request_id).first()
    if not food_request:
        raise HTTPException(status_code=404, detail="Food request not found")
    
    # Update the request status
    food_request.status = status
    
    # Update the food item status if the request is completed or rejected
    if status == "completed":
        food_request.food_item.status = "completed"
        food_request.pickup_date = datetime.utcnow()
    elif status == "rejected":
        # Check if there are other pending requests for this food item
        other_pending = db.query(FoodRequest).filter(
            FoodRequest.food_id == food_request.food_id,
            FoodRequest.id != request_id,
            FoodRequest.status == "pending"
        ).first()
        
        # If no other pending requests, set food item back to available
        if not other_pending:
            food_request.food_item.status = "available"
    
    # Save changes
    db.commit()
    
    return {"message": f"Request status updated to {status}"}

# Add a route to check expired food and update status
@app.get("/api/food/check-expired", status_code=200)
async def check_expired_food(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    
    # Find food items that have expired but still marked as available
    expired_foods = db.query(FoodItem).filter(
        FoodItem.expiry_date < now,
        FoodItem.status == "available"
    ).all()
    
    # Update their status
    for food in expired_foods:
        food.status = "expired"
    
    db.commit()
    
    return {"message": f"Updated {len(expired_foods)} expired food items"}

# Add some test data when server starts
@app.on_event("startup")
async def startup_event():
    db = SessionLocal()
    
    # Check if we already have data
    user_count = db.query(func.count(User.id)).scalar()
    
    if user_count == 0:
        # Create sample users
        donor1 = User(
            username="donor1",
            email="donor1@example.com",
            hashed_password="hashed_password",  # In a real app, use proper password hashing
            full_name="John Donor",
            user_type="donor"
        )
        donor2 = User(
            username="donor2",
            email="donor2@example.com",
            hashed_password="hashed_password",
            full_name="Jane Giver",
            user_type="donor"
        )
        receiver1 = User(
            username="receiver1",
            email="receiver1@example.com",
            hashed_password="hashed_password",
            full_name="Bob Receiver",
            user_type="receiver"
        )
        
        db.add_all([donor1, donor2, receiver1])
        db.commit()
        
        # Create sample food items with different dates
        food1 = FoodItem(
            name="Fresh Vegetable Bundle",
            description="A bundle of fresh vegetables including carrots, tomatoes, and leafy greens. Perfect for a family meal.",
            quantity="5 kg",
            location="Downtown",
            donor_id=1,
            expiry_date=datetime.utcnow() + timedelta(days=3),
            created_at=datetime.utcnow(),
            image_path="/static/placeholder.jpg",
            status="available"
        )
        food2 = FoodItem(
            name="Bakery Goods",
            description="Assorted bread and pastries from local bakery. Still fresh and delicious!",
            quantity="12 items",
            location="Westside",
            donor_id=1,
            expiry_date=datetime.utcnow() + timedelta(days=1),
            created_at=datetime.utcnow() - timedelta(days=1),
            image_path="/static/placeholder.jpg",
            status="available"
        )
        food3 = FoodItem(
            name="Canned Food Package",
            description="Variety of canned foods including beans, soup, and vegetables. Long shelf life.",
            quantity="10 cans",
            location="Eastside",
            donor_id=2,
            expiry_date=datetime.utcnow() + timedelta(days=180),
            created_at=datetime.utcnow() - timedelta(days=2),
            image_path="/static/placeholder.jpg",
            status="available"
        )
        food4 = FoodItem(
            name="Fresh Fruit Basket",
            description="Seasonal fruits including apples, oranges, and bananas. Great source of vitamins.",
            quantity="3 kg",
            location="North Area",
            donor_id=2,
            expiry_date=datetime.utcnow() + timedelta(days=5),
            created_at=datetime.utcnow(),
            image_path="/static/placeholder.jpg",
            status="available"
        )
        
        db.add_all([food1, food2, food3, food4])
        db.commit()
        
        # Create some food requests
        request1 = FoodRequest(
            food_id=1,
            receiver_id=3,
            status="pending",
            created_at=datetime.utcnow() - timedelta(hours=2)
        )
        request2 = FoodRequest(
            food_id=2,
            receiver_id=3,
            status="approved",
            created_at=datetime.utcnow() - timedelta(days=1)
        )
        request3 = FoodRequest(
            food_id=3,
            receiver_id=3,
            status="completed",
            created_at=datetime.utcnow() - timedelta(days=2),
            pickup_date=datetime.utcnow() - timedelta(days=1)
        )
        
        db.add_all([request1, request2, request3])
        db.commit()
    
    db.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)