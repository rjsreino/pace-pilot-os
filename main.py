import os
import sys
import json
import logging
from dotenv import load_dotenv

# Ensure root directory is in python module search path
root_dir = os.path.abspath(os.path.dirname(__file__))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from core.ingestion import fetch_daily_context, EnvironmentState
from core.engine import generate_workout_draft
from core.validation import prompt_user_validation
from core.execution import execute_final_action

# Set up logging
logger = logging.getLogger("PacePilot.Main")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

def main():
    print("=" * 65)
    print("PacePilot - Agentic Running Coach Initialization")
    print("=" * 65)
    
    # Load environment variables from .env
    dotenv_path = os.path.join(root_dir, '.env')
    if os.path.exists(dotenv_path):
        load_dotenv(dotenv_path)
        print("[INFO] Loaded configuration from .env")
    else:
        print("[WARNING] .env file not found. Using system environment variables.")
        print("[TIP] You can copy .env.example to .env and fill in your credentials.")

    # Expected variables
    expected_vars = [
        "GARMIN_EMAIL",
        "GARMIN_PASSWORD",
        "GOOGLE_CALENDAR_ID"
    ]
    
    status_ready = True
    print("\nEnvironment Status Check:")
    for var in expected_vars:
        value = os.getenv(var)
        if value:
            # Mask sensitive values
            masked_value = value[:3] + "*" * (len(value) - 3) if len(value) > 3 else "***"
            print(f"  - {var}: LOADED ({masked_value})")
        else:
            print(f"  - {var}: MISSING")
            status_ready = False
            
    if not status_ready:
        print("\n[NOTE] Some credentials are missing. The application will use local offline fallbacks.")
        
    print("\n" + "=" * 65)
    print("                 STARTING PACEPILOT PIPELINE")
    print("=" * 65)

    # ----------------------------------------------------
    # Phase 1: Context Ingestion
    # ----------------------------------------------------
    logger.info("Executing Phase 1: Context Ingestion...")
    lat_val = os.getenv("LATITUDE")
    lon_val = os.getenv("LONGITUDE")
    lat = float(lat_val) if lat_val else 37.5665
    lon = float(lon_val) if lon_val else 126.978
    
    # Ingest biometric/weather data and generate state.json
    fetch_daily_context(lat, lon)
    state_file_path = os.path.join(root_dir, "state.json")

    # ----------------------------------------------------
    # Phase 2: Read state.json & Generate Initial Proposal
    # ----------------------------------------------------
    logger.info("Executing Phase 2: Generating Initial Recommendation...")
    if not os.path.exists(state_file_path):
        logger.error(f"Aborting: state.json was not found at {state_file_path}")
        return

    try:
        with open(state_file_path, "r", encoding="utf-8") as f:
            state_data = json.load(f)
        state = EnvironmentState.model_validate(state_data)
    except Exception as e:
        logger.error(f"Aborting: Failed to read or parse state.json: {e}")
        return

    # Prompt the user for their baseline target workout for the day
    default_workout = "60-minute Threshold Tempo Run"
    try:
        user_input = input(f"\nEnter baseline workout target for today [Default: '{default_workout}']: ").strip()
    except (KeyboardInterrupt, EOFError):
        print("\n[-] Initialization interrupted. Exiting.")
        return

    original_workout = user_input if user_input else default_workout
    initial_draft = generate_workout_draft(original_workout, state)

    # ----------------------------------------------------
    # Phase 3: Interactive Validation Gatekeeper
    # ----------------------------------------------------
    logger.info("Executing Phase 3: Interactive Validation Gatekeeper...")
    final_draft = prompt_user_validation(state_file_path, initial_draft)

    # ----------------------------------------------------
    # Phase 4: Final Action Execution Synchronization
    # ----------------------------------------------------
    if final_draft:
        logger.info("Executing Phase 4: Synchronizing workout action...")
        success = execute_final_action(final_draft)
        if success:
            logger.info("PacePilot pipeline executed successfully.")
        else:
            logger.error("PacePilot pipeline failed during execution phase.")
    else:
        logger.info("PacePilot validation gatekeeper returned None. Clean shutdown complete.")

    print("=" * 65)

if __name__ == "__main__":
    main()
