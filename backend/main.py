from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Allows your frontend (running on a different address/port)
# to make requests to your backend.
app.add_middleware(
    CORSMiddleware,
    # In development, you often allow all origins.
    # In production, replace "*" with your frontend's actual domain/IP.
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"], # Allows GET, POST, PUT, DELETE, etc.
    allow_headers=["*"], # Allows all headers
)

@app.get("/hello")
async def read_hello():
    """
    A simple endpoint that returns a greeting message.
    """
    return {"message": "Hello from the FastAPI backend!"}

# To run this, you'll use uvicorn:
# uvicorn main:app --reload
# The --reload flag is handy during development as it restarts the server
# automatically when you save changes.
# By default, uvicorn runs on http://127.0.0.1:8000
