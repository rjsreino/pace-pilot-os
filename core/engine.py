import os
import json
import logging
import datetime
import re
from typing import Optional
import requests
from pydantic import BaseModel, Field
from core.ingestion import EnvironmentState

# Set up logging
logger = logging.getLogger("PacePilot.Engine")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


# ==========================================
# 1. Data Schema (Pydantic v2)
# ==========================================

class WorkoutDraft(BaseModel):
    original_workout: str = Field(..., description="The name or description of the planned workout")
    adjusted_workout: str = Field(..., description="The name or description of the modified workout")
    target_zone: int = Field(..., description="Target training heart rate zone (1 to 5)")
    duration_minutes: int = Field(..., description="Target duration of the workout in minutes")
    rationale: str = Field(..., description="Detailed explanation of physiological or environmental adjustments")


# ==========================================
# Helper Utilities
# ==========================================

def parse_workout_details(workout_name: str) -> tuple[int, int]:
    """
    Parses common running community target zones and duration in minutes
    from standard workout titles (e.g. '60-minute Threshold Tempo Run').
    """
    # Default parameters
    default_zone = 2
    default_duration = 45

    # 1. Parse Duration
    duration_match = re.search(r"(\d+)\s*-?\s*minute", workout_name, re.IGNORECASE)
    if duration_match:
        duration = int(duration_match.group(1))
    else:
        min_match = re.search(r"(\d+)\s*(?:min|mins)", workout_name, re.IGNORECASE)
        if min_match:
            duration = int(min_match.group(1))
        else:
            duration = default_duration

    # 2. Parse Zone using standard running terminologies
    name_lower = workout_name.lower()
    if "zone 1" in name_lower or "recovery" in name_lower:
        zone = 1
    elif "zone 2" in name_lower or "easy" in name_lower:
        zone = 2
    elif "zone 3" in name_lower or "tempo" in name_lower:
        zone = 3
    elif "zone 4" in name_lower or "uptempo" in name_lower:
        zone = 4
    elif "zone 5" in name_lower or "threshold" in name_lower or "interval" in name_lower:
        zone = 5
    else:
        zone = default_zone

    return zone, duration


# ==========================================
# Step 1: Heuristic Climate-Biometric Engine
# ==========================================

def evaluate_heuristics(
    state: EnvironmentState,
    original_workout: str,
    original_zone: int,
    original_duration: int
) -> dict:
    """
    Applies deterministic physiological and thermal rules to compute training adjustments.
    - Temperature > 28°C: reduces duration by 20% due to thermal stress / cardiac drift.
    - Sleep < 60 or Low/Unbalanced HRV: Caps intensity to Zone 1 or 2, slices volume by 40%.
    - Compounding triggers: Forces low-intensity rest day or active walk.
    """
    temp_warning = False
    bio_warning = False
    
    rec_zone = original_zone
    rec_duration = original_duration

    # 1. Temperature Constraint (Cardiac Drift)
    if state.weather.temperature_c > 28.0:
        temp_warning = True
        rec_duration = int(rec_duration * 0.8)  # 20% duration reduction
        logger.info(f"Heuristics: High temperature ({state.weather.temperature_c}°C) triggered 20% duration reduction.")

    # 2. Biometric Constraint (Insufficent Recovery)
    hrv_status_upper = state.biometric.hrv_status.upper() if state.biometric.hrv_status else "UNKNOWN"
    if (state.biometric.sleep_score < 60) or (hrv_status_upper in ["LOW", "UNBALANCED"]):
        bio_warning = True
        rec_zone = min(rec_zone, 2)            # Force intensity zone 1 or 2
        rec_duration = int(rec_duration * 0.6)  # 40% duration reduction
        logger.info(f"Heuristics: Poor biometrics (Sleep: {state.biometric.sleep_score}, HRV: {hrv_status_upper}) triggered down-regulation.")

    # 3. Compounding Constraint (Extreme combined stress)
    compounding_warning = temp_warning and bio_warning
    if compounding_warning:
        rec_zone = 1
        rec_duration = 30  # Fixed low volume recovery walk/activity
        logger.warning("Heuristics: Compounding safety warning active. Capping to Zone 1 light walk.")

    return {
        "temp_warning": temp_warning,
        "bio_warning": bio_warning,
        "compounding_warning": compounding_warning,
        "recommended_zone": rec_zone,
        "recommended_duration": rec_duration
    }


# ==========================================
# Step 3: Robust Local Fallback (No-Key Support)
# ==========================================

def generate_fallback_draft(
    original_workout: str,
    original_zone: int,
    original_duration: int,
    state: EnvironmentState,
    heuristics: dict
) -> WorkoutDraft:
    """
    Generates a high-quality WorkoutDraft object locally using deterministic templates.
    Ensures execution safety when API keys are absent or endpoints time out.
    """
    temp = state.weather.temperature_c
    sleep = state.biometric.sleep_score
    hrv = state.biometric.hrv_status
    
    if heuristics["compounding_warning"]:
        adjusted_workout = "30-minute Active Recovery Walk"
        rationale = (
            f"SAFETY LOCKOUT TRIGGERED. Autonomic balance is critical (HRV: {hrv}, Sleep Score: {sleep}/100) "
            f"coupled with high environmental heat strain ({temp}°C > 28°C). Executing high-intensity or extended "
            f"cardiovascular training today presents acute dehydration and physiological overreaching risks. "
            f"Adjusted to a low-intensity active recovery walk."
        )
        return WorkoutDraft(
            original_workout=original_workout,
            adjusted_workout=adjusted_workout,
            target_zone=1,
            duration_minutes=30,
            rationale=rationale
        )
        
    elif heuristics["bio_warning"]:
        adjusted_zone = heuristics["recommended_zone"]
        adjusted_duration = heuristics["recommended_duration"]
        adjusted_workout = f"Recovery Run (Cap Zone {adjusted_zone})"
        rationale = (
            f"BIOMETRIC INTENSITY DOWNGRADE. Under-recovery markers detected: Sleep score ({sleep}/100) "
            f"or HRV status is ({hrv}). Performing high heart-rate work under parasympathetic depression "
            f"delays adaptation and risks injury. Target zone restricted to Zone {adjusted_zone} "
            f"and training duration reduced by 40% to {adjusted_duration} minutes."
        )
        return WorkoutDraft(
            original_workout=original_workout,
            adjusted_workout=adjusted_workout,
            target_zone=adjusted_zone,
            duration_minutes=adjusted_duration,
            rationale=rationale
        )
        
    elif heuristics["temp_warning"]:
        adjusted_duration = heuristics["recommended_duration"]
        adjusted_workout = f"Heat-adjusted {original_workout}"
        rationale = (
            f"THERMAL STRESS DURATION CAP. Local temperature is ({temp}°C), which exceeds the 28°C threshold. "
            f"Extended efforts in elevated temperatures elevate blood viscosity and trigger cardiac drift "
            f"(upward drift in heart rate relative to power/pace). Workout duration scaled back by 20% "
            f"to {adjusted_duration} minutes to manage cardiovascular drift."
        )
        return WorkoutDraft(
            original_workout=original_workout,
            adjusted_workout=adjusted_workout,
            target_zone=original_zone,
            duration_minutes=adjusted_duration,
            rationale=rationale
        )
        
    else:
        rationale = (
            f"FIT FOR TRAINING. Physiological parameters (Sleep: {sleep}/100, HRV: {hrv}) are in optimal ranges, "
            f"and environmental factors ({temp}°C, {state.weather.humidity}% humidity) present no heat stress constraints. "
            f"Proceeding with the original training protocol."
        )
        return WorkoutDraft(
            original_workout=original_workout,
            adjusted_workout=original_workout,
            target_zone=original_zone,
            duration_minutes=original_duration,
            rationale=rationale
        )


# ==========================================
# Step 2: LLM Orchestration Layer (Gemini API)
# ==========================================

def generate_workout_draft(original_workout: str, state: EnvironmentState) -> WorkoutDraft:
    """
    Central reasoning coordinator. Evaluates heuristics first, then dispatches
    to Google Gemini (gemini-2.5-flash) with Pydantic JSON response constraints.
    Falls back to deterministic generation if keys are missing or requests fail.
    """
    original_zone, original_duration = parse_workout_details(original_workout)
    heuristics = evaluate_heuristics(state, original_workout, original_zone, original_duration)

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.warning("No Gemini/Google API key found. Defaulting to local offline heuristic engine.")
        return generate_fallback_draft(original_workout, original_zone, original_duration, state, heuristics)

    try:
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
        headers = {"Content-Type": "application/json"}
        params = {"key": api_key}

        prompt_text = f"""
You are the reasoning engine of PacePilot, an agentic AI running coach.
Your task is to analyze the athlete's environmental and recovery metrics and adjust their target workout draft.

Original Target Workout:
- Name: {original_workout}
- Planned Zone: Zone {original_zone}
- Planned Duration: {original_duration} minutes

Athlete Ingested Parameters:
- Sleep Score: {state.biometric.sleep_score}/100
- HRV Status: {state.biometric.hrv_status}
- Acute Training Load: {state.biometric.acute_training_load}
- Local Temperature: {state.weather.temperature_c}°C
- Local Humidity: {state.weather.humidity}%
- Weather Conditions: {state.weather.summary}

Heuristic Bounds Check:
- Temp Warning Triggered: {heuristics['temp_warning']}
- Biometric Recovery Warning Triggered: {heuristics['bio_warning']}
- Compounding Safety Lockout Triggered: {heuristics['compounding_warning']}
- Suggested Target Zone Cap: Zone {heuristics['recommended_zone']}
- Suggested Duration limit: {heuristics['recommended_duration']} minutes

Decision Directives:
1. If Compounding Safety Lockout is True, you MUST set the adjusted workout to a Rest Day or Active Walk (Zone 1, 20-30 minutes).
2. If Biometric Recovery Warning is True, cap the heart rate intensity to Zone 1 or Zone 2, and reduce the duration.
3. If Temperature Warning is True, scale duration down by 15-20% to prevent excess heat load.
4. Elaborate on the rationale using standard athletic training terminology (e.g., cardiac drift, EPOC, parasympathetic nervous system, recovery window, autonomic fatigue).
"""

        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": prompt_text
                        }
                    ]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": {
                    "type": "OBJECT",
                    "properties": {
                        "original_workout": {"type": "STRING"},
                        "adjusted_workout": {"type": "STRING"},
                        "target_zone": {"type": "INTEGER"},
                        "duration_minutes": {"type": "INTEGER"},
                        "rationale": {"type": "STRING"}
                    },
                    "required": ["original_workout", "adjusted_workout", "target_zone", "duration_minutes", "rationale"]
                }
            }
        }

        logger.info("Requesting structured completion from Gemini API...")
        response = requests.post(url, json=payload, headers=headers, params=params, timeout=25)
        response.raise_for_status()

        resp_json = response.json()
        candidates = resp_json.get("candidates", [])
        if candidates:
            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            if parts:
                raw_text = parts[0].get("text", "")
                logger.info("Successfully fetched Gemini response.")
                draft_dict = json.loads(raw_text)
                return WorkoutDraft(**draft_dict)

        raise ValueError("Invalid candidates block returned by Gemini API")

    except Exception as e:
        logger.error(f"Gemini API invocation failed: {e}. Falling back to offline engine.")
        return generate_fallback_draft(original_workout, original_zone, original_duration, state, heuristics)


# ==========================================
# 5. Verification Execution
# ==========================================

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    print("=" * 60)
    print("PacePilot - Phase 2 Agent Reasoning Engine Verification")
    print("=" * 60)

    # Resolve state file
    root_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    state_file = os.path.join(root_path, "state.json")
    
    current_state = None
    if os.path.exists(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
            current_state = EnvironmentState.model_validate(raw)
            print(f"Ingested state.json successfully from {os.path.basename(state_file)}.")
        except Exception as err:
            print(f"Could not load state.json: {err}. Fabricating mock state.")

    if current_state is None:
        # Mocking an under-recovered, hot-weather scenario
        from core.ingestion import BiometricData, WeatherData
        current_state = EnvironmentState(
            biometric=BiometricData(
                sleep_score=52,
                hrv_status="LOW",
                acute_training_load=520.0
            ),
            weather=WeatherData(
                temperature_c=30.5,
                humidity=75,
                summary="Hot and humid"
            ),
            iso_timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
        )
        print("Generated mock environment snapshot:")
        print(current_state.model_dump_json(indent=2))

    # Evaluate target workout
    baseline_workout = "60-minute Threshold Tempo Run"
    print(f"\nProcessing target workout: '{baseline_workout}'")
    
    workout_draft = generate_workout_draft(baseline_workout, current_state)
    
    print("\nResulting WorkoutDraft Output:")
    print(workout_draft.model_dump_json(indent=2))
    print("=" * 60)
