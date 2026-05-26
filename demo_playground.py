import os
import sys
import json
import datetime
from pydantic import ValidationError

# Add root folder to path to enable package imports
root_path = os.path.dirname(os.path.abspath(__file__))
if root_path not in sys.path:
    sys.path.append(root_path)

from core.ingestion import EnvironmentState, BiometricData, WeatherData
from core.engine import generate_workout_draft, WorkoutDraft

def save_state_to_file(state: EnvironmentState):
    """Writes the given environment state to state.json in the workspace root."""
    state_file = os.path.join(root_path, "state.json")
    try:
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(state.model_dump(), f, indent=2, ensure_ascii=False)
        print(f"[+] Successfully staged EnvironmentState to state.json")
    except Exception as e:
        print(f"[-] Error writing state.json: {e}", file=sys.stderr)

def prompt_manual_override() -> EnvironmentState:
    """Interactively prompts the user to input custom health and weather stats."""
    print("\n" + "-" * 50)
    print("          MANUAL SCENARIO PARAMETERS OVERRIDE")
    print("-" * 50)

    # 1. Sleep Score
    while True:
        try:
            sleep_input = input("Enter Sleep Score (0-100) [Default 75]: ").strip()
            sleep = int(sleep_input or "75")
            if not (0 <= sleep <= 100):
                print("[-] Sleep score must be between 0 and 100.")
                continue
            break
        except ValueError:
            print("[-] Please enter a valid integer.")

    # 2. HRV Status
    while True:
        hrv_input = input("Enter HRV Status (BALANCED, LOW, UNBALANCED) [Default BALANCED]: ").strip().upper()
        hrv = hrv_input or "BALANCED"
        if hrv not in ["BALANCED", "LOW", "UNBALANCED"]:
            print("[-] Invalid status. Pick from BALANCED, LOW, or UNBALANCED.")
            continue
        break

    # 3. Acute Training Load
    while True:
        try:
            load_input = input("Enter Acute Training Load (float/None) [Default 400.0]: ").strip()
            load = float(load_input or "400.0")
            break
        except ValueError:
            print("[-] Please enter a valid float number.")

    # 4. Temperature
    while True:
        try:
            temp_input = input("Enter Temperature in °C (e.g., 28.5) [Default 20.0]: ").strip()
            temp = float(temp_input or "20.0")
            break
        except ValueError:
            print("[-] Please enter a valid float number.")

    # 5. Humidity
    while True:
        try:
            humidity_input = input("Enter Humidity % (0-100) [Default 60]: ").strip()
            humidity = int(humidity_input or "60")
            if not (0 <= humidity <= 100):
                print("[-] Humidity must be between 0 and 100.")
                continue
            break
        except ValueError:
            print("[-] Please enter a valid integer.")

    # 6. Summary
    summary = input("Enter Weather Summary [Default 'Clear']: ").strip() or "Clear"

    # Build Pydantic models
    bio = BiometricData(
        sleep_score=sleep,
        hrv_status=hrv,
        acute_training_load=load
    )
    weather = WeatherData(
        temperature_c=temp,
        humidity=humidity,
        summary=summary
    )

    return EnvironmentState(
        biometric=bio,
        weather=weather,
        iso_timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
    )

def print_decision_brief(state: EnvironmentState, draft: WorkoutDraft):
    """Renders a clean, formatted decision output of the Observe -> Think -> Act loop."""
    print("\n" + "#" * 70)
    print("                 PACEPILOT AGENT DECISION BRIEF")
    print("#" * 70)

    # 1. OBSERVE SECTION
    print("\n[PHASE 1: OBSERVE - COLLECTED ATMOSPHERIC & PHYSIOLOGICAL SNAPSHOT]")
    print(f"  - Ingestion Time:         {state.iso_timestamp}")
    print(f"  - Sleep Score:            {state.biometric.sleep_score}/100")
    print(f"  - HRV Readiness:          {state.biometric.hrv_status}")
    print(f"  - Acute Training Load:    {state.biometric.acute_training_load}")
    print(f"  - Local Temperature:      {state.weather.temperature_c} °C")
    print(f"  - Relative Humidity:      {state.weather.humidity} %")
    print(f"  - Weather Conditions:     {state.weather.summary}")

    # 2. THINK & ACT SECTION
    print("\n[PHASE 2: THINK & ACT - RUNNING SCHEDULE MODIFICATION]")
    print(f"  - Original Planned Workout: {draft.original_workout}")
    print(f"  - Adjusted Target Workout:  {draft.adjusted_workout}")
    print(f"  - Target Intensity Zone:    Zone {draft.target_zone}")
    print(f"  - Target Training Duration: {draft.duration_minutes} minutes")
    print("\n  - Decision Rationale:")
    
    # Wrap rationale description beautifully for terminal display
    words = draft.rationale.split()
    lines = []
    current_line = []
    for word in words:
        current_line.append(word)
        if len(" ".join(current_line)) > 60:
            lines.append(" ".join(current_line))
            current_line = []
    if current_line:
        lines.append(" ".join(current_line))

    for line in lines:
        print(f"    {line}")

    print("\n" + "#" * 70 + "\n")

def run_playground():
    """Main CLI control loop."""
    while True:
        print("\n" + "=" * 60)
        print("               PACEPILOT DEVELOPMENT PLAYGROUND")
        print("=" * 60)
        print("Select a testing scenario to stage in state.json:")
        print("  [1] Scenario A: Perfect Performance Window (Optimal bio + Cool weather)")
        print("  [2] Scenario B: Acute Biological Fatigue (Low sleep + Low HRV)")
        print("  [3] Scenario C: Summer Heat Stress (High temperature > 32°C)")
        print("  [4] Scenario D: Compound Hazard Lockout (Low sleep + High temperature)")
        print("  [5] Scenario E: Manual Real-Time Overrides (Input your own values)")
        print("  [6] Exit Playground")
        print("=" * 60)

        choice = input("Enter choice (1-6): ").strip()

        if choice == "6":
            print("\nExiting playground. Run safely!")
            break

        state = None

        if choice == "1":
            # Scenario A: Perfect
            state = EnvironmentState(
                biometric=BiometricData(sleep_score=90, hrv_status="BALANCED", acute_training_load=380.0),
                weather=WeatherData(temperature_c=16.5, humidity=50, summary="Clear sky"),
                iso_timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
            )
        elif choice == "2":
            # Scenario B: Biological Fatigue
            state = EnvironmentState(
                biometric=BiometricData(sleep_score=54, hrv_status="LOW", acute_training_load=490.0),
                weather=WeatherData(temperature_c=19.0, humidity=62, summary="Partly cloudy"),
                iso_timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
            )
        elif choice == "3":
            # Scenario C: Summer Heat
            state = EnvironmentState(
                biometric=BiometricData(sleep_score=82, hrv_status="BALANCED", acute_training_load=410.0),
                weather=WeatherData(temperature_c=33.5, humidity=75, summary="Sunny and Humid"),
                iso_timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
            )
        elif choice == "4":
            # Scenario D: Compound Hazard
            state = EnvironmentState(
                biometric=BiometricData(sleep_score=50, hrv_status="UNBALANCED", acute_training_load=520.0),
                weather=WeatherData(temperature_c=32.0, humidity=80, summary="Hot and Humid"),
                iso_timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat()
            )
        elif choice == "5":
            state = prompt_manual_override()
        else:
            print("[-] Invalid choice. Please pick between 1 and 6.")
            continue

        if state:
            # Stage the state in state.json
            save_state_to_file(state)

            # Prompt for baseline workout
            workout_input = input("\nEnter baseline target workout [Default: '60-minute Threshold Tempo Run']: ").strip()
            baseline_workout = workout_input or "60-minute Threshold Tempo Run"

            # Execute Reasoning Engine
            print(f"\nDispatched reasoning engine for target workout: '{baseline_workout}'...")
            draft = generate_workout_draft(baseline_workout, state)

            # Print Decision Brief
            print_decision_brief(state, draft)

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    try:
        run_playground()
    except KeyboardInterrupt:
        print("\nPlayground aborted. Bye!")
