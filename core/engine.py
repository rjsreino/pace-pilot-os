import os
import json
import logging
import datetime
import requests

from core.ingestion import EnvironmentState
from core.models import WorkoutDraft, UserSettings, WeeklyScheduleDraft
from core.parser import parse_workout_details, rebuild_workout_name, parse_day_offset
from core.sentiment import detect_sentiment, stem_word
from core.heuristics import evaluate_heuristics
from core.fallback import (
    generate_fallback_draft,
    generate_fallback_with_feedback,
    generate_fallback_weekly_schedule,
    generate_fallback_weekly_schedule_with_feedback,
    determine_weekly_frequency_and_slots,
    get_slot_parameters
)


# Set up logging
logger = logging.getLogger("PacePilot.Engine")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


# ==========================================
# Step 2: LLM Orchestration Layer (Gemini API)
# ==========================================

def clean_json_response(raw_text: str) -> str:
    """
    Cleans markdown backticks (```json ... ```) and filters conversational trailing/leading text
    to extract the raw JSON string.
    """
    raw_text = raw_text.strip()
    if raw_text.startswith("```"):
        import re
        raw_text = re.sub(r"^```(?:json)?\s*", "", raw_text)
        raw_text = re.sub(r"\s*```$", "", raw_text)
    raw_text = raw_text.strip()
    import re
    match = re.search(r"(\{.*\}|\[.*\])", raw_text, re.DOTALL)
    if match:
        raw_text = match.group(1)
    return raw_text.strip()

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
        model_name = os.getenv("GEMINI_MODEL", "gemma-4-31b-it")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
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
                raw_text = clean_json_response(raw_text)
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
        model_name = os.getenv("GEMINI_MODEL", "gemma-4-31b-it")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
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
                raw_text = clean_json_response(raw_text)
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


def generate_weekly_schedule_draft(settings: UserSettings, state: EnvironmentState) -> WeeklyScheduleDraft:
    """
    Central reasoning coordinator for weekly macro planning. Evaluates heuristics,
    then dispatches to Google Gemini with Pydantic JSON response constraints.
    Falls back to deterministic offline generation if keys are missing or requests fail.
    """
    heuristics = evaluate_heuristics(state, "60-minute Run", 3, 60)
    
    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.warning("No Gemini/Google API key found. Defaulting to local offline weekly schedule generator.")
        return generate_fallback_weekly_schedule(settings, state, heuristics)

    try:
        model_name = os.getenv("GEMINI_MODEL", "gemma-4-31b-it")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        headers = {"Content-Type": "application/json"}
        params = {"key": api_key}

        freq, slots = determine_weekly_frequency_and_slots(settings.target_weekly_mileage)
        
        slots_description = ""
        for slot in slots:
            pct, orig_zone, base_name = get_slot_parameters(settings.distance_goal, slot)
            slots_description += f"- \"{slot}\": Base intensity Zone {orig_zone}, volume split {int(pct*100)}%, Base workout: {base_name}\n"

        prompt_text = f"""
You are the reasoning engine of PacePilot, an agentic AI running coach.
Your task is to analyze the athlete's race distance goal and target weekly mileage along with environmental and recovery metrics to distribute the mileage across exactly {freq} sessions for the week.

You MUST return a list of workouts under the "schedule" key in your JSON response.
For each item in the "schedule" array, you MUST populate the "session_slot" field with one of these exact slot names in order:
{json.dumps(slots, indent=2)}

Session configuration guidelines:
{slots_description}

Athlete Ingested Parameters:
- Distance Goal: {settings.distance_goal}
- Target Weekly Mileage: {settings.target_weekly_mileage} km
- Sleep Score: {state.biometric.sleep_score}/100
- HRV Status: {state.biometric.hrv_status}
- Acute Training Load: {state.biometric.acute_training_load}
- Local Temperature: {state.weather.temperature_c}°C
- Local Humidity: {state.weather.humidity}%
- Weather Conditions: {state.weather.summary}

Heuristic Safety Caps to apply to ALL generated workouts:
- Temp Warning Triggered: {heuristics['temp_warning']}
- Biometric Recovery Warning Triggered: {heuristics['bio_warning']}
- Compounding Safety Lockout Triggered: {heuristics['compounding_warning']}

Training Philosophy rules:
1. 5K / 10K Goals: Short, high-intensity intervals (Zone 4/5 VO2 Max work), high stride frequencies, and shorter, faster long run sessions.
2. Half Marathon / Marathon Goals: Progressive steady-state tempo runs (Zone 3 aerobic threshold), cumulative volume handling, and long slow base runs (Zone 2 mitochondrial development).
3. Volume constraint: Distribute target weekly mileage to durations based on a baseline pace translation (approx 6.0 min/km for 5K/10K; 6.5 min/km for HALF/MARATHON).
   Total duration minutes = target weekly mileage * pace translation.
   For each session key, calculate the base planned duration as: total duration minutes * volume split.
4. Safety constraints:
   - If Compounding Safety Lockout is True: You MUST set the adjusted workouts for ALL days to an Active Recovery Walk (Zone 1, 30 minutes). Rationale must explain the compounding safety lockout.
   - If Biometric Recovery Warning is True: Cap all heart rate intensities to Zone 1 or Zone 2, and reduce the durations of all workouts by 40% (i.e. scale by 0.6). High intensity sessions (e.g. speed/intervals/tempo) must be capped at Zone 1 (active walk).
   - If Temperature Warning is True: Scale all durations down by 20% to prevent excess heat load.
   - Keep the rationale clear, concise, and capped at a maximum of 2 to 3 sentences. Avoid verbose introductory fluff.
   - Provide a single, powerful line item (under 10 words) identifying the primary physiological factor being evaluated or protected (e.g., 'Autonomic fatigue prevention & cardiac drift mitigation') in the 'physiological_focus' field of each workout.
"""

        schema = {
            "type": "OBJECT",
            "properties": {
                "schedule": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "session_slot": {"type": "STRING"},
                            "original_workout": {"type": "STRING"},
                            "adjusted_workout": {"type": "STRING"},
                            "target_zone": {"type": "INTEGER"},
                            "duration_minutes": {"type": "INTEGER"},
                            "physiological_focus": {"type": "STRING"},
                            "rationale": {"type": "STRING"},
                            "scheduled_start_iso": {"type": "STRING"}
                        },
                        "required": [
                            "session_slot",
                            "original_workout",
                            "adjusted_workout",
                            "target_zone",
                            "duration_minutes",
                            "physiological_focus",
                            "rationale",
                            "scheduled_start_iso"
                        ]
                    }
                }
            },
            "required": ["schedule"]
        }

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
                "responseSchema": schema
            }
        }

        logger.info("Requesting structured completion from Gemini API for weekly schedule...")
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
                raw_text = clean_json_response(raw_text)
                draft_dict = json.loads(raw_text)
                return WeeklyScheduleDraft(**draft_dict)

        raise ValueError("Invalid candidates block returned by Gemini API")

    except Exception as e:
        logger.error(f"Gemini API invocation failed: {e}. Falling back to offline weekly schedule generator.")
        return generate_fallback_weekly_schedule(settings, state, heuristics)


def regenerate_weekly_schedule_with_feedback(
    state_path: str,
    settings: UserSettings,
    user_feedback: str,
    draft_1: WeeklyScheduleDraft
) -> WeeklyScheduleDraft:
    """
    Re-runs the reasoning engine incorporating user subjective feedback.
    Maintains biometric safety boundaries (heuristics) but adapts training style.
    Allows scaling up to the heuristic safety bounds when user feedback indicates high energy.
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
        
    heuristics = evaluate_heuristics(state, "60-minute Run", 3, 60)

    # Detect high-energy signals in feedback
    sentiment = detect_sentiment(user_feedback)
    is_high_energy = (sentiment == "high_energy")

    api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if not api_key:
        logger.warning("No Gemini API key found for feedback regeneration. Falling back to local offline feedback weekly generator.")
        return generate_fallback_weekly_schedule_with_feedback(settings, state, heuristics, user_feedback, draft_1)

    try:
        model_name = os.getenv("GEMINI_MODEL", "gemma-4-31b-it")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
        headers = {"Content-Type": "application/json"}
        params = {"key": api_key}

        # Calculate safety caps for reference
        goal = settings.distance_goal
        mileage = settings.target_weekly_mileage
        pace_multiplier = 6.0 if goal in ["5K", "10K"] else 6.5
        total_duration = mileage * pace_multiplier
        
        freq, slots = determine_weekly_frequency_and_slots(mileage)
        
        safety_caps = {}
        for day_key in slots:
            pct, orig_zone, base_name = get_slot_parameters(goal, day_key)
            orig_duration = int(round(total_duration * pct))
            if heuristics["compounding_warning"]:
                max_duration = 30
                max_zone = 1
            elif heuristics["bio_warning"]:
                max_duration = int(round(orig_duration * 0.6))
                max_zone = 1 if any(term in day_key for term in ["Speed", "Interval", "Tempo"]) else 2
            elif heuristics["temp_warning"]:
                max_duration = int(round(orig_duration * 0.8))
                max_zone = orig_zone
            else:
                max_duration = orig_duration
                max_zone = orig_zone
            
            # Find in draft_1
            d1_w = None
            for w in draft_1.schedule:
                if w.session_slot == day_key:
                    d1_w = w
                    break
            
            if d1_w:
                d1_zone = d1_w.target_zone
                d1_duration = d1_w.duration_minutes
            else:
                d1_zone = orig_zone
                d1_duration = orig_duration
                
            if is_high_energy:
                safety_caps[day_key] = {"max_zone": max_zone, "max_duration": max_duration}
            else:
                safety_caps[day_key] = {"max_zone": min(d1_zone, max_zone), "max_duration": min(d1_duration, max_duration)}

        prompt_text = f"""
You are the reasoning engine of PacePilot, an agentic AI running coach.
The athlete rejected your initial weekly training schedule recommendation and provided subjective feedback.
Generate a new, revised WeeklyScheduleDraft that addresses their feedback while strictly maintaining safety boundaries.

Athlete's Subjective Feedback:
- User feels: "{user_feedback}"

Athlete Ingested Parameters:
- Distance Goal: {settings.distance_goal}
- Target Weekly Mileage: {settings.target_weekly_mileage} km
- Sleep Score: {state.biometric.sleep_score}/100
- HRV Status: {state.biometric.hrv_status}
- Local Temperature: {state.weather.temperature_c}°C

Your Initial Proposal (Draft 1):
"""
        for day_key in slots:
            d1_w = None
            for w in draft_1.schedule:
                if w.session_slot == day_key:
                    d1_w = w
                    break
            if d1_w:
                prompt_text += f"- {day_key}: {d1_w.adjusted_workout} (Zone {d1_w.target_zone}, {d1_w.duration_minutes} min)\n"

        prompt_text += "\nSafety Guidelines (DO NOT EXCEED):\n"
        for day_key, cap in safety_caps.items():
            prompt_text += f"- {day_key} Cap: Zone {cap['max_zone']}, Duration {cap['max_duration']} min\n"

        prompt_text += f"""
Adaptation instructions:
1. You MUST return a list of workouts under the "schedule" key in your JSON response.
2. For each item in the "schedule" array, you MUST populate the "session_slot" field with one of these exact slot names in order:
{json.dumps(slots, indent=2)}
3. You MUST NOT exceed the Maximum Safety Zone Cap or the Maximum Recommended Duration for each day.
4. Adapt the workouts to address user feedback:
   - If user reports high-energy/readiness ("{user_feedback}"), you may scale the workouts UP to the maximum allowed by the safety bounds.
   - If user reports soreness/fatigue/pain, scale all workouts DOWN or modify structure accordingly (e.g. Speed/Intervals become walk, other days are shortened or turned into mobility/stretching).
5. Keep the rationales clear, concise, and capped at 2 to 3 sentences.
6. Provide a single, powerful physiological_focus under 10 words for each workout in the 'physiological_focus' field.
"""

        schema = {
            "type": "OBJECT",
            "properties": {
                "schedule": {
                    "type": "ARRAY",
                    "items": {
                        "type": "OBJECT",
                        "properties": {
                            "session_slot": {"type": "STRING"},
                            "original_workout": {"type": "STRING"},
                            "adjusted_workout": {"type": "STRING"},
                            "target_zone": {"type": "INTEGER"},
                            "duration_minutes": {"type": "INTEGER"},
                            "physiological_focus": {"type": "STRING"},
                            "rationale": {"type": "STRING"},
                            "scheduled_start_iso": {"type": "STRING"}
                        },
                        "required": [
                            "session_slot",
                            "original_workout",
                            "adjusted_workout",
                            "target_zone",
                            "duration_minutes",
                            "physiological_focus",
                            "rationale",
                            "scheduled_start_iso"
                        ]
                    }
                }
            },
            "required": ["schedule"]
        }

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
                "responseSchema": schema
            }
        }

        logger.info("Requesting feedback-adjusted completion from Gemini API for weekly schedule...")
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
                raw_text = clean_json_response(raw_text)
                draft_dict = json.loads(raw_text)
                draft = WeeklyScheduleDraft(**draft_dict)
                for day_key, cap in safety_caps.items():
                    for w in draft.schedule:
                        if w.session_slot == day_key:
                            w.target_zone = min(cap["max_zone"], w.target_zone)
                            w.duration_minutes = min(cap["max_duration"], w.duration_minutes)
                            break
                return draft

        raise ValueError("Invalid candidates block returned by Gemini API")

    except Exception as e:
        logger.error(f"Feedback-adjusted Gemini API call failed: {e}. Falling back to offline feedback weekly generator.")
        return generate_fallback_weekly_schedule_with_feedback(settings, state, heuristics, user_feedback, draft_1)

        raise ValueError("Invalid candidates block returned by Gemini API")

    except Exception as e:
        logger.error(f"Feedback-adjusted Gemini API call failed: {e}. Falling back to offline feedback weekly generator.")
        return generate_fallback_weekly_schedule_with_feedback(settings, state, heuristics, user_feedback, draft_1)


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
