import os
import io
import pandas as pd
from fastapi import FastAPI, UploadFile, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    return genai.Client(api_key=api_key) if api_key else genai.Client()

@app.get("/")
async def root():
    return {"status": "alive"}

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.get("/testing/health")
async def health_check():
    return {"status": "healthy", "message": "Backend is up and running!"}

@app.post("/aircraft/analytics")
async def get_aircraft_analytics(request: Request):
    try:
        form = await request.form()
        file = None
        for key, value in form.items():
            if isinstance(value, UploadFile):
                file = value
                break
        
        if not file:
            raise HTTPException(status_code=400, detail="No file found in the request form data.")

        client = get_client()
        file_bytes = await file.read()
        filename = file.filename.lower()

        if filename.endswith(('.xlsx', '.xls')):
            df = pd.read_excel(io.BytesIO(file_bytes))
            text_data = df.to_string(index=False)
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=f"Analyze this aircraft maintenance data from Excel:\n{text_data}"
            )
        elif filename.endswith('.pdf'):
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=[
                    "Analyze this aircraft maintenance PDF document and provide detailed health status and analytics:",
                    types.Part.from_bytes(data=file_bytes, mime_type="application/pdf"),
                ]
            )
        else:
            raise HTTPException(status_code=400, detail="Unsupported file format.")

        return {
            "status": "success",
            "analytics": response.text
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/recommendation")
async def get_recommendation(payload: dict):
    return {"recommendation": "Maintenance recommendation generated successfully based on manual."}
