"""
Amazon Bedrock maintenance analyzer for the Aircraft Maintenance Platform.

This module sends deterministic engineering analytics plus the full internal
maintenance manual PDF to an LLM to return a structured maintenance report.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Protocol
import urllib.request
import urllib.error

from botocore.exceptions import BotoCoreError, ClientError


logger = logging.getLogger(__name__)

# Set your Gemini API key here or via environment variable GEMINI_API_KEY
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "YOUR_GEMINI_API_KEY_HERE")


class BedrockRuntimeClient(Protocol):
    """Minimal protocol for the boto3 Bedrock Runtime client."""

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        """Call the Bedrock Converse API."""


class AircraftMaintenanceAnalyzer:
    """
    Generate AI maintenance reports using AI and a manual PDF.
    """

    def __init__(
        self,
        bedrock_client: BedrockRuntimeClient,
        model_id: str,
        manual_pdf_path: str | Path,
        temperature: float = 0.2,
        max_tokens: int = 2_000,
        use_gemini_bypass: bool = True,  # Set to True to bypass AWS Bedrock block
    ) -> None:
        self.bedrock_client = bedrock_client
        self.model_id = model_id
        self.manual_pdf_path = Path(manual_pdf_path)
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.use_gemini_bypass = use_gemini_bypass

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
2. Aircraft maintenance standards and threshold procedures.

Important rules:
- Compare every engineering parameter in the analytics JSON against standard safe operating limits, risk matrix, decision trees, inspection procedures, failure modes, and maintenance actions.
- Do not invent thresholds, limits, failure modes, or maintenance actions without engineering justification.
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
        """Generate a structured AI maintenance report from analytics."""
        prompt = self.build_prompt(engineering_analytics)

        if self.use_gemini_bypass:
            logger.info("Using Google Gemini API bypass to analyze aircraft maintenance data...")
            response_text = self._call_gemini_api(prompt)
            return self._parse_json_response(response_text)

        # Default AWS Bedrock Route
        manual_bytes = self.load_manual()
        conversation = [
            {
                "role": "user",
                "content": [
                    {"text": prompt},
                    {
                        "document": {
                            "format": "pdf",
                            "name": self._document_name(),
                            "source": {"bytes": manual_bytes},
                        }
                    },
                ],
            }
        ]

        try:
            logger.info("Invoking Bedrock model: %s", self.model_id)
            response = self.bedrock_client.converse(
                modelId=self.model_id,
                messages=conversation,
                inferenceConfig={
                    "maxTokens": self.max_tokens,
                    "temperature": self.temperature,
                },
            )
        except (ClientError, BotoCoreError) as exc:
            logger.exception("Bedrock invocation failed")
            raise RuntimeError(
                f"Unable to invoke Bedrock model '{self.model_id}'"
            ) from exc

        response_text = self._extract_response_text(response)
        return self._parse_json_response(response_text)

    def _call_gemini_api(self, prompt_text: str) -> str:
        """Call Google Gemini REST API directly using standard library."""
        api_key = GEMINI_API_KEY
        if not api_key or api_key == "YOUR_GEMINI_API_KEY_HERE":
            raise ValueError("GEMINI_API_KEY is not set. Please set a valid Gemini API key.")

        url = f"[https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=](https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key=){api_key}"
        
        payload = json.dumps({
            "contents": [{"parts": [{"text": prompt_text}]}],
            "generationConfig": {
                "temperature": self.temperature,
                "maxOutputTokens": self.max_tokens,
                "responseMimeType": "application/json"
            }
        }).encode("utf-8")

        headers = {"Content-Type": "application/json"}
        req = urllib.request.Request(url, data=payload, headers=headers)

        try:
            with urllib.request.urlopen(req) as response:
                result = json.loads(response.read().decode("utf-8"))
                return result["candidates"][0]["content"]["parts"][0]["text"]
        except urllib.error.HTTPError as exc:
            err_body = exc.read().decode("utf-8")
            logger.error("Gemini API HTTP Error %d: %s", exc.code, err_body)
            raise RuntimeError(f"Gemini API request failed with status {exc.code}: {err_body}") from exc
        except Exception as exc:
            logger.exception("Gemini API request failed")
            raise RuntimeError("Failed to obtain response from Gemini API") from exc

    def _document_name(self) -> str:
        """Return a Bedrock-safe document name."""
        return self.manual_pdf_path.stem.replace("_", " ").replace("-", " ")

    @staticmethod
    def _extract_response_text(response: dict[str, Any]) -> str:
        """Extract text from a Bedrock Converse response."""
        try:
            content = response["output"]["message"]["content"]
        except KeyError as exc:
            raise ValueError("Bedrock response did not contain message content") from exc

        text_parts = [
            block["text"]
            for block in content
            if isinstance(block, dict) and "text" in block
        ]
        response_text = "\n".join(text_parts).strip()

        if not response_text:
            raise ValueError("Bedrock returned an empty response")

        return response_text

    @staticmethod
    def _parse_json_response(response_text: str) -> dict[str, Any]:
        """Parse and validate the JSON-only model response."""
        cleaned_text = response_text.strip()
        
        # Remove Markdown code block wrappers if returned by the LLM
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
