from fastapi import FastAPI
from pydantic import BaseModel
import requests

app = FastAPI(title="FDI PLN LLM")

class Prompt(BaseModel):
    prompt: str

@app.post("/generate")
def generate(data: Prompt):
    response = requests.post(
        "http://localhost:11434/api/generate",
        json={
            "model": "mistral",
            "prompt": data.prompt,
            "stream": False
        }
    )
    return response.json()

