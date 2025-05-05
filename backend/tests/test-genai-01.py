import os
from dotenv import load_dotenv
from google import genai

# Load environment variables from .env file
load_dotenv()

# Retrieve the API key from environment variables
api_key = os.environ.get("GEMINI_API_KEY")

# Check if the API key is available
if not api_key:
    raise ValueError("API key not found. Please set GOOGLE_API_KEY in your .env file.")

# Initialize the GenAI client with the API key
client = genai.Client(api_key=api_key)

# Start an interactive chat session
print("Welcome to the Gemini 2.0 Flash Chatbot! (Type 'quit' to exit)\n")

while True:
    user_input = input("You: ")
    if user_input.lower().strip() == "quit":
        print("Goodbye!")
        break

    try:
        response = client.models.generate_content(
            model="gemini-2.0-flash",
            contents=user_input
        )
        print(f"Gemini: {response.text.strip()}\n")
    except Exception as e:
        print(f"Error: {e}\n")