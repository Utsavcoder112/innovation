from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import google.generativeai as genai
import os
from typing import Dict, List
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Setup Gemini API - REPLACE WITH YOUR ACTUAL API KEY
GOOGLE_API_KEY = "AIzaSyDG9zXb55LcoiYNwfMZABYulx60IoHvhnE"  # Replace this with your actual Google API key
genai.configure(api_key=GOOGLE_API_KEY)

try:
    model = genai.GenerativeModel("gemini-2.0-flash")
    logger.info("Gemini model initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize Gemini model: {e}")
    model = None

# Enhanced system prompt for Nepali food chatbot
SYSTEM_PROMPT = """You are a knowledgeable and friendly  food expert assistant. You specialize in:
- Traditional Nepali dishes (dal-bhat, momo, gundruk, etc.)
- Regional Nepali cuisines (Newari, Thakali, etc.)
- Nepali cooking techniques and ingredients
- Nutritional information about Nepali foods
- Recipe suggestions and cooking tips
- Cultural significance of Nepali dishes
-Famous Indian cuisines
-Famous cuisines around the world

Always respond in a warm, helpful manner. If asked about non-food topics, politely redirect the conversation back to  cuisine. Keep responses concise but informative."""

# Create FastAPI app
app = FastAPI(title="Nepali Food Chatbot API", version="1.0.0")

# Enhanced CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:8080","http://127.0.0.1:8000", "*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["*"],
)

# In-memory conversation store (session_id -> list of messages)
conversation_memory: Dict[str, List[str]] = {}

# Request schema
class ChatRequest(BaseModel):
    message: str
    session_id: str

# Response schema
class ChatResponse(BaseModel):
    response: str
    session_id: str

# Health check endpoint
@app.get("/")
async def root():
    return {"message": "Nepali Food Chatbot API is running!", "status": "healthy"}

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "gemini_model": "available" if model else "unavailable"
    }

# POST endpoint for chatting
@app.post("/chat", response_model=ChatResponse)
async def chat_with_bot(chat_request: ChatRequest):
    try:
        if not model:
            logger.error("Gemini model not available")
            raise HTTPException(status_code=503, detail="AI model not available. Please check API key configuration.")
        
        user_message = chat_request.message.strip()
        session_id = chat_request.session_id
        
        if not user_message:
            raise HTTPException(status_code=400, detail="Message cannot be empty")
        
        logger.info(f"Received message from session {session_id[:8]}...")
        
        # Initialize memory if new session
        if session_id not in conversation_memory:
            conversation_memory[session_id] = []
            logger.info(f"New session created: {session_id[:8]}...")
        
        # Build conversation context
        conversation_context = [SYSTEM_PROMPT]
        
        # Add recent conversation history (last 6 messages to keep context manageable)
        recent_history = conversation_memory[session_id][-6:]
        conversation_context.extend(recent_history)
        
        # Add current user message
        conversation_context.append(f"User: {user_message}")
        
        # Generate response using Gemini
        full_prompt = "\n".join(conversation_context)
        
        response = model.generate_content(full_prompt)
        
        if not response.text:
            bot_response = "I'm sorry, I couldn't generate a response. Could you please rephrase your question?"
        else:
            bot_response = response.text.strip()
        
        # Update conversation memory
        conversation_memory[session_id].append(f"User: {user_message}")
        conversation_memory[session_id].append(f"Assistant: {bot_response}")
        
        # Limit memory size (keep last 20 messages)
        if len(conversation_memory[session_id]) > 20:
            conversation_memory[session_id] = conversation_memory[session_id][-20:]
        
        logger.info(f"Response generated for session {session_id[:8]}...")
        
        return ChatResponse(response=bot_response, session_id=session_id)
    
    except genai.types.generation_types.BlockedPromptException:
        logger.warning("Content was blocked by safety filters")
        return ChatResponse(
            response="I apologize, but I can't respond to that. Let's talk about delicious Nepali food instead! What would you like to know?",
            session_id=chat_request.session_id
        )
    
    except genai.types.generation_types.StopCandidateException:
        logger.warning("Generation stopped by safety filters")
        return ChatResponse(
            response="Let me help you with Nepali cuisine questions instead. What dish would you like to learn about?",
            session_id=chat_request.session_id
        )
    
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"An error occurred while processing your request: {str(e)}"
        )

# Clear conversation for a session (optional endpoint)
@app.delete("/chat/{session_id}")
async def clear_conversation(session_id: str):
    if session_id in conversation_memory:
        del conversation_memory[session_id]
        return {"message": f"Conversation cleared for session {session_id}"}
    return {"message": "Session not found"}

# Get conversation history (optional endpoint for debugging)
@app.get("/chat/{session_id}")
async def get_conversation(session_id: str):
    if session_id in conversation_memory:
        return {"conversation": conversation_memory[session_id][-10:]}  # Last 10 messages
    return {"conversation": []}

if __name__ == "__main__":
    import uvicorn
    print("Starting Nepali Food Chatbot API...")
    print("Make sure to:")
    print("1. Replace 'YOUR_GOOGLE_API_KEY' with your actual Google API key")
    print("2. Install required packages: pip install fastapi uvicorn google-generativeai")
    print("3. Access the frontend at http://localhost:8000 after starting")
    uvicorn.run(app, host="0.0.0.0", port=8000)