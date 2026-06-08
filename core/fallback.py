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
            f"Compounding safety lockout active due to critical recovery (HRV: {hrv}, Sleep: {sleep}/100) "
            f"and high heat ({temp}°C). High-intensity training today presents acute dehydration and overreaching risks. "
            f"Adjusted to a low-intensity active recovery walk."
        )
        return WorkoutDraft(
            original_workout=original_workout,
            adjusted_workout=adjusted_workout,
            target_zone=1,
            duration_minutes=30,
            rationale=rationale,
            physiological_focus="Cardiovascular strain & acute thermal stress protection"
        )
        
    elif heuristics["bio_warning"]:
        adjusted_zone = heuristics["recommended_zone"]
        adjusted_duration = heuristics["recommended_duration"]
        adjusted_workout = f"Recovery Run (Cap Zone {adjusted_zone})"
        rationale = (
            f"Biometric downgrade triggered by under-recovery markers (Sleep: {sleep}/100, HRV: {hrv}). "
            f"High heart-rate training under parasympathetic depression delays adaptation and risks injury. "
            f"Target zone is restricted to Zone {adjusted_zone} and duration reduced to {adjusted_duration} minutes."
        )
        return WorkoutDraft(
            original_workout=original_workout,
            adjusted_workout=adjusted_workout,
            target_zone=adjusted_zone,
            duration_minutes=adjusted_duration,
            rationale=rationale,
            physiological_focus="Parasympathetic depression & injury prevention safety cap"
        )
        
    elif heuristics["temp_warning"]:
        adjusted_duration = heuristics["recommended_duration"]
        adjusted_workout = f"Heat-adjusted {original_workout}"
        rationale = (
            f"Thermal stress duration cap triggered by local temperature ({temp}°C). "
            f"Extended efforts in elevated temperatures elevate blood viscosity and trigger cardiac drift. "
            f"Duration is scaled back by 20% to {adjusted_duration} minutes to manage heat strain."
        )
        return WorkoutDraft(
            original_workout=original_workout,
            adjusted_workout=adjusted_workout,
            target_zone=original_zone,
            duration_minutes=adjusted_duration,
            rationale=rationale,
            physiological_focus="Thermal cardiac drift & blood viscosity management"
        )
        
    else:
        rationale = (
            f"Physiological parameters (Sleep: {sleep}/100, HRV: {hrv}) and climate conditions ({temp}°C) are optimal. "
            f"No safety warning is active. Proceeding with the original training protocol."
        )
        return WorkoutDraft(
            original_workout=original_workout,
            adjusted_workout=original_workout,
            target_zone=original_zone,
            duration_minutes=original_duration,
            rationale=rationale,
            physiological_focus="Aerobic base development & autonomic stability validation"
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
                f"Athlete reported feeling strong and ready: '{user_feedback}'. "
                f"Biometrics and climate are optimal, allowing completion of the full planned training protocol."
            )
        elif heuristics["compounding_warning"]:
            adjusted_workout = "30-minute Active Recovery Walk"
            rationale = (
                f"Athlete reported feeling strong but compounding safety lockout is active (Sleep: {sleep}/100, HRV: {hrv}, Temp: {temp}°C). "
                f"To prevent cardiovascular and autonomic overload, training is restricted to a Zone {target_zone} recovery walk for {duration_minutes} minutes."
            )
        elif heuristics["bio_warning"]:
            adjusted_workout = rebuild_workout_name(original_workout, duration_minutes, "Biometrically-Capped")
            rationale = (
                f"Athlete reported feeling strong but under-recovery markers (Sleep: {sleep}/100, HRV: {hrv}) cap training. "
                f"Target intensity is limited to Zone {target_zone} and duration to {duration_minutes} minutes to prevent autonomic overreaching."
            )
        else:
            adjusted_workout = rebuild_workout_name(original_workout, duration_minutes, "Heat-adjusted")
            rationale = (
                f"Athlete reported feeling strong but ambient heat ({temp}°C) requires keeping a duration cap of {duration_minutes} minutes. "
                f"Target intensity is permitted up to Zone {target_zone}."
            )
    elif sentiment == "pain":
        duration_minutes = min(30, draft_1.duration_minutes)
        adjusted_workout = f"{duration_minutes}-minute Full-Body Stretching and Mobility Session"
        target_zone = 1
        rationale = (
            f"Athlete reported soreness/pain: '{user_feedback}'. "
            f"To facilitate recovery and prevent injury, the session is changed to a mobility/stretching session capped at Zone {target_zone}."
        )
    elif sentiment == "fatigue":
        duration_minutes = min(20, draft_1.duration_minutes)
        adjusted_workout = f"{duration_minutes}-minute Easy Active Recovery Walk"
        target_zone = 1
        rationale = (
            f"Athlete reported subjective fatigue: '{user_feedback}'. "
            f"Autonomic and central nervous system strain require down-regulation to a Zone {target_zone} active recovery walk."
        )
    else:
        # Generic adjustment scaling down from Draft 1
        target_zone = max(1, draft_1.target_zone - 1)
        duration_minutes = int(draft_1.duration_minutes * 0.8)
        adjusted_workout = rebuild_workout_name(draft_1.adjusted_workout, duration_minutes, "Reduced Intensity")
        rationale = (
            f"Athlete requested modification: '{user_feedback}'. "
            f"Heart rate is capped at Zone {target_zone} and duration reduced to {duration_minutes} minutes to align with subjective recovery state."
        )

    # Map physiological focus based on state
    if sentiment == "pain" or heuristics["bio_warning"]:
        phys_focus = "Parasympathetic depression & injury prevention safety cap"
    elif heuristics["compounding_warning"]:
        phys_focus = "Cardiovascular strain & acute thermal stress protection"
    elif heuristics["temp_warning"]:
        phys_focus = "Thermal cardiac drift & blood viscosity management"
    else:
        phys_focus = "Aerobic base development & autonomic stability validation"

    return WorkoutDraft(
        original_workout=original_workout,
        adjusted_workout=adjusted_workout,
        target_zone=target_zone,
        duration_minutes=duration_minutes,
        rationale=rationale,
        physiological_focus=phys_focus
    )
