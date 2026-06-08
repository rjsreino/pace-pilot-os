import os
import json
import logging
import datetime
import requests

from core.ingestion import EnvironmentState
from core.models import WorkoutDraft
from core.parser import parse_workout_details, rebuild_workout_name
from core.sentiment import detect_sentiment, stem_word
from core.heuristics import evaluate_heuristics
from core.fallback import generate_fallback_draft, generate_fallback_with_feedback

# Set up logging
logger = logging.getLogger("PacePilot.Engine")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


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
4. Keep the rationale clear, concise, and capped at a maximum of 2 to 3 sentences. Avoid verbose introductory fluff. Use precise running terminology (e.g., cardiac drift, autonomic fatigue, recovery window) only where directly informative to the adjustment.
5. Provide a single, powerful line item (under 10 words) identifying the primary physiological factor being evaluated or protected (e.g., 'Autonomic fatigue prevention & cardiac drift mitigation', 'Central nervous system down-regulation', or 'Mitochondrial biogenesis optimization') in the 'physiological_focus' field.
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
                        "rationale": {"type": "STRING"},
                        "physiological_focus": {"type": "STRING"}
                    },
                    "required": ["original_workout", "adjusted_workout", "target_zone", "duration_minutes", "rationale", "physiological_focus"]
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
# Step 4: Feedback Refinement Layer (Gemini API & Fallback)
# ==========================================

def regenerate_with_feedback(
    state_path: str,
    original_workout: str,
    user_feedback: str,
    draft_1: WorkoutDraft
) -> WorkoutDraft:
    """
    Re-runs the reasoning engine incorporating user subjective feedback (e.g. 'Legs are sore').
    Maintains biometric safety boundaries (heuristics) but adapts training style.
    Allows scaling up up to the heuristic safety bounds when user feedback indicates high energy.
    """
    state = None
    if os.path.exists(state_path):
        try:
            with open(state_path, "r", encoding="utf-8") as f:
                raw = json.load(f)
            state = EnvironmentState.model_validate(raw)
        except Exception as e:
            logger.error(f"Failed to read state.json during feedback regeneration: {e}")
            
    if state is None:
        from core.ingestion import BiometricData, WeatherData
        state = EnvironmentState(
            biometric=BiometricData(sleep_score=70, hrv_status="BALANCED", acute_training_load=400.0),
            weather=WeatherData(temperature_c=20.0, humidity=60, summary="Clear"),
            iso_timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
        )
        
    original_zone, original_duration = parse_workout_details(original_workout)
    heuristics = evaluate_heuristics(state, original_workout, original_zone, original_duration)

    # Detect high-energy signals in feedback
    sentiment = detect_sentiment(user_feedback)
    is_high_energy = (sentiment == "high_energy")

    # Determine maximum boundaries for this regeneration
    if is_high_energy:
        max_allowed_zone = heuristics["recommended_zone"]
        max_allowed_duration = heuristics["recommended_duration"]
    else:
        max_allowed_zone = draft_1.target_zone
        max_allowed_duration = draft_1.duration_minutes

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.warning("No Gemini API key found for feedback regeneration. Falling back to local offline heuristic engine.")
        fallback = generate_fallback_with_feedback(original_workout, original_zone, original_duration, state, heuristics, user_feedback, draft_1)
        fallback.target_zone = min(max_allowed_zone, fallback.target_zone)
        fallback.duration_minutes = min(max_allowed_duration, fallback.duration_minutes)
        return fallback

    try:
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
        headers = {"Content-Type": "application/json"}
        params = {"key": api_key}

        prompt_text = f"""
You are the reasoning engine of PacePilot, an agentic AI running coach.
The athlete rejected your initial training recommendation and provided subjective feedback.
Generate a new, revised workout draft that addresses their feedback while strictly maintaining safety boundaries.

Original Planned Workout:
- Name: {original_workout}
- Planned Zone: Zone {original_zone}
- Planned Duration: {original_duration} minutes

Athlete Ingested Parameters:
- Sleep Score: {state.biometric.sleep_score}/100
- HRV Status: {state.biometric.hrv_status}
- Acute Training Load: {state.biometric.acute_training_load}
- Local Temperature: {state.weather.temperature_c}°C
- Local Humidity: {state.weather.humidity}%

Your Initial Proposal (Draft 1):
- Workout Name: {draft_1.adjusted_workout}
- Target Zone: Zone {draft_1.target_zone}
- Target Duration: {draft_1.duration_minutes} minutes
- Initial Rationale: {draft_1.rationale}

Athlete's Subjective Feedback:
- User feels: "{user_feedback}"

Heuristic Safety Bounds (DO NOT EXCEED):
- Maximum Safety Heart Rate Zone Cap: Zone {max_allowed_zone}
- Maximum Recommended Duration: {max_allowed_duration} minutes

Safety Guidelines:
1. You MUST NOT exceed the Maximum Safety Heart Rate Zone Cap or the Maximum Recommended Duration.
2. Adapt the workout to address the user feedback. 
   - If user reports high-energy/readiness ("{user_feedback}"), you may scale the workout UP to the maximum allowed by the safety bounds.
   - If user reports soreness/fatigue, scale the workout DOWN from Draft 1 and change structure accordingly (e.g. walk/stretching).
3. Keep the rationale clear, concise, and capped at a maximum of 2 to 3 sentences. Avoid verbose introductory fluff. Use precise running terminology (e.g., cardiac drift, autonomic fatigue, recovery window) only where directly informative to the adjustment.
4. Provide a single, powerful line item (under 10 words) identifying the primary physiological factor being evaluated or protected (e.g., 'Autonomic fatigue prevention & cardiac drift mitigation', 'Central nervous system down-regulation', or 'Mitochondrial biogenesis optimization') in the 'physiological_focus' field.
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
                        "rationale": {"type": "STRING"},
                        "physiological_focus": {"type": "STRING"}
                    },
                    "required": ["original_workout", "adjusted_workout", "target_zone", "duration_minutes", "rationale", "physiological_focus"]
                }
            }
        }

        logger.info("Requesting feedback-adjusted completion from Gemini API...")
        response = requests.post(url, json=payload, headers=headers, params=params, timeout=25)
        response.raise_for_status()

        resp_json = response.json()
        candidates = resp_json.get("candidates", [])
        if candidates:
            content = candidates[0].get("content", {})
            parts = content.get("parts", [])
            if parts:
                raw_text = parts[0].get("text", "")
                logger.info("Successfully fetched feedback-adjusted Gemini response.")
                draft_dict = json.loads(raw_text)
                draft = WorkoutDraft(**draft_dict)
                # Enforce strict safety boundary check
                draft.target_zone = min(max_allowed_zone, draft.target_zone)
                draft.duration_minutes = min(max_allowed_duration, draft.duration_minutes)
                return draft

        raise ValueError("Invalid candidates block returned by Gemini API")

    except Exception as e:
        logger.error(f"Feedback-adjusted Gemini API call failed: {e}. Falling back to offline fallback.")
        fallback = generate_fallback_with_feedback(original_workout, original_zone, original_duration, state, heuristics, user_feedback, draft_1)
        fallback.target_zone = min(max_allowed_zone, fallback.target_zone)
        fallback.duration_minutes = min(max_allowed_duration, fallback.duration_minutes)
        return fallback


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
