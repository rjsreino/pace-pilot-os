import logging
from core.ingestion import EnvironmentState

# Set up logging
logger = logging.getLogger("PacePilot.Engine")

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
