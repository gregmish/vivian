import requests
import json

response = requests.post(
    "http://localhost:11434/api/generate",
    headers={"Content-Type": "application/json"},
    json={
        "model": "mistral",
        "prompt": "Hello, who are you?",
        "stream": False
    }
)

print("REPLY FROM MODEL:")
print(response.json()["response"])