import os
import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from src.aircraft_maintenance.bedrock_maintenance_analyzer import AircraftMaintenanceAnalyzer
from src.aircraft_maintenance.engineering_analytics import AircraftEngineeringAnalytics

load_dotenv()

app = FastAPI(title="Aircraft Maintenance API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def root() -> dict[str, str]:
    return {"status": "ok", "service": "aircraft-maintenance-api"}

@app.get("/testing/health")
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "aircraft-maintenance-api"}

@app.post("/aircraft/analytics")
async def aircraft_analytics(excel_file: UploadFile = File(...)) -> dict[str, Any]:
    if not excel_file.filename:
        raise HTTPException(status_code=400, detail="Please upload an Excel file.")
    
    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(excel_file.filename).suffix) as temp_file:
            content = await excel_file.read()
            temp_file.write(content)
            temp_path = temp_file.name

        analytics = AircraftEngineeringAnalytics(excel_path=temp_path, sheet_name=0)
        analytics.load_dataset()
        aircraft_list = analytics.list_aircraft()
        if not aircraft_list:
            raise ValueError("No aircraft data found in the uploaded file.")

        first_aircraft = aircraft_list[0]
        summary = analytics.generate_summary(aircraft_id=first_aircraft, history_window=10)
        return {"message": "Analytics generated successfully", "aircraft_id": first_aircraft, "summary": summary.to_dict()}
    finally:
        if temp_path and os.path.exists(temp_path):
            os.remove(temp_path)

@app.post("/aircraft/maintenance-prediction")
def maintenance_prediction(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload:
        raise HTTPException(status_code=400, detail="Empty payload.")

    engineering_json = payload.get("summary", payload.get("engineering_json", payload))
    
    base_dir = Path(__file__).resolve().parent
    manual_pdf_path = str(base_dir / "data" / "AeroTech_ATX200_Maintenance_Manual.pdf")

    try:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable is not set.")

        analyzer = AircraftMaintenanceAnalyzer(
            manual_pdf_path=manual_pdf_path,
            temperature=0.2
        )
        report = analyzer.analyze(engineering_json)
        return {"success": True, "report": report}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Maintenance prediction failed: {exc}") from exc
