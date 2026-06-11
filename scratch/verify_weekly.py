import sys
import os
import json
import datetime

# Add parent directory to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv
load_dotenv()

from core.models import UserSettings
from core.ingestion import EnvironmentState, BiometricData, WeatherData
from core.engine import generate_weekly_schedule_draft, regenerate_weekly_schedule_with_feedback

def main():
    print("=== Running Weekly Schedule Integration Verification ===")
    
    # Define settings & mock context state
    settings = UserSettings(distance_goal="HALF", target_weekly_mileage=40.0)
    
    state = EnvironmentState(
        biometric=BiometricData(sleep_score=85, hrv_status="BALANCED", acute_training_load=350.0),
        weather=WeatherData(temperature_c=18.0, humidity=55, summary="Partly Cloudy"),
        iso_timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    
    # Save a temporary state.json file for the feedback loop
    state_file = "state.json"
    with open(state_file, "w", encoding="utf-8") as f:
        f.write(state.model_dump_json(indent=2))
    
    print("\n1. Generating Initial Draft (Draft 1)...")
    try:
        draft_1 = generate_weekly_schedule_draft(settings, state)
        print(f"Success! Generated {len(draft_1.schedule)} workouts.")
        for idx, workout in enumerate(draft_1.schedule):
            print(f"  [{idx}] Slot: {workout.session_slot}")
            print(f"      Original: {workout.original_workout}")
            print(f"      Adjusted: {workout.adjusted_workout}")
            print(f"      Zone: {workout.target_zone} | Duration: {workout.duration_minutes} mins")
            print(f"      Physiological Focus: {workout.physiological_focus}")
            print(f"      Rationale: {workout.rationale}")
    except Exception as e:
        print(f"Failed to generate initial draft: {e}")
        sys.exit(1)
        
    print("\n2. Generating Feedback-Adjusted Draft (Draft 2)...")
    feedback = "My knees are a little stiff and I am feeling tired from work."
    try:
        draft_2 = regenerate_weekly_schedule_with_feedback(state_file, settings, feedback, draft_1)
        print(f"Success! Generated feedback-adjusted schedule with {len(draft_2.schedule)} workouts.")
        for idx, workout in enumerate(draft_2.schedule):
            print(f"  [{idx}] Slot: {workout.session_slot}")
            print(f"      Original: {workout.original_workout}")
            print(f"      Adjusted: {workout.adjusted_workout}")
            print(f"      Zone: {workout.target_zone} | Duration: {workout.duration_minutes} mins")
            print(f"      Physiological Focus: {workout.physiological_focus}")
            print(f"      Rationale: {workout.rationale}")
    except Exception as e:
        print(f"Failed to generate feedback-adjusted draft: {e}")
        sys.exit(1)

    print("\nVerification passed successfully!")

if __name__ == "__main__":
    main()
