"""
Constrained LLM Information Extraction for Railway Defect Reports.
Uses Groq LLMs (openai/gpt-oss-120b or qwen/qwen3.8-27b) with strict JSON output schemas.
Includes an intelligent domain heuristic fallback for offline testing and resilience.
"""
import os
import re
import json
import logging
from typing import Optional, Dict, Any
from groq import Groq

logger = logging.getLogger(__name__)

PRIMARY_EXTRACTION_MODEL = "openai/gpt-oss-120b"
SECONDARY_EXTRACTION_MODEL = "qwen/qwen3.8-27b"

EXTRACTION_SYSTEM_PROMPT = """You are an expert railway operations AI parsing maintenance and defect reports for the Indian Railways Visakhapatnam-Vijayawada corridor.
Given an operator's unstructured report (transcribed from voice or typed), extract structured defect attributes and return STRICT JSON ONLY.

The JSON schema must match these fields exactly:
{
  "defect_type": string (e.g. "Rail Fracture", "Point Machine Failure", "OHE Catenary Wire Sag", "Track Buckling", "Signal Interlocking Failure", "Ballast Deficiency", "Insulator Flashover"),
  "description": string (concise, professional technical summary of the condition),
  "severity": string ("critical", "high", "medium", or "low"),
  "work_category": string ("defect", "scheduled_maintenance", or "overdue_task"),
  "estimated_duration_min": integer (estimated minutes needed for repair or block possession, e.g. 60, 90, 120, 180),
  "urgency_hours": float (estimated hours within which work must finish; 1-4 for critical, 6-12 for high, 24-48 for medium, 72+ for low),
  "department": string ("TMS" for Track/Civil, "SMMS" for Signals/Telecom, "TDMS" for Traction/OHE),
  "raw_location_text": string (the exact portion of text mentioning stations, kilometers, tracks, or yards),
  "direction": string or null ("DN" if towards Vijayawada/down, "UP" if towards Visakhapatnam/up, or null if unspecified),
  "requires_track_block": boolean (true if track possession needed),
  "requires_signal_block": boolean (true if signal disconnection/block needed),
  "requires_power_block": boolean (true if OHE power isolation needed)
}

RULES:
- Never include explanatory prose or markdown fences outside the JSON object.
- If duration is not stated, infer realistic railway duration (e.g. 90m for rail fracture, 120m for point machine, 60m for OHE sag, 120m for tamping).
- Severity mapping:
  * critical: rail fracture, track buckling, derailment risk, catenary snapped, signal red failure
  * high: point machine failure, significant weld defect, deep ballast washaway, insulator flashover
  * medium: ballast deficiency, minor OHE tension loss, routine relay review
  * low: routine inspection, tamping cycle, cosmetic patrolling
"""

class DefectExtractor:
    """
    Extracts structured railway defect parameters from plain natural-language text.
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self._client: Optional[Groq] = None
        if self.api_key:
            try:
                self._client = Groq(api_key=self.api_key)
            except Exception as e:
                logger.warning(f"Failed to initialize Groq client for extraction: {e}")

    def is_available(self) -> bool:
        return self._client is not None

    def extract_structured_defect(
        self,
        text: str,
        department_hint: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Extracts structured defect schema fields from natural language text.
        Tries primary LLM (gpt-oss-120b), falls back to secondary LLM (qwen3.8-27b),
        and if offline falls back to rule-based heuristic extraction.
        """
        if not text or not text.strip():
            raise ValueError("Input report text cannot be empty.")

        # Attempt LLM extraction if client is available
        if self._client:
            for model_name in [PRIMARY_EXTRACTION_MODEL, SECONDARY_EXTRACTION_MODEL]:
                try:
                    user_msg = f"Report text: \"{text.strip()}\""
                    if department_hint:
                        user_msg += f"\nReporting department hint: {department_hint}"

                    resp = self._client.chat.completions.create(
                        model=model_name,
                        messages=[
                            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
                            {"role": "user", "content": user_msg}
                        ],
                        response_format={"type": "json_object"},
                        temperature=0.1,
                    )
                    raw_content = resp.choices[0].message.content
                    parsed = json.loads(raw_content)
                    
                    # Validate and normalize
                    normalized = self._normalize_extracted_json(parsed, text, department_hint)
                    normalized["extraction_method"] = f"groq-llm:{model_name}"
                    logger.info(f"Successfully extracted structured defect using {model_name}.")
                    return normalized
                except Exception as e:
                    logger.warning(f"Groq extraction failed with {model_name}: {e}")

        # Resilient offline heuristic fallback
        logger.info("Using resilient heuristic rule extractor fallback.")
        fallback_res = self._heuristic_fallback_extract(text, department_hint)
        fallback_res["extraction_method"] = "heuristic-rule-fallback"
        return fallback_res

    def _normalize_extracted_json(self, data: Dict[str, Any], raw_text: str, department_hint: Optional[str]) -> Dict[str, Any]:
        """
        Validates and cleans LLM-extracted JSON to ensure strict compliance with backend schemas.
        """
        dept = (department_hint or data.get("department") or "TMS").upper()
        if dept not in ["TMS", "SMMS", "TDMS"]:
            dept = "TMS"

        severity = str(data.get("severity", "medium")).lower()
        if severity not in ["low", "medium", "high", "critical"]:
            severity = "medium"

        work_category = str(data.get("work_category", "defect")).lower()
        if work_category not in ["defect", "scheduled_maintenance", "overdue_task"]:
            work_category = "defect"

        duration = data.get("estimated_duration_min")
        try:
            duration = max(15, min(720, int(duration)))
        except (TypeError, ValueError):
            duration = 90

        urgency_hours = data.get("urgency_hours")
        try:
            urgency_hours = max(0.5, min(168.0, float(urgency_hours)))
        except (TypeError, ValueError):
            urgency_hours = 4.0 if severity == "critical" else (12.0 if severity == "high" else 24.0)

        defect_type = str(data.get("defect_type", "Track Defect")).strip()[:50]
        description = str(data.get("description", raw_text)).strip()
        raw_location = str(data.get("raw_location_text", raw_text)).strip()

        direction = data.get("direction")
        if direction:
            direction = str(direction).upper().strip()
            if direction not in ["DN", "UP"]:
                direction = None

        req_track = bool(data.get("requires_track_block", dept == "TMS"))
        req_signal = bool(data.get("requires_signal_block", dept == "SMMS"))
        req_power = bool(data.get("requires_power_block", dept == "TDMS"))

        return {
            "department": dept,
            "defect_type": defect_type,
            "description": description,
            "severity": severity,
            "work_category": work_category,
            "estimated_duration_min": duration,
            "urgency_hours": urgency_hours,
            "raw_location_text": raw_location,
            "direction": direction,
            "requires_track_block": req_track,
            "requires_signal_block": req_signal,
            "requires_power_block": req_power,
        }

    def _heuristic_fallback_extract(self, text: str, department_hint: Optional[str]) -> Dict[str, Any]:
        """
        Intelligent deterministic regex and keyword extractor for offline resilience.
        """
        text_lower = text.lower()

        # 1. Department inference
        dept = department_hint or "TMS"
        if any(w in text_lower for w in ["ohe", "catenary", "pantograph", "wire", "traction", "insulator", "mast"]):
            dept = "TDMS"
        elif any(w in text_lower for w in ["signal", "point machine", "interlocking", "relay", "axle counter", "track circuit"]):
            dept = "SMMS"
        elif any(w in text_lower for w in ["rail", "track", "weld", "sleeper", "ballast", "tamping", "fracture", "geometry"]):
            dept = "TMS"

        # 2. Defect Type
        defect_type = "Track Defect"
        if "rail fracture" in text_lower:
            defect_type = "Rail Fracture"
        elif "point machine" in text_lower:
            defect_type = "Point Machine Failure"
        elif "catenary" in text_lower or "ohe wire" in text_lower or "wire sag" in text_lower:
            defect_type = "OHE Catenary Wire Sag"
        elif "weld" in text_lower:
            defect_type = "Thermit Weld Defect"
        elif "ballast" in text_lower:
            defect_type = "Ballast Deficiency"
        elif "signal" in text_lower:
            defect_type = "Signal Lamp / Circuit Failure"
        elif "tamping" in text_lower:
            defect_type = "Mechanized Tamping Maintenance"
        elif "insulator" in text_lower:
            defect_type = "Insulator Flashover"

        # 3. Severity
        severity = "medium"
        if any(w in text_lower for w in ["fracture", "buckl", "broken", "critical", "emergency", "derail", "severe", "halt"]):
            severity = "critical"
        elif any(w in text_lower for w in ["urgent", "failure", "failed", "high", "danger", "cut"]):
            severity = "high"
        elif any(w in text_lower for w in ["routine", "periodic", "low", "minor", "scheduled", "patrol"]):
            severity = "low"

        # 4. Estimated Duration
        duration = 90
        dur_match = re.search(r'(\d+)\s*(?:min|minute|minutes|m\b)', text_lower)
        hr_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:hour|hours|hr|hrs)\b', text_lower)
        if dur_match:
            duration = int(dur_match.group(1))
        elif hr_match:
            duration = int(float(hr_match.group(1)) * 60)
        else:
            if severity == "critical":
                duration = 90
            elif severity == "high":
                duration = 120
            else:
                duration = 60

        # 5. Urgency hours
        urgency_hours = 4.0 if severity == "critical" else (12.0 if severity == "high" else 48.0)
        urg_match = re.search(r'before\s*(\d+)\s*(?:hour|hours|hr|hrs|pm|am)', text_lower)
        if "today" in text_lower:
            urgency_hours = 6.0
        elif "tomorrow" in text_lower:
            urgency_hours = 24.0

        # 6. Direction
        direction = None
        if "dn" in text_lower or "down" in text_lower or "towards vijayawada" in text_lower or "towards bza" in text_lower:
            direction = "DN"
        elif "up" in text_lower or "towards visakhapatnam" in text_lower or "towards vskp" in text_lower:
            direction = "UP"

        # 7. Work Category
        work_category = "defect"
        if any(w in text_lower for w in ["scheduled", "routine", "cycle", "periodic"]):
            work_category = "scheduled_maintenance"

        return {
            "department": dept,
            "defect_type": defect_type,
            "description": text.strip(),
            "severity": severity,
            "work_category": work_category,
            "estimated_duration_min": duration,
            "urgency_hours": urgency_hours,
            "raw_location_text": text.strip(),
            "direction": direction,
            "requires_track_block": dept == "TMS",
            "requires_signal_block": dept == "SMMS",
            "requires_power_block": dept == "TDMS",
        }
