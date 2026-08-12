import os
import json
import google.generativeai as genai
from typing import Any

class AircraftMaintenanceAnalyzer:
    def __init__(self, manual_pdf_path: str, temperature: float = 0.2, max_tokens: int = 2000):
        self.manual_pdf_path = manual_pdf_path
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("Google Gemini API Key is missing from environment variables!")
            
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('gemini-3.5-flash')

    def analyze(self, engineering_json: dict[str, Any]) -> str:
        prompt = f"""
        You are an expert aircraft maintenance AI.
        Please analyze the following engineering data and provide a detailed maintenance prediction report:
        
        {json.dumps(engineering_json, indent=2)}
        """
        
        response = self.model.generate_content(
            prompt,
            generation_config=genai.GenerationConfig(
                temperature=self.temperature,
                max_output_tokens=self.max_tokens
            )
        )
        
        return response.text
