"""
Google Gemini maintenance analyzer for the Aircraft Maintenance Platform.

This module sends deterministic engineering analytics plus the full internal
maintenance manual PDF directly to Google Gemini using native PDF support.
"""

from __future__ import annotations

import base64
import json
import logging
import os
from pathlib import Path
from typing import Any
import urllib.request
import urllib.error

logger = logging.getLogger(__name__)

# Keep placeholder for security; Kubernetes will inject the real key via env var
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")


class AircraftMaintenanceAnalyzer:
    """
    Generate AI maintenance reports using Google Gemini and a manual PDF.
    """

    def __init__(
        self,
        bedrock_client: Any,
        model_id: str,
        manual_pdf_path: str | Path,
        temperature: float = 0.2,
        max_tokens: int = 2_000,
    ) -> None:
        self.bedrock_client = bedrock_client
        self.model_id = model_id
        self.manual_pdf_path = Path(manual_pdf_path)
        self.temperature = temperature
        self.max_tokens = max_tokens

    def load_manual(self) -> bytes:
        """Load the complete aircraft maintenance manual PDF as bytes."""
        if not self.manual_pdf_path.exists():
            raise FileNotFoundError(
                f"Maintenance manual not found: {self.manual_pdf_path}"
            )

        if self.manual_pdf_path.suffix.lower() != ".pdf":
            raise ValueError(
                "Maintenance manual must be a PDF file. "
                f"Received: {self.manual_pdf_path}"
            )

        logger.info("Loading maintenance manual: %s", self.manual_pdf_path)
        return self.manual_pdf_path.read_bytes()

    def build_prompt(self, engineering_analytics: dict[str, Any]) -> str:
        """Build the model prompt from engineering analytics JSON."""
        analytics_json = json.dumps(
            engineering_analytics,
            indent=2,
            ensure_ascii=False,
            default=str,
        )

        return f"""
You are a Senior Aircraft Maintenance Engineer.

Your task is to generate a professional aircraft maintenance engineering report
using two inputs:

1. Engineering Analytics JSON provided below.
2. The attached internal Aircraft Maintenance Manual PDF.

Important rules:
- Compare every engineering parameter in the analytics JSON against the
  thresholds, safe operating limits, risk matrix, decision trees, inspection
  procedures, failure modes, and maintenance actions defined in the manual.
- Use only thresholds and maintenance procedures found in the attached manual.
- Do not invent thresholds, limits, failure modes, or maintenance actions.
- If a required threshold or procedure is unavailable in the manual, state that
  explicitly in the JSON output.
- Prioritize maintenance actions when multiple actions apply.
- Determine whether the aircraft status is one of:
  SAFE, MONITOR, MAINTENANCE REQUIRED, GROUND AIRCRAFT.
- Produce a final flight decision for the operations dashboard. The decision
  must clearly state whether the aircraft may fly now, may fly with monitoring,
  or must not fly until maintenance is completed.
- Return JSON only. Do not include Markdown, prose outside JSON, or code fences.

Required analysis:
- Health Status
- Failure Severity
- Threshold Violations
- Maintenance Recommendation
- Flight Readiness
- Final Fly / No-Fly Decision
- Inspection Required
- Root Cause
- Confidence
- Generated Work Order

Engineering Analytics JSON:
{analytics_json}

Return exactly one JSON object with this schema:
{{
  "aircraft": "string",
  "aircraft_model": "string",
  "health_status": "SAFE | MONITOR | MAINTENANCE REQUIRED | GROUND AIRCRAFT",
  "risk_level": "LOW | MEDIUM | HIGH | CRITICAL | UNKNOWN",
  "safe_for_next_flight": true,
  "final_flight_decision": {{
    "decision": "CLEARED_TO_FLY | FLY_WITH_MONITORING | MAINTENANCE_REQUIRED_BEFORE_FLIGHT | GROUND_AIRCRAFT",
    "can_fly_now": true,
    "ui_statement": "string",
    "required_before_next_flight": "string",
    "decision_rationale": "string"
  }},
  "overall_summary": "string",
  "threshold_violations": [
    {{
      "parameter": "string",
      "observed_value": "number or string",
      "manual_threshold": "string",
      "severity": "LOW | MEDIUM | HIGH | CRITICAL | UNKNOWN",
      "manual_reference": "string",
      "explanation": "string"
    }}
  ],
  "root_cause": {{
    "most_likely_cause": "string",
    "supporting_evidence": ["string"],
    "manual_reference": "string"
  }},
  "maintenance_actions": [
    {{
      "priority": 1,
      "action": "string",
      "reason": "string",
      "manual_reference": "string"
    }}
  ],
  "inspection_checklist": [
    {{
      "step": 1,
      "inspection_item": "string",
      "acceptance_criteria": "string",
      "manual_reference": "string"
    }}
  ],
  "work_order": {{
    "title": "string",
    "aircraft_id": "string",
    "work_order_type": "INSPECTION | REPAIR | MONITORING | GROUNDING",
    "priority": "LOW | MEDIUM | HIGH | CRITICAL",
    "tasks": ["string"],
    "required_parts_or_tools": ["string"],
    "estimated_maintenance_category": "string"
  }},
  "confidence": {{
    "score": 0.0,
    "rationale": "string",
    "missing_information": ["string"]
  }}
}}
""".strip()

    def analyze(self, engineering_analytics: dict[str, Any]) -> dict[str, Any]:
        """Generate a structured AI maintenance report using Google Gemini API."""
        prompt = self.build_prompt(engineering_analytics)
        manual_bytes = self.load_manual()
        pdf_base64 = base64.b64encode(manual_bytes).decode("utf-8")

        api_key = GEMINI_API_KEY
        if not api_key or api_key == "YOUR_GEMINI_API_KEY_HERE":
            api_key = os.getenv("GEMINI_API_KEY", "")

        if not api_key:
            raise ValueError("GEMINI_API_KEY is not set.")

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"

        payload = json.dumps({
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": "application/pdf",
                                "data": pdf_base64
                            }
                        }
                    ]
                }
            ],
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_tokens,
                "responseMimeType": "application/json"
            }
        }).encode("utf-8")

        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(url, data=payload, headers=headers)

        try:
            logger.info("Invoking Google Gemini API with native PDF manual...")
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode("utf-8"))
                response_text = result["candidates"][0]["content"]["parts"][0]["text"]
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8")
            logger.error("Gemini API HTTP Error %d: %s", exc.code, err_body)
            raise RuntimeError(f"Gemini API request failed with status {exc.code}: {err_body}") from exc
        except Exception as exc:
            logger.exception("Gemini API request failed")
            raise RuntimeError("Failed to obtain response from Gemini API") from exc

        return self._parse_json_response(response_text)

    @staticmethod
    def _parse_json_response(response_text: str) -> dict[str, Any]:
        """Parse and validate the JSON-only model response."""
        cleaned_text = response_text.strip()
        
        if cleaned_text.startswith("```"):
            lines = cleaned_text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned_text = "\n".join(lines).strip()

        try:
            parsed = json.loads(cleaned_text)
        except json.JSONDecodeError as exc:
            logger.error("Model returned non-JSON response: %s", response_text)
            raise ValueError("Model response was not valid JSON") from exc

        if not isinstance(parsed, dict):
            raise ValueError("Model response JSON must be an object")

        return parsed
