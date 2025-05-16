from fastapi import APIRouter, HTTPException, Form, BackgroundTasks
from pydantic import BaseModel, EmailStr
import sqlite3
import secrets
import string
from datetime import datetime, timedelta
from typing import Optional
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

# Create a router for password reset functionality
router = APIRouter()

# Database settings
DB_PATH = "users.db"

# Email settings (replace with your actual SMTP settings)
SMTP_SERVER = "smtp.example.com"
SMTP_PORT = 587
SMTP_USERNAME = "your_email@example.com"
SMTP_PASSWORD = "your_email_password"
SENDER_EMAIL = "noreply@yourwebsite.com"

# Token settings
TOKEN_LENGTH = 64
TOKEN_EXPIRY_HOURS = 24

# Initialize reset tokens table if it doesn't exist
def init_reset_tokens_table():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS password_reset_tokens (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT NOT NULL,
        token TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP NOT NULL,
        used BOOLEAN DEFAULT 0
    )
    ''')
    conn.commit()
    conn.close()

# Model for request body
class PasswordResetRequest(BaseModel):
    email: EmailStr

class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str

# Helper function to send email
def send_password_reset_email(email: str, token: str):
    # Create reset URL with token
    reset_url = f"http://localhost:5000/reset-password.html?token={token}"
    
    # Create email content
    message = MIMEMultipart()
    message["From"] = SENDER_EMAIL
    message["To"] = email
    message["Subject"] = "Password Reset Request"
    
    # Email body
    body = f"""
    <html>
    <body>
        <h2>Password Reset Request</h2>
        <p>We received a request to reset your password. Click the link below to reset your password:</p>
        <p><a href="{reset_url}">Reset Your Password</a></p>
        <p>This link will expire in {TOKEN_EXPIRY_HOURS} hours.</p>
        <p>If you did not request a password reset, please ignore this email.</p>
    </body>
    </html>
    """
    
    message.attach(MIMEText(body, "html"))
    
    try:
        # Connect to SMTP server
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        
        # Send email
        server.sendmail(SENDER_EMAIL, email, message.as_string())
        server.quit()
        return True
    except Exception as e:
        print(f"Failed to send email: {e}")
        return False

# Generate a random token
def generate_token(length=TOKEN_LENGTH):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))

# Save token to database
def save_reset_token(email: str, token: str):
    # Calculate expiry time
    expiry_time = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRY_HOURS)
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # First invalidate any existing tokens for this email
    cursor.execute(
        "UPDATE password_reset_tokens SET used = 1 WHERE email = ? AND used = 0",
        (email,)
    )
    
    # Insert new token
    cursor.execute(
        "INSERT INTO password_reset_tokens (email, token, expires_at) VALUES (?, ?, ?)",
        (email, token, expiry_time)
    )
    
    conn.commit()
    conn.close()

# Verify token is valid
def verify_token(token: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute(
        "SELECT email, expires_at FROM password_reset_tokens WHERE token = ? AND used = 0",
        (token,)
    )
    
    result = cursor.fetchone()
    conn.close()
    
    if not result:
        return None
    
    email, expires_at = result
    expiry_time = datetime.fromisoformat(expires_at)
    
    if datetime.utcnow() > expiry_time:
        # Token has expired, mark as used
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("UPDATE password_reset_tokens SET used = 1 WHERE token = ?", (token,))
        conn.commit()
        conn.close()
        return None
    
    return email

# Mark token as used
def mark_token_used(token: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("UPDATE password_reset_tokens SET used = 1 WHERE token = ?", (token,))
    conn.commit()
    conn.close()

# Update user password
def update_user_password(email: str, new_password_hash: str):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute(
        "UPDATE users SET password = ? WHERE email = ?",
        (new_password_hash, email)
    )
    
    success = cursor.rowcount > 0
    conn.commit()
    conn.close()
    
    return success

# Endpoints
@router.post("/request-password-reset")
async def request_password_reset(email: str = Form(...), background_tasks: BackgroundTasks = None):
    # Check if user exists
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
    user = cursor.fetchone()
    conn.close()
    
    if not user:
        # Don't reveal that the email doesn't exist for security
        return {"message": "If your email exists in our system, you will receive a password reset link."}
    
    # Generate token
    token = generate_token()
    
    # Save token to database
    save_reset_token(email, token)
    
    # Send email (in background to improve response time)
    if background_tasks:
        background_tasks.add_task(send_password_reset_email, email, token)
    else:
        # For development, we can just print the token
        print(f"Password reset token for {email}: {token}")
        # send_password_reset_email(email, token)
    
    return {"message": "If your email exists in our system, you will receive a password reset link."}

@router.post("/reset-password")
async def reset_password(token: str = Form(...), new_password: str = Form(...)):
    from ..main import pwd_context, UserCreate  # Import password hashing utility
    
    # Verify token
    email = verify_token(token)
    if not email:
        raise HTTPException(status_code=400, detail="Invalid or expired token")
    
    try:
        # Validate password using Pydantic model
        # This reuses the validation from UserCreate
        UserCreate(full_name="Temp Name", email=email, password=new_password)
        
        # Hash new password
        hashed_password = pwd_context.hash(new_password)
        
        # Update user's password
        success = update_user_password(email, hashed_password)
        
        if not success:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Mark token as used
        mark_token_used(token)
        
        return {"message": "Password has been reset successfully"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# Initialize the reset tokens table when the router is imported
init_reset_tokens_table()