import os
import sys
import logging
import json
import datetime
from core.engine import WorkoutDraft, regenerate_with_feedback, parse_workout_details

# Set up logging
logger = logging.getLogger("PacePilot.Validation")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


# ==========================================
# Helper Utilities
# ==========================================

def wrap_text(text: str, width: int = 55) -> list[str]:
    """Wraps text into lines of maximum width for terminal readability."""
    words = text.split()
    lines = []
    current_line = []
    for word in words:
        current_line.append(word)
        if len(" ".join(current_line)) > width:
            lines.append(" ".join(current_line))
            current_line = []
    if current_line:
        lines.append(" ".join(current_line))
    return lines


def print_workout_card(title: str, draft: WorkoutDraft):
    """Prints a clean ASCII training review card for a draft workout."""
    print(f"\n  [{title}]")
    print(f"    - Proposal:   {draft.adjusted_workout}")
    print(f"    - Intensity:  Zone {draft.target_zone}")
    print(f"    - Duration:   {draft.duration_minutes} minutes")
    print(f"    - Original:   {draft.original_workout}")
    print("    - Rationale:")
    wrapped = wrap_text(draft.rationale, 55)
    for line in wrapped:
        print(f"      {line}")


# ==========================================
# Core Function: The Gatekeeper State Machine
# ==========================================

def resolve_target_schedule_time() -> datetime.datetime:
    """
    Resolves the target scheduled start time for the workout based on the current local clock.
    If the current hour is >= 20 (8:00 PM), baseline options shift to tomorrow.
    """
    now = datetime.datetime.now().astimezone()
    
    if now.hour >= 20:
        print("\n[TEMPORAL CAP] It is past optimal training hours. Shifting baseline options to tomorrow.")
        
    print("\n" + "-" * 50)
    print("             SELECT WORKOUT WINDOW")
    print("-" * 50)
    print("  [1] Morning Window (Tomorrow at 7:00 AM) - Ideal for minimizing summer heat load")
    print("  [2] Evening Window (Tomorrow at 6:00 PM) - Ideal for post-class cooling windows")
    print("  [3] Custom Time Slot (Prompt user to input a simple date/hour offset)")
    print("-" * 50)
    
    while True:
        try:
            choice = input("Select option [1-3]: ").strip()
            if choice == "1":
                tomorrow = now + datetime.timedelta(days=1)
                return tomorrow.replace(hour=7, minute=0, second=0, microsecond=0)
            elif choice == "2":
                tomorrow = now + datetime.timedelta(days=1)
                return tomorrow.replace(hour=18, minute=0, second=0, microsecond=0)
            elif choice == "3":
                print("\nCustom Time Slot Picker:")
                while True:
                    try:
                        days_input = input("Enter days offset from today (0 for today, 1 for tomorrow, etc.) [Default: 1]: ").strip()
                        days = int(days_input) if days_input else 1
                        if days < 0:
                            print("[-] Days offset must be non-negative.")
                            continue
                        break
                    except ValueError:
                        print("[-] Please enter a valid integer.")
                
                while True:
                    try:
                        hour_input = input("Enter hour of the day (0-23) [Default: 9]: ").strip()
                        hour = int(hour_input) if hour_input else 9
                        if not (0 <= hour <= 23):
                            print("[-] Hour must be between 0 and 23.")
                            continue
                        break
                    except ValueError:
                        print("[-] Please enter a valid integer.")
                        
                target = now + datetime.timedelta(days=days)
                return target.replace(hour=hour, minute=0, second=0, microsecond=0)
            else:
                print("[-] Invalid choice. Please select 1, 2, or 3.")
        except (KeyboardInterrupt, EOFError):
            print("\n[-] Time selection interrupted. Defaulting to tomorrow morning at 7:00 AM.")
            tomorrow = now + datetime.timedelta(days=1)
            return tomorrow.replace(hour=7, minute=0, second=0, microsecond=0)


def prompt_user_validation(state_path: str, initial_draft: WorkoutDraft) -> WorkoutDraft | None:
    """
    Validation Gatekeeper State Machine.
    Allows interactive authorization, subjective feedback loop, and final reversion capabilities.
    """
    # Round 1: Presentation
    print("\n" + "=" * 65)
    print("             PACEPILOT SCHEDULE VALIDATION GATEKEEPER")
    print("=" * 65)
    print_workout_card("DRAFT 1: INITIAL RECOMMENDATION", initial_draft)
    print("=" * 65)

    while True:
        try:
            auth_choice = input("Do you authorize scheduling this adjustment? [Y/N]: ").strip().upper()
            if auth_choice in ["Y", "YES"]:
                logger.info("Initial Draft 1 authorized directly by user.")
                initial_draft.scheduled_start_iso = resolve_target_schedule_time().isoformat()
                return initial_draft
            elif auth_choice in ["N", "NO"]:
                logger.info("Draft 1 rejected. Opening sub-menu options...")
                break
            else:
                print("[-] Invalid choice. Please enter Y or N.")
        except (KeyboardInterrupt, EOFError):
            print("\n[-] Validation interrupted. Exiting gatekeeper.")
            return None

    # Rejection Sub-Menu Loop
    while True:
        print("\n" + "-" * 50)
        print("                REJECTION SUB-MENU")
        print("-" * 50)
        print("  [1] Force Original Protocol (Override safety guidance)")
        print("  [2] Absolute Rest Day (Force Z0, 0 minutes)")
        print("  [3] Readjust Plan (Provide subjective feedback on how you feel)")
        print("  [4] Cancel/Exit Validation")
        print("-" * 50)
        
        try:
            sub_choice = input("Select option [1-4]: ").strip()
            if sub_choice == "1":
                orig_zone, orig_duration = parse_workout_details(initial_draft.original_workout)
                forced_draft = WorkoutDraft(
                    original_workout=initial_draft.original_workout,
                    adjusted_workout=initial_draft.original_workout,
                    target_zone=orig_zone,
                    duration_minutes=orig_duration,
                    rationale="User bypassed agent safety warnings and forced the original unadjusted training protocol."
                )
                logger.warning("User forced original unadjusted training protocol.")
                forced_draft.scheduled_start_iso = resolve_target_schedule_time().isoformat()
                return forced_draft
                
            elif sub_choice == "2":
                rest_draft = WorkoutDraft(
                    original_workout=initial_draft.original_workout,
                    adjusted_workout="Rest Day",
                    target_zone=0,
                    duration_minutes=0,
                    rationale="User requested an absolute rest day, overriding all planned exercise."
                )
                logger.info("Absolute rest day forced by user.")
                rest_draft.scheduled_start_iso = resolve_target_schedule_time().isoformat()
                return rest_draft
                
            elif sub_choice == "3":
                feedback = input("\nHow do you feel? (e.g. 'legs sore', 'too tired'): ").strip()
                if not feedback:
                    feedback = "User requested manual adjustment without details."
                
                print("\nRegenerating plan incorporating subjective feedback...")
                draft_2 = regenerate_with_feedback(state_path, initial_draft.original_workout, feedback, initial_draft)
                break
                
            elif sub_choice == "4":
                logger.info("User cancelled validation loop.")
                return None
            else:
                print("[-] Invalid choice. Please pick between 1 and 4.")
        except (KeyboardInterrupt, EOFError):
            print("\n[-] Selection interrupted. Exiting gatekeeper.")
            return None

    # Round 2: The Final Pass & Choice Matrix
    print("\n" + "=" * 65)
    print("                 COMPARING PROPOSED WORKOUT DRAFTS")
    print("=" * 65)
    print_workout_card("DRAFT 1: ORIGINAL RECOMMENDATION", initial_draft)
    print_workout_card("DRAFT 2: FEEDBACK-ADJUSTED PLAN", draft_2)
    print("=" * 65)

    while True:
        print("\nFinal Decision Matrix:")
        print("  [1] Approve Draft 2 (Feedback-adjusted)")
        print("  [2] Revert to Draft 1 (Original recommendation)")
        print("  [3] Safety Override (Absolute Rest Day)")
        print("  [4] Cancel/Exit")
        
        try:
            final_choice = input("Select final action [1-4]: ").strip()
            if final_choice == "1":
                logger.info("User approved Draft 2 (feedback-adjusted).")
                draft_2.scheduled_start_iso = resolve_target_schedule_time().isoformat()
                return draft_2
            elif final_choice == "2":
                logger.info("User reverted to Draft 1 (original recommendation).")
                initial_draft.scheduled_start_iso = resolve_target_schedule_time().isoformat()
                return initial_draft
            elif final_choice == "3":
                rest_draft = WorkoutDraft(
                    original_workout=initial_draft.original_workout,
                    adjusted_workout="Rest Day",
                    target_zone=0,
                    duration_minutes=0,
                    rationale="User selected Safety Override to force an absolute rest day."
                )
                logger.info("User forced safety override rest day.")
                rest_draft.scheduled_start_iso = resolve_target_schedule_time().isoformat()
                return rest_draft
            elif final_choice == "4":
                logger.info("User cancelled validation in final matrix.")
                return None
            else:
                print("[-] Invalid choice. Please pick between 1 and 4.")
        except (KeyboardInterrupt, EOFError):
            print("\n[-] Validation interrupted. Exiting gatekeeper.")
            return None


# ==========================================
# Verification Execution
# ==========================================

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    print("=" * 65)
    print("PacePilot - Phase 3 Reversion-Cache State Machine Test")
    print("=" * 65)

    # Resolve local state path
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    state_file = os.path.join(root_dir, "state.json")

    # Backup original state.json if it exists to maintain workspace state
    backup_state = None
    if os.path.exists(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                backup_state = json.load(f)
        except Exception:
            pass

    # Stage a consistent test state matching the mock initial draft context (no heat warning)
    test_state = {
        "biometric": {
            "sleep_score": 54,
            "hrv_status": "LOW",
            "acute_training_load": 490.0
        },
        "weather": {
            "temperature_c": 20.0,
            "humidity": 65,
            "summary": "Clear and cool"
        },
        "iso_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat()
    }

    try:
        with open(state_file, "w", encoding="utf-8") as f:
            json.dump(test_state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[-] Warning: Failed to stage test state: {e}")

    mock_initial_draft = WorkoutDraft(
        original_workout="60-minute Threshold Tempo Run",
        adjusted_workout="36-minute Easy Recovery Run",
        target_zone=2,
        duration_minutes=36,
        rationale=(
            "Under-recovery detected (Sleep score: 54, HRV status: LOW). "
            "To prevent autonomic overload, duration is scaled back by 40% "
            "and intensity capped at Zone 2."
        )
    )

    try:
        final_draft = prompt_user_validation(state_file, mock_initial_draft)

        if final_draft:
            print("\n[VALIDATION COMPLETE] Output WorkoutDraft:")
            print(final_draft.model_dump_json(indent=2))
        else:
            print("\n[VALIDATION SKIPPED/CANCELLED]")
    finally:
        # Restore the original state.json backup if it exists
        if backup_state is not None:
            try:
                with open(state_file, "w", encoding="utf-8") as f:
                    json.dump(backup_state, f, indent=2, ensure_ascii=False)
            except Exception:
                pass
        else:
            # Clean up the staged test state if there was no original file
            if os.path.exists(state_file):
                try:
                    os.remove(state_file)
                except Exception:
                    pass

    print("=" * 65)
