from fastapi import FastAPI, Request, Form, UploadFile, File
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
import mysql.connector
from mysql.connector import pooling
import contextlib
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Database Configuration
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "user": os.getenv("DB_USER", "root"),
    "password": os.getenv("DB_PASSWORD", ""),
    "database": os.getenv("DB_NAME", "foodlinker"),
}

# Create connection pool
connection_pool = pooling.MySQLConnectionPool(
    pool_name="foodlinker_pool",
    pool_size=5,
    **DB_CONFIG
)

# Context manager for database connections
@contextlib.contextmanager
def get_db_connection():
    connection = connection_pool.get_connection()
    try:
        yield connection
    finally:
        connection.close()

# Initialize database tables
def init_db():
    with get_db_connection() as connection:
        cursor = connection.cursor()
        
        # Create donations table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS donations (
            id VARCHAR(36) PRIMARY KEY,
            title VARCHAR(255) NOT NULL,
            description TEXT,
            pickup_date DATE NOT NULL,
            expiry_date DATE NOT NULL,
            pickup_time VARCHAR(50) NOT NULL,
            pickup_address TEXT NOT NULL,
            contact_email VARCHAR(255) NOT NULL,
            contact_phone VARCHAR(50) NOT NULL,
            created_at DATETIME NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            image_path VARCHAR(255)
        )
        """)
        
        # Create food_items table
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS food_items (
            id VARCHAR(36) PRIMARY KEY,
            donation_id VARCHAR(36) NOT NULL,
            name VARCHAR(255) NOT NULL,
            quantity INT NOT NULL,
            unit VARCHAR(50) NOT NULL,
            FOREIGN KEY (donation_id) REFERENCES donations(id) ON DELETE CASCADE
        )
        """)
        
        connection.commit()

# Create directories if they don't exist
if not os.path.exists("static"):
    os.makedirs("static")
if not os.path.exists("static/uploads"):
    os.makedirs("static/uploads")
if not os.path.exists("templates"):
    os.makedirs("templates")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup templates
templates = Jinja2Templates(directory="templates")

# Email settings
EMAIL_HOST = os.getenv("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "your-email@gmail.com")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "your-app-password")
EMAIL_FROM = os.getenv("EMAIL_FROM", "FoodLinker <your-email@gmail.com>")

@app.on_event("startup")
async def startup_event():
    # Initialize database
    init_db()
    
    # Create HTML template if it doesn't exist
    if not os.path.exists("templates/index.html"):
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
        async with aiofiles.open("templates/index.html", "w") as f:
            await f.write(html_content)
    
    # Create CSS file if it doesn't exist
    if not os.path.exists("static/form.css"):
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
        async with aiofiles.open("static/form.css", "w") as f:
            await f.write(css_content)

class FoodItem(BaseModel):
    name: str
    quantity: int
    unit: str

class Donation(BaseModel):
    title: str
    description: str
    pickup_date: str
    expiry_date: str
    pickup_time: str
    pickup_address: str
    contact_email: str
    contact_phone: str
    items: List[FoodItem]

class EmailRequest(BaseModel):
    donationId: str
    donationTitle: str
    donorEmail: EmailStr
    requesterName: str
    requesterEmail: EmailStr
    requesterPhone: Optional[str] = None
    requestMessage: Optional[str] = None
    timestamp: str

# Route to serve the main HTML page
@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/api/donations/")
async def create_donation(donation: Donation):
    try:
        donation_id = str(uuid.uuid4())
        created_at = datetime.now()
        
        with get_db_connection() as connection:
            cursor = connection.cursor(dictionary=True)
            
            # Insert donation record
            query = """
            INSERT INTO donations 
            (id, title, description, pickup_date, expiry_date, pickup_time, 
            pickup_address, contact_email, contact_phone, created_at, is_active)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            values = (
                donation_id, 
                donation.title, 
                donation.description, 
                donation.pickup_date, 
                donation.expiry_date,
                donation.pickup_time, 
                donation.pickup_address, 
                donation.contact_email, 
                donation.contact_phone,
                created_at,
                True
            )
            cursor.execute(query, values)
            
            # Insert food items
            for item in donation.items:
                item_id = str(uuid.uuid4())
                query = """
                INSERT INTO food_items (id, donation_id, name, quantity, unit)
                VALUES (%s, %s, %s, %s, %s)
                """
                values = (item_id, donation_id, item.name, item.quantity, item.unit)
                cursor.execute(query, values)
            
            connection.commit()
        
        # Return donation data with generated ID
        return {
            "id": donation_id,
            "title": donation.title,
            "description": donation.description,
            "pickup_date": donation.pickup_date,
            "expiry_date": donation.expiry_date,
            "pickup_time": donation.pickup_time,
            "pickup_address": donation.pickup_address,
            "contact_email": donation.contact_email,
            "contact_phone": donation.contact_phone,
            "created_at": created_at.isoformat(),
            "is_active": True,
            "image_path": None,
            "items": [item.dict() for item in donation.items]
        }
    
    except Exception as e:
        print(f"Error creating donation: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.post("/api/donations/{donation_id}/upload-image")
async def upload_image(donation_id: str, file: UploadFile = File(...)):
    try:
        # Check if donation exists
        with get_db_connection() as connection:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT id FROM donations WHERE id = %s", (donation_id,))
            donation = cursor.fetchone()
            
            if not donation:
                return JSONResponse(status_code=404, content={"message": "Donation not found"})
        
        # Save file
        file_extension = os.path.splitext(file.filename)[1]
        new_filename = f"{donation_id}{file_extension}"
        file_path = f"static/uploads/{new_filename}"
        
        async with aiofiles.open(file_path, "wb") as out_file:
            content = await file.read()
            await out_file.write(content)
        
        # Update image path in database
        image_url = f"/static/uploads/{new_filename}"
        with get_db_connection() as connection:
            cursor = connection.cursor()
            cursor.execute(
                "UPDATE donations SET image_path = %s WHERE id = %s",
                (image_url, donation_id)
            )
            connection.commit()
        
        return {"filename": new_filename, "image_url": image_url}
    
    except Exception as e:
        print(f"Error uploading image: {e}")
        raise HTTPException(status_code=500, detail=f"Error uploading image: {str(e)}")

@app.get("/api/donations/")
async def get_donations(active_only: bool = True):
    try:
        with get_db_connection() as connection:
            cursor = connection.cursor(dictionary=True)
            
            if active_only:
                query = "SELECT * FROM donations WHERE is_active = TRUE ORDER BY created_at DESC"
            else:
                query = "SELECT * FROM donations ORDER BY created_at DESC"
                
            cursor.execute(query)
            donations = cursor.fetchall()
            
            # Get food items for each donation
            for donation in donations:
                cursor.execute(
                    "SELECT id, name, quantity, unit FROM food_items WHERE donation_id = %s",
                    (donation["id"],)
                )
                donation["items"] = cursor.fetchall()
            
            return donations
    
    except Exception as e:
        print(f"Error fetching donations: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.get("/api/donations/{donation_id}")
async def get_donation(donation_id: str):
    try:
        with get_db_connection() as connection:
            cursor = connection.cursor(dictionary=True)
            
            # Get donation details
            cursor.execute("SELECT * FROM donations WHERE id = %s", (donation_id,))
            donation = cursor.fetchone()
            
            if not donation:
                return JSONResponse(status_code=404, content={"message": "Donation not found"})
            
            # Get food items
            cursor.execute(
                "SELECT id, name, quantity, unit FROM food_items WHERE donation_id = %s",
                (donation_id,)
            )
            donation["items"] = cursor.fetchall()
            
            return donation
    
    except Exception as e:
        print(f"Error fetching donation: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.delete("/api/donations/{donation_id}")
async def delete_donation(donation_id: str):
    try:
        with get_db_connection() as connection:
            cursor = connection.cursor(dictionary=True)
            
            # Check if donation exists
            cursor.execute("SELECT id, image_path FROM donations WHERE id = %s", (donation_id,))
            donation = cursor.fetchone()
            
            if not donation:
                return JSONResponse(status_code=404, content={"message": "Donation not found"})
            
            # Delete from database (foreign key cascade will delete food items)
            cursor.execute("DELETE FROM donations WHERE id = %s", (donation_id,))
            connection.commit()
            
            # Delete image file if it exists
            if donation["image_path"]:
                image_path = os.path.join(".", donation["image_path"][1:])  # Remove leading slash
                if os.path.exists(image_path):
                    os.remove(image_path)
            
            return {"message": "Donation deleted successfully"}
    
    except Exception as e:
        print(f"Error deleting donation: {e}")
        raise HTTPException(status_code=500, detail=f"Database error: {str(e)}")

@app.post("/api/send-request-email/")
async def send_request_email(request: EmailRequest = Body(...)):
    try:
        # Log the request information (for debugging)
        print(f"Received request for donation: {request.donationId}")
        print(f"From: {request.requesterName} ({request.requesterEmail})")
        
        # For development: Mock the email sending without actually connecting
        # In production, uncomment and configure the SMTP section
        """
        # Create email message
        message = MIMEMultipart()
        message["From"] = EMAIL_FROM
        message["To"] = request.donorEmail
        message["Subject"] = f"New Food Request: {request.donationTitle}"
        
        # Email body
        email_body = f"..."
        
        # Attach HTML content
        message.attach(MIMEText(email_body, "html"))
        
        # Connect to SMTP server and send email
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_HOST_USER, EMAIL_HOST_PASSWORD)
            server.send_message(message)
        """
        
        # Instead, just log what would have been sent
        print(f"Would send email to: {request.donorEmail}")
        print(f"Email subject: New Food Request: {request.donationTitle}")
        
        # Return success response
        return {"status": "success", "message": "Email request processed successfully"}
    
    except Exception as e:
        print(f"Error in send_request_email: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to process email request: {str(e)}")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)