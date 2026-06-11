import logging
from core.models import WorkoutDraft, UserSettings, WeeklyScheduleDraft
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
    heuristics: dict,
    session_slot: str = ""
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
            physiological_focus="Cardiovascular strain & acute thermal stress protection",
            session_slot=session_slot
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
            physiological_focus="Parasympathetic depression & injury prevention safety cap",
            session_slot=session_slot
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
            physiological_focus="Thermal cardiac drift & blood viscosity management",
            session_slot=session_slot
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
            physiological_focus="Aerobic base development & autonomic stability validation",
            session_slot=session_slot
        )


def generate_fallback_with_feedback(
    original_workout: str,
    original_zone: int,
    original_duration: int,
    state: EnvironmentState,
    heuristics: dict,
    user_feedback: str,
    draft_1: WorkoutDraft,
    session_slot: str = ""
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
        physiological_focus=phys_focus,
        session_slot=session_slot or draft_1.session_slot
    )


def get_weekly_mileage_proportions(num_runs: int) -> list[float]:
    """
    Returns the list of mileage proportions for each session slot based on weekly frequency.
    """
    if num_runs == 3:
        return [0.20, 0.35, 0.45]
    elif num_runs == 4:
        return [0.20, 0.35, 0.20, 0.45]
    elif num_runs == 5:
        return [0.20, 0.20, 0.25, 0.15, 0.25]
    elif num_runs == 6:
        return [0.15, 0.20, 0.15, 0.15, 0.15, 0.20]
    else:
        return [0.12, 0.13, 0.10, 0.15, 0.12, 0.13, 0.25]


def determine_weekly_frequency_and_slots(mileage: float) -> tuple[int, list[str]]:
    """
    Enforces frequency map thresholds based on weekly mileage.
    Returns (frequency, slots).
    """
    if mileage < 45.0:
        return 3, ["Day 1: Speed", "Day 3: Easy", "Day 6: Long"]
    elif mileage < 65.0:
        return 4, ["Day 1: Speed", "Day 3: Easy", "Day 4: Recovery", "Day 6: Long"]
    elif mileage < 85.0:
        return 5, ["Day 1: Speed", "Day 2: Easy", "Day 4: Mid-Week Long", "Day 5: Recovery", "Day 7: Long"]
    elif mileage < 110.0:
        return 6, ["Day 1: Interval", "Day 2: Easy", "Day 3: Tempo", "Day 5: Recovery", "Day 6: Easy", "Day 7: Long"]
    else:
        return 7, ["Day 1: Intervals", "Day 3: Easy", "Day 4 (AM): Recovery Flush", "Day 4 (PM): Tempo", "Day 5: Easy", "Day 6: Recovery", "Day 7: Macro Long Run"]


def get_slot_parameters(goal: str, slot: str) -> tuple[float, int, str]:
    """
    Returns (proportional_percentage, target_zone, base_workout_name) for a slot.
    """
    # 3-session slots
    if slot == "Day 1: Speed":
        return 0.20, (5 if goal in ["5K", "10K"] else 3), ("VO2 Max Intervals" if goal in ["5K", "10K"] else "Threshold Tempo Run")
    elif slot == "Day 3: Easy":
        return 0.35, 2, "Easy Recovery Run"
    elif slot == "Day 6: Long":
        return 0.45, (3 if goal in ["5K", "10K"] else 2), ("Fartlek Run" if goal in ["5K", "10K"] else "Aerobic Base Run")
        
    # 4-session slots
    elif slot == "Day 4: Recovery":
        return 0.20, 1, "Active Recovery Walk"
        
    # 5-session slots
    elif slot == "Day 2: Easy":
        return 0.20, 2, "Easy Base Run"
    elif slot == "Day 4: Mid-Week Long":
        return 0.25, 2, "Moderate Aerobic Run"
    elif slot == "Day 5: Recovery":
        return 0.15, 1, "Active Recovery Walk"
    elif slot == "Day 7: Long":
        return 0.25, (3 if goal in ["5K", "10K"] else 2), ("Fartlek Run" if goal in ["5K", "10K"] else "Aerobic Base Run")
        
    # 6-session slots
    elif slot == "Day 1: Interval":
        return 0.15, 5, "High Intensity Intervals"
    elif slot == "Day 3: Tempo":
        return 0.15, 3, "Steady State Tempo"
    elif slot == "Day 6: Easy":
        return 0.15, 2, "Aerobic Base Run"
        
    # 7-session slots
    elif slot == "Day 1: Intervals":
        return 0.12, 5, "VO2 Max Intervals"
    elif slot == "Day 3: Easy":
        return 0.13, 2, "Aerobic Base Run"
    elif slot == "Day 4 (AM): Recovery Flush":
        return 0.10, 1, "Active Recovery Walk"
    elif slot == "Day 4 (PM): Tempo":
        return 0.15, 3, "Lactate Threshold Tempo"
    elif slot == "Day 5: Easy":
        return 0.12, 2, "Easy Base Run"
    elif slot == "Day 6: Recovery":
        return 0.13, 1, "Active Recovery Run"
    return 0.20, 2, "Aerobic Run"


def generate_fallback_weekly_schedule(
    settings: UserSettings,
    state: EnvironmentState,
    heuristics: dict
) -> WeeklyScheduleDraft:
    """
    Generates a deterministic WeeklyScheduleDraft based on UserSettings and EnvironmentState.
    """
    goal = settings.distance_goal
    mileage = settings.target_weekly_mileage
    
    # Pace translation
    pace_multiplier = 6.0 if goal in ["5K", "10K"] else 6.5
    total_duration = mileage * pace_multiplier
    
    # Determine slots dynamically
    freq, slots = determine_weekly_frequency_and_slots(mileage)
    
    schedule = []
    temp = state.weather.temperature_c
    sleep = state.biometric.sleep_score
    hrv = state.biometric.hrv_status
    
    for day_key in slots:
        pct, orig_zone, base_name = get_slot_parameters(goal, day_key)
        orig_duration = int(round(total_duration * pct))
        original_workout = f"{orig_duration}-minute {base_name}"
        
        if heuristics["compounding_warning"]:
            adjusted_workout = "30-minute Active Recovery Walk"
            adjusted_duration = 30
            adjusted_zone = 1
            rationale = (
                f"Compounding safety lockout active due to critical recovery (HRV: {hrv}, Sleep: {sleep}/100) "
                f"and high heat ({temp}°C). High-intensity training today presents acute dehydration and overreaching risks. "
                f"Entire weekly block down-regulated to active recovery walks."
            )
            phys_focus = "Cardiovascular strain & acute thermal stress protection"
        elif heuristics["bio_warning"]:
            # cap to Zone 2 or Zone 1 (if speed/intervals/tempo)
            if any(term in day_key for term in ["Speed", "Interval", "Tempo"]):
                adjusted_zone = 1
                adjusted_workout = "Active Recovery Walk (Cap Zone 1)"
            else:
                adjusted_zone = 2
                adjusted_workout = "Recovery Run (Cap Zone 2)"
            
            adjusted_duration = int(round(orig_duration * 0.6))
            rationale = (
                f"Biometric downgrade triggered by under-recovery markers (Sleep: {sleep}/100, HRV: {hrv}). "
                f"High heart-rate training under parasympathetic depression delays adaptation and risks injury. "
                f"Target zone capped at Zone {adjusted_zone} and duration reduced to {adjusted_duration} minutes."
            )
            phys_focus = "Parasympathetic depression & injury prevention safety cap"
        elif heuristics["temp_warning"]:
            adjusted_duration = int(round(orig_duration * 0.8))
            adjusted_zone = orig_zone
            adjusted_workout = f"Heat-adjusted {orig_duration}-minute {base_name}"
            rationale = (
                f"Thermal stress duration cap triggered by local temperature ({temp}°C). "
                f"Extended efforts in elevated temperatures elevate blood viscosity and trigger cardiac drift. "
                f"Duration is scaled back by 20% to {adjusted_duration} minutes to manage heat strain."
            )
            phys_focus = "Thermal cardiac drift & blood viscosity management"
        else:
            adjusted_duration = orig_duration
            adjusted_zone = orig_zone
            adjusted_workout = original_workout
            rationale = (
                f"Physiological parameters (Sleep: {sleep}/100, HRV: {hrv}) and climate conditions ({temp}°C) are optimal. "
                f"No safety warning is active. Proceeding with weekly training protocol."
            )
            phys_focus = "Aerobic base development & autonomic stability validation"
            
        schedule.append(WorkoutDraft(
            original_workout=original_workout,
            adjusted_workout=adjusted_workout,
            target_zone=adjusted_zone,
            duration_minutes=adjusted_duration,
            rationale=rationale,
            physiological_focus=phys_focus,
            session_slot=day_key
        ))
        
    return WeeklyScheduleDraft(schedule=schedule)


def generate_fallback_weekly_schedule_with_feedback(
    settings: UserSettings,
    state: EnvironmentState,
    heuristics: dict,
    user_feedback: str,
    draft_1: WeeklyScheduleDraft
) -> WeeklyScheduleDraft:
    """
    Offline feedback adaptation for weekly schedule.
    """
    sentiment = detect_sentiment(user_feedback)
    temp = state.weather.temperature_c
    sleep = state.biometric.sleep_score
    hrv = state.biometric.hrv_status
    
    # Calculate target (optimal) bounds for reference
    goal = settings.distance_goal
    mileage = settings.target_weekly_mileage
    pace_multiplier = 6.0 if goal in ["5K", "10K"] else 6.5
    total_duration = mileage * pace_multiplier
    
    # Determine slots dynamically
    freq, slots = determine_weekly_frequency_and_slots(mileage)
    
    schedule = []
    
    for day_key in slots:
        pct, orig_zone, base_name = get_slot_parameters(goal, day_key)
        orig_duration = int(round(total_duration * pct))
        original_workout = f"{orig_duration}-minute {base_name}"
        
        # Determine safety upper bounds for this day
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
        d1_workout = None
        for w in draft_1.schedule:
            if w.session_slot == day_key:
                d1_workout = w
                break
        
        if d1_workout is None:
            # Stage temporary workout
            d1_workout = WorkoutDraft(
                original_workout=original_workout,
                adjusted_workout=original_workout,
                target_zone=orig_zone,
                duration_minutes=orig_duration,
                rationale="Staged new session slot.",
                physiological_focus="Aerobic base development & autonomic stability validation",
                session_slot=day_key
            )
        
        if sentiment == "high_energy":
            target_zone = max_zone
            duration_minutes = max_duration
            adjusted_workout = d1_workout.adjusted_workout
            rationale = (
                f"Athlete reported feeling strong and ready: '{user_feedback}'. "
                f"Weekly training session scaled up to maximum allowed safety limits."
            )
            phys_focus = d1_workout.physiological_focus
        elif sentiment == "pain":
            duration_minutes = min(30, d1_workout.duration_minutes)
            adjusted_workout = f"{duration_minutes}-minute Full-Body Stretching and Mobility Session"
            target_zone = 1
            rationale = (
                f"Athlete reported soreness/pain: '{user_feedback}'. "
                f"To facilitate recovery and prevent injury, this weekly session is changed to a mobility/stretching session."
            )
            phys_focus = "Parasympathetic depression & injury prevention safety cap"
        elif sentiment == "fatigue":
            duration_minutes = min(20, d1_workout.duration_minutes)
            adjusted_workout = f"{duration_minutes}-minute Easy Active Recovery Walk"
            target_zone = 1
            rationale = (
                f"Athlete reported subjective fatigue: '{user_feedback}'. "
                f"Autonomic and central nervous system strain require down-regulation to a Zone 1 active recovery walk."
            )
            phys_focus = "Parasympathetic depression & injury prevention safety cap"
        else:
            target_zone = max(1, d1_workout.target_zone - 1)
            duration_minutes = int(round(d1_workout.duration_minutes * 0.8))
            adjusted_workout = f"Reduced Intensity {d1_workout.adjusted_workout}"
            rationale = (
                f"Athlete requested modification: '{user_feedback}'. "
                f"Duration reduced and intensity capped to align with subjective recovery state."
            )
            phys_focus = d1_workout.physiological_focus
            
        target_zone = min(max_zone, target_zone)
        duration_minutes = min(max_duration, duration_minutes)
        
        schedule.append(WorkoutDraft(
            original_workout=original_workout,
            adjusted_workout=adjusted_workout,
            target_zone=target_zone,
            duration_minutes=duration_minutes,
            rationale=rationale,
            physiological_focus=phys_focus,
            session_slot=day_key
        ))
        
    return WeeklyScheduleDraft(schedule=schedule)


