import os
import io
import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,   # can't combine wildcard origins with credentials
    allow_methods=["*"],
    allow_headers=["*"],
)

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.5-flash")

def get_client():
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    return genai.Client(api_key=api_key) if api_key else genai.Client()

COLUMN_MAP = {
    "Aircraft_ID": "Aircraft_ID",
    "Aircraft_Model": "Aircraft_Model",
    "Engine_Model": "Engine_Model",
    "Airport_Code": "Airport_Code",
    "Flight_Cycle (cycles)": "Flight_Cycle",
    "Flight_Hours (hrs)": "Flight_Hours",
    "Cycles_Since_Overhaul (cycles)": "Cycles_Since_Overhaul",
    "Last_Maintenance_Date": "Last_Maintenance_Date",
    "Ambient_Temperature (°C)": "Ambient_Temperature",
    "Humidity (%)": "Humidity",
    "Outside_Air_Temperature (°C)": "Outside_Air_Temperature",
    "Engine_Temperature (°C)": "Engine_Temperature",
    "Exhaust_Gas_Temperature (°C)": "Exhaust_Gas_Temperature",
    "Oil_Temperature (°C)": "Oil_Temperature",
    "Oil_Pressure (PSI)": "Oil_Pressure",
    "Engine_Vibration (mm/s)": "Engine_Vibration",
    "Compressor_Pressure (PSI)": "Compressor_Pressure",
    "Fuel_Flow (kg/hr)": "Fuel_Flow",
    "Hydraulic_Pressure (PSI)": "Hydraulic_Pressure",
    "Engine_RPM": "Engine_RPM",
    "Risk_Score (%)": "Risk_Score",
    "Remaining_Useful_Life (cycles)": "Remaining_Useful_Life",
    "Detected_Failure_Mode": "Detected_Failure_Mode",
    "Recommended_Maintenance_Action": "Recommended_Maintenance_Action",
    "Maintenance_Status": "Maintenance_Status",
}

def build_summary(df: pd.DataFrame):
    if df.empty:
        raise ValueError("The uploaded file contains no rows.")

    df = df.rename(columns={k: v for k, v in COLUMN_MAP.items() if k in df.columns})

    if "Flight_Cycle" in df.columns and pd.api.types.is_numeric_dtype(df["Flight_Cycle"]):
        sort_col = "Flight_Cycle"
    else:
        numeric_cols = df.select_dtypes(include="number").columns
        sort_col = numeric_cols[0] if len(numeric_cols) else None

    if sort_col is not None:
        df = df.sort_values(by=sort_col).reset_index(drop=True)

    latest_row = df.iloc[-1]
    window_size = min(10, len(df))
    baseline_df = df.iloc[:window_size]

    aircraft_id = str(latest_row.get("Aircraft_ID", "N/A"))

    current_record = {}
    for col in df.columns:
        val = latest_row[col]
        if pd.isna(val):
            current_record[col] = None
        elif isinstance(val, (int, float)):
            current_record[col] = float(val)
        else:
            current_record[col] = str(val)

    trend_columns = ["Ambient_Temperature", "Humidity", "Outside_Air_Temperature", "Engine_Temperature", "Exhaust_Gas_Temperature", "Oil_Temperature", "Oil_Pressure", "Engine_Vibration", "Compressor_Pressure", "Fuel_Flow", "Hydraulic_Pressure", "Engine_RPM", "Risk_Score", "Remaining_Useful_Life"]
    historical_analysis = []
    for col in trend_columns:
        if col not in df.columns:
            continue
        latest_value = latest_row[col]
        baseline_mean = baseline_df[col].mean()
        if pd.isna(latest_value) or pd.isna(baseline_mean) or baseline_mean == 0:
            change_percent = 0.0
        else:
            change_percent = ((latest_value - baseline_mean) / abs(baseline_mean)) * 100

        if col == "Remaining_Useful_Life":
            trend_direction = "DECREASING" if change_percent < -1 else ("INCREASING" if change_percent > 1 else "STABLE")
        else:
            trend_direction = "INCREASING" if change_percent > 1 else ("DECREASING" if change_percent < -1 else "STABLE")

        historical_analysis.append({
            "column": col,
            "latest_value": round(float(latest_value), 2) if not pd.isna(latest_value) else None,
            "change_percent": round(float(change_percent), 2),
            "trend_direction": trend_direction,
        })

    return {
        "aircraft_id": aircraft_id,
        "summary": {
            "current_record": current_record,
            "historical_analysis": historical_analysis,
            "latest_flight_cycle": current_record.get("Flight_Cycle"),
            "historical_window_size": window_size,
        },
    }

@app.get("/")
async def root():
    return {"status": "alive"}

@app.get("/api/health")
async def health():
    return {"status": "healthy"}

@app.get("/testing/health")
async def health_check():
    return {"status": "healthy", "message": "Backend is up and running!"}

async def _extract_upload_file(request: Request):
    form = await request.form()
    for _, value in form.items():
        if hasattr(value, "filename") and hasattr(value, "read"):
            return value
    return None

@app.post("/api/aircraft/analytics")
async def get_aircraft_analytics(request: Request):
    try:
        file = await _extract_upload_file(request)
        if not file or not file.filename:
            raise HTTPException(status_code=400, detail="No file found in the request form data.")

        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        filename = file.filename.lower()
        client = get_client()

        if filename.endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(file_bytes))
            summary_data = build_summary(df)
            text_data = df.to_string(index=False)
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=f"Analyze this aircraft maintenance data from Excel:\n{text_data}",
            )
            return {
                "status": "success",
                "analytics": response.text,
                "aircraft_id": summary_data["aircraft_id"],
                "summary": summary_data["summary"],
            }

        elif filename.endswith(".pdf"):
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[
                    "Analyze this aircraft maintenance PDF document and provide detailed health status and analytics:",
                    types.Part.from_bytes(data=file_bytes, mime_type="application/pdf"),
                ],
            )
            return {"status": "success", "analytics": response.text}

        else:
            raise HTTPException(status_code=400, detail="Unsupported file format. Use .xlsx, .xls, or .pdf.")

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
@app.post("/api/recommendation")
async def get_recommendation(request: Request):
    try:
        form = await request.form()
        analytics_text = form.get("analytics", "")
        if not analytics_text:
            raise HTTPException(status_code=400, detail="No analytics data provided.")

        manual_file = await _extract_upload_file(request)
        client = get_client()

        structured_prompt = (
            "Based on this aircraft maintenance analysis, produce a structured maintenance decision. "
            "Respond ONLY with valid JSON (no markdown, no code fences) matching exactly this schema:\n"
            "{\n"
            "  \"aircraft_id\": string,\n"
            "  \"aircraft_model\": string,\n"
            "  \"status_badges\": [string, ...],\n"
            "  \"summary_quote\": string,\n"
            "  \"ground_aircraft\": boolean,\n"
            "  \"alert_title\": string,\n"
            "  \"alert_subtitle\": string,\n"
            "  \"alert_message\": string,\n"
            "  \"alert_note\": string,\n"
            "  \"violations\": [{\"parameter\": string, \"observed\": string, \"threshold\": string}, ...],\n"
            "  \"root_cause_analysis\": string,\n"
            "  \"maintenance_actions\": [string, ...],\n"
            "  \"inspection_checklist\": [string, ...],\n"
            "  \"ambient_conditions\": string,\n"
            "  \"work_order\": {\"type\": string, \"priority\": string, \"description\": string}\n"
            "}\n"
            "status_badges should be short labels like GROUND AIRCRAFT, CRITICAL RISK, MONITOR, or HEALTHY. "
            "violations should list every parameter that breached a critical or warning threshold, with the observed value and the threshold it breached. "
            "root_cause_analysis should be 2-4 sentences explaining the most likely underlying mechanical or system cause based on the parameter pattern and manual guidance. "
            "maintenance_actions should be a short ordered list of concrete corrective actions to perform. "
            "inspection_checklist should be a short ordered list of specific physical inspection steps a technician would follow. "
            "ambient_conditions should be one sentence summarizing the ambient/environmental readings (temperature, humidity, OAT) and whether they are within normal range. "
            "work_order.type should be a short label such as UNSCHEDULED, LINE MAINTENANCE, or HEAVY CHECK. work_order.priority should be one of IMMEDIATE, SCHEDULED, or ROUTINE. work_order.description should be one sentence summarizing the work order. "
            "Base all values strictly on this analysis data:\n" + analytics_text
        )
        contents = [structured_prompt]

        if manual_file and manual_file.filename:
            file_bytes = await manual_file.read()
            if file_bytes:
                contents[0] += "\nAlso reference the attached maintenance manual PDF for manual-specific thresholds and guidance."
                contents.append(types.Part.from_bytes(data=file_bytes, mime_type="application/pdf"))

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents,
            config=types.GenerateContentConfig(response_mime_type="application/json"),
        )

        import json as _json
        structured = _json.loads(response.text)
        return structured

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)

