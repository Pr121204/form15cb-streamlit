import os
from dotenv import load_dotenv
from google import genai

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise RuntimeError("GEMINI_API_KEY not found in environment/.env")

client = genai.Client(api_key=api_key)

# Optional: list models to confirm what's available for your key
models = list(client.models.list())
print("First 15 models:")
for m in models[:15]:
    print("-", m.name)

model_name = os.getenv("GEMINI_MODEL_NAME", "gemini-2.0-flash")

resp = client.models.generate_content(
    model=model_name,
    contents="Reply only with OK"
)

print("\nResponse:", resp.text)
