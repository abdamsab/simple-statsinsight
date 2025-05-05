import os
from dotenv import load_dotenv
from google import genai

# Load environment variables from .env file
load_dotenv()

# Retrieve the API key from environment variables
api_key = os.environ.get("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY not found in environment variables.")

# Initialize the GenAI client
client = genai.Client(api_key=api_key)

# Create a chat session for multi-turn conversation
chat = client.chats.create(model="gemini-2.0-flash")

# Start the interactive chat loop
print("Welcome to the Gemini 2.0 Flash Chatbot! (Type 'quit' to exit)\n")

while True:
    user_input = input("You: ")
    if user_input.lower().strip() == "quit":
        print("Goodbye!")
        break

    try:
        response = chat.send_message(user_input)
        print(f"Gemini: {response.text.strip()}\n")
    except Exception as e:
        print(f"Error: {e}\n")