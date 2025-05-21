from fastapi import FastAPI, Request, Form, UploadFile, File, Depends
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
import uvicorn
from typing import List, Optional
import aiofiles
import os
import uuid
from pydantic import BaseModel, EmailStr
from datetime import datetime
from fastapi import HTTPException, Body
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

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

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files and templates setup
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# Database configuration
DATABASE_URL = "mysql+mysqlconnector://root:Arceus123Mewtow@localhost/foodlinker_db"

# SQLAlchemy setup
Base = declarative_base()

# Define database models
class FoodDonation(Base):
    __tablename__ = "food_donations"
    
    id = Column(String(36), primary_key=True, index=True)
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
    
    # Relationship with FoodItem
    items = relationship("FoodItem", back_populates="donation", cascade="all, delete-orphan")

class FoodItem(Base):
    __tablename__ = "food_items"
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    donation_id = Column(String(36), ForeignKey("food_donations.id"), nullable=False)
    name = Column(String(255), nullable=False)
    quantity = Column(Integer, nullable=False)
    unit = Column(String(50), nullable=False)
    
    # Relationship with FoodDonation
    donation = relationship("FoodDonation", back_populates="items")

# Create engine and session
engine = create_engine(
    DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_recycle=3600,
    pool_pre_ping=True,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Create tables on app startup
@app.on_event("startup")
async def startup_event():
    Base.metadata.create_all(bind=engine)
    
    # Generate template files if they don't exist
    if not os.path.exists("templates"):
        os.makedirs("templates")
        
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8" />
        <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
        <title>FoodLinker - Donate Food</title>
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css"/>
        <link rel="stylesheet" href="/static/form.css"/>
        
        <style>
            /* Reset & Base Styles */
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            }
            
            body {
                background-color: #f5f7fa;
            }
            
            .container {
                display: flex;
            }
            
            /* Rest of the CSS content... */
        </style>
    </head>
    <body>
        <div class="container">
            <!-- Sidebar and main content would go here -->
        </div>

        <script>
            // JavaScript functions
            
            // Submit form to the API instead of the original submission
  async function submitForm() {
    const foodTitle = document.getElementById('foodTitle').value;
    const description = document.getElementById('description').value;
    const pickupDate = document.getElementById('pickupDate').value;
    const expiryDate = document.getElementById('expiryDate').value;
    const pickupTime = document.getElementById('pickupTime').value;
    const pickupAddress = document.getElementById('pickupAddress').value;
    const contactEmail = document.getElementById('contactEmail').value;
    const contactPhone = document.getElementById('contactPhone').value;
    
    // Get food items
    const foodItems = [];
    const itemContainers = document.querySelectorAll('.food-item');
    
    itemContainers.forEach(container => {
        const itemName = container.querySelector('input[name="item[]"]').value;
        const quantity = parseInt(container.querySelector('input[name="quantity[]"]').value);
        const unit = container.querySelector('select[name="unit[]"]').value;
        
        if (itemName && quantity) {
            foodItems.push({
                name: itemName,
                quantity: quantity,
                unit: unit
            });
        }
    });
    
    // Create donation object
    const donation = {
        title: foodTitle,
        description: description,
        pickup_date: pickupDate,
        expiry_date: expiryDate,
        pickup_time: pickupTime,
        pickup_address: pickupAddress,
        contact_email: contactEmail,
        contact_phone: contactPhone,
        items: foodItems
    };
    
    try {
        // Send data to API
        const response = await fetch('/api/donations/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(donation)
        });
        
        if (!response.ok) {
            throw new Error('Failed to submit donation');
        }
        
        const result = await response.json();
        
        // Handle file upload if a file was selected
        const fileInput = document.getElementById('fileInput');
        if (fileInput.files.length > 0) {
            await uploadImage(result.id, fileInput.files[0]);
        }
        
        // Show success message
        const successMessage = document.getElementById('successMessage');
        successMessage.style.display = 'block';
        window.scrollTo({ top: 0, behavior: 'smooth' });
        
        // Reset form
        document.getElementById('foodForm').reset();
        document.getElementById('imagePreview').style.display = 'none';
        
        // Hide message after 3 seconds
        setTimeout(() => {
            successMessage.style.display = 'none';
        }, 3000);
        
    } catch (error) {
        console.error('Error:', error);
        alert('Failed to submit form. Please try again.');
    }
}
            
            // Upload image function
            async function uploadImage(donationId, file) {
                const formData = new FormData();
                formData.append('file', file);
                
                try {
                    const response = await fetch(`/api/donations/${donationId}/upload-image`, {
                        method: 'POST',
                        body: formData
                    });
                    
                    if (!response.ok) {
                        throw new Error('Failed to upload image');
                    }
                    
                    return await response.json();
                } catch (error) {
                    console.error('Error uploading image:', error);
                    return null;
                }
            }
            
            // Add new food item
            function addFoodItem() {
                const container = document.getElementById('food-items-container');
                const foodItem = document.createElement('div');
                foodItem.className = 'food-item';
                foodItem.innerHTML = `
                    <input type="text" name="item[]" placeholder="Enter food item name" required>
                    <input type="number" name="quantity[]" placeholder="Qty" min="1" style="width: 80px; margin: 0 10px;" required>
                    <select name="unit[]" style="width: 100px;">
                        <option value="pieces">Pieces</option>
                        <option value="servings">Servings</option>
                        <option value="kg">Kg</option>
                        <option value="lb">lb</option>
                    </select>
                    <button type="button" onclick="removeItem(this)"><i class="fas fa-times"></i></button>
                `;
                container.appendChild(foodItem);
            }
            
            // Remove food item
            function removeItem(button) {
                const item = button.parentNode;
                item.parentNode.removeChild(item);
            }
            
            // Preview uploaded image
            function previewImage(event) {
                const preview = document.getElementById('imagePreview');
                preview.style.display = 'block';
                preview.src = URL.createObjectURL(event.target.files[0]);
            }
        </script>
    </body>
    </html>
    """
    
    # Create the HTML template file
    if not os.path.exists("templates/index.html"):
        async with aiofiles.open("templates/index.html", "w") as f:
            await f.write(html_content)
    
    # Create CSS file
    css_content = """
    /* CSS content */
    body {
        background-color: #f5f7fa;
    }
    
    .container {
        display: flex;
    }
    
    /* Sidebar styling */
    .sidebar {
        width: 280px;
        background-color: #2c3e50;
        height: 100vh;
        position: sticky;
        top: 0;
        color: #fff;
        padding: 20px 0;
        display: flex;
        flex-direction: column;
    }
    
    /* Rest of the CSS content... */
    """
    
    if not os.path.exists("static/form.css"):
        async with aiofiles.open("static/form.css", "w") as f:
            await f.write(css_content)

# Pydantic models for request validation
class FoodItemCreate(BaseModel):
    name: str
    quantity: int
    unit: str

class DonationCreate(BaseModel):
    title: str
    description: str
    pickup_date: str
    expiry_date: str
    pickup_time: str
    pickup_address: str
    contact_email: str
    contact_phone: str
    items: List[FoodItemCreate]

class EmailRequest(BaseModel):
    donationId: str
    donationTitle: str
    donorEmail: EmailStr
    requesterName: str
    requesterEmail: EmailStr
    requesterPhone: Optional[str] = None
    requestMessage: Optional[str] = None
    timestamp: str

# Email configuration
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_HOST_USER = "your-email@gmail.com"  
EMAIL_HOST_PASSWORD = "your-app-password"  
EMAIL_FROM = "FoodLinker <your-email@gmail.com>"

# API Routes
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/donations/")
async def create_donation(donation: DonationCreate, db: Session = Depends(get_db)):
    try:
        # Create donation record
        donation_id = str(uuid.uuid4())
        
        db_donation = FoodDonation(
            id=donation_id,
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
                name=item.name,
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
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to create donation: {str(e)}")

@app.post("/api/donations/{donation_id}/upload-image")
async def upload_image(donation_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    # Find the donation
    donation = db.query(FoodDonation).filter(FoodDonation.id == donation_id).first()
    
    if not donation:
        return JSONResponse(status_code=404, content={"message": "Donation not found"})
    
    # Process the uploaded file
    file_extension = os.path.splitext(file.filename)[1]
    new_filename = f"{donation_id}{file_extension}"
    file_path = f"static/uploads/{new_filename}"
    
    try:
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
        return JSONResponse(status_code=500, content={"message": f"Error uploading file: {str(e)}"})

@app.get("/api/donations/")
async def get_donations(active_only: bool = True, db: Session = Depends(get_db)):
    try:
        # Query donations based on active status
        query = db.query(FoodDonation)
        if active_only:
            query = query.filter(FoodDonation.is_active == True)
        
        donations = query.all()
        
        # Format response
        result = []
        for donation in donations:
            result.append({
                "id": donation.id,
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
        raise HTTPException(status_code=500, detail=f"Failed to fetch donations: {str(e)}")

@app.get("/api/donations/{donation_id}")
async def get_donation(donation_id: str, db: Session = Depends(get_db)):
    try:
        # Query the specific donation
        donation = db.query(FoodDonation).filter(FoodDonation.id == donation_id).first()
        
        if not donation:
            return JSONResponse(status_code=404, content={"message": "Donation not found"})
        
        # Format response
        result = {
            "id": donation.id,
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
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch donation: {str(e)}")

@app.delete("/api/donations/{donation_id}")
async def delete_donation(donation_id: str, db: Session = Depends(get_db)):
    try:
        # Query the donation
        donation = db.query(FoodDonation).filter(FoodDonation.id == donation_id).first()
        
        if not donation:
            return JSONResponse(status_code=404, content={"message": "Donation not found"})
        
        # Delete associated food items (SQLAlchemy will handle this with cascade)
        db.delete(donation)
        db.commit()
        
        return {"message": "Donation deleted successfully"}
        
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete donation: {str(e)}")

# Email functionality commented out for now
# @app.post("/api/send-request-email/")
# async def send_request_email(request: EmailRequest = Body(...)):
#     try:
#         # Implementation goes here
#         return {"status": "success", "message": "Email request processed successfully"}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Failed to process email request: {str(e)}")

if __name__ == "__main__":
    uvicorn.run("form:app", host="0.0.0.0", port=8000, reload=True)