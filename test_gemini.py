import os
from dotenv import load_dotenv
import google.generativeai as genai

load_dotenv()
key = os.getenv("GEMINI_API_KEY")
model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
assert key, "No GEMINI_API_KEY in .env"

genai.configure(api_key=key)
m = genai.GenerativeModel(model)
r = m.generate_content("Say a 6-word roast about rubber ducks, PG-13.")
print("MODEL:", model)
print("TEXT :", getattr(r, "text", "(no text)"))
