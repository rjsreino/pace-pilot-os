import logging
from core.models import WorkoutDraft
from core.ingestion import EnvironmentState
from core.parser import rebuild_workout_name
from core.sentiment import detect_sentiment

# Set up logging
logger = logging.getLogger("PacePilot.Engine")

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


def generate_fallback_with_feedback(
    original_workout: str,
    original_zone: int,
    original_duration: int,
    state: EnvironmentState,
    heuristics: dict,
    user_feedback: str,
    draft_1: WorkoutDraft
) -> WorkoutDraft:
    """Offline rule-based fallback when Gemini API key is missing during regeneration."""
    sentiment = detect_sentiment(user_feedback)
    
    heur_zone = heuristics["recommended_zone"]
    heur_duration = heuristics["recommended_duration"]
    
    temp = state.weather.temperature_c
    sleep = state.biometric.sleep_score
    hrv = state.biometric.hrv_status

    if sentiment == "high_energy":
        # Scale up to Heuristic bounds (biometric/weather safety bounds)
        target_zone = heur_zone
        duration_minutes = heur_duration
        
        # If Heuristics actually match original planned workout, athlete can proceed in full
        if duration_minutes == original_duration and target_zone == original_zone:
            adjusted_workout = original_workout
            rationale = (
                f"OFFLINE READJUSTMENT: Athlete reported feeling strong and ready: '{user_feedback}'. "
                f"Biometrics and climate are optimal, allowing the athlete to perform the full "
                f"scheduled workout protocol."
            )
        elif heuristics["compounding_warning"]:
            adjusted_workout = "30-minute Active Recovery Walk"
            rationale = (
                f"OFFLINE READJUSTMENT: Athlete reported feeling strong and ready: '{user_feedback}'. "
                f"However, compounding safety lockout is active due to poor recovery (Sleep: {sleep}/100, HRV: {hrv}) "
                f"and ambient heat stress ({temp}°C). To prevent cardiovascular and autonomic overload, training is "
                f"capped at a Zone {target_zone} active recovery walk for {duration_minutes} minutes."
            )
        elif heuristics["bio_warning"]:
            adjusted_workout = rebuild_workout_name(original_workout, duration_minutes, "Biometrically-Capped")
            rationale = (
                f"OFFLINE READJUSTMENT: Athlete reported feeling strong and ready: '{user_feedback}'. "
                f"However, physiological indicators (Sleep: {sleep}/100, HRV: {hrv}) cap intensity at Zone {target_zone} "
                f"and duration at {duration_minutes} minutes to prevent autonomic overreaching."
            )
        else:
            adjusted_workout = rebuild_workout_name(original_workout, duration_minutes, "Heat-adjusted")
            rationale = (
                f"OFFLINE READJUSTMENT: Athlete reported feeling strong and ready: '{user_feedback}'. "
                f"However, ambient heat stress ({temp}°C) requires keeping the 20% duration cap to "
                f"{duration_minutes} minutes, though heart rate is permitted up to Zone {target_zone}."
            )
    elif sentiment == "pain":
        duration_minutes = min(30, draft_1.duration_minutes)
        adjusted_workout = f"{duration_minutes}-minute Full-Body Stretching and Mobility Session"
        target_zone = 1
        rationale = (
            f"OFFLINE READJUSTMENT: Athlete reported muscular soreness/pain: '{user_feedback}'. "
            f"To facilitate recovery and prevent injury, the training is changed from running to a "
            f"mobility/stretching session, capped at Zone {target_zone}."
        )
    elif sentiment == "fatigue":
        duration_minutes = min(20, draft_1.duration_minutes)
        adjusted_workout = f"{duration_minutes}-minute Easy Active Recovery Walk"
        target_zone = 1
        rationale = (
            f"OFFLINE READJUSTMENT: Athlete reported subjective fatigue/under-recovery: '{user_feedback}'. "
            f"Autonomic and central nervous system strain require down-regulation to a very light "
            f"active recovery walk, capped at Zone {target_zone}."
        )
    else:
        # Generic adjustment scaling down from Draft 1
        target_zone = max(1, draft_1.target_zone - 1)
        duration_minutes = int(draft_1.duration_minutes * 0.8)
        adjusted_workout = rebuild_workout_name(draft_1.adjusted_workout, duration_minutes, "Reduced Intensity")
        rationale = (
            f"OFFLINE READJUSTMENT: Athlete requested modification: '{user_feedback}'. "
            f"Workout adjusted downwards. Heart rate capped at Zone {target_zone} and duration reduced "
            f"to {duration_minutes} minutes to align with subjective recovery state."
        )

    return WorkoutDraft(
        original_workout=original_workout,
        adjusted_workout=adjusted_workout,
        target_zone=target_zone,
        duration_minutes=duration_minutes,
        rationale=rationale
    )
