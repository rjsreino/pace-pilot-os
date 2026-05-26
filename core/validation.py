import logging
from core.engine import WorkoutDraft

# Set up logging
logger = logging.getLogger("PacePilot.Validation")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")


# ==========================================
# 1. Core Function: Validation Gatekeeper
# ==========================================

def prompt_user_validation(draft: WorkoutDraft) -> bool:
    """
    Presents an interactive terminal-based confirmation card.
    Halts the scheduling pipeline for user safety validation before triggering external API mutations.
    """
    # 2. Clear Visual Layout (Console UI)
    print("\n" + "=" * 65)
    print("             PACEPILOT SCHEDULE VALIDATION GATEKEEPER")
    print("=" * 65)
    print(f"  [PROPOSAL]  {draft.adjusted_workout}")
    print(f"  [INTENSITY] Zone {draft.target_zone}")
    print(f"  [DURATION]  {draft.duration_minutes} minutes")
    print(f"  [ORIGINAL]   {draft.original_workout}")
    print("\n  [RATIONALE]:")
    
    # Wrap rationale string nicely for console card presentation
    words = draft.rationale.split()
    lines = []
    current_line = []
    for word in words:
        current_line.append(word)
        if len(" ".join(current_line)) > 55:
            lines.append(" ".join(current_line))
            current_line = []
    if current_line:
        lines.append(" ".join(current_line))
        
    for line in lines:
        print(f"    {line}")
    print("=" * 65)

    # 3. Interactive Decision Capture
    while True:
        try:
            choice = input("Do you authorize scheduling this adjustment? [Y/N]: ").strip().upper()
            if choice in ["Y", "YES"]:
                logger.info("Scheduling adjustment authorized by user.")
                return True
            elif choice in ["N", "NO"]:
                logger.warning("Scheduling adjustment rejected by user.")
                return False
            else:
                print("[-] Invalid input. Please enter 'Y' or 'N' (or 'Yes' / 'No').")
        except (KeyboardInterrupt, EOFError):
            print("\n[-] Validation interrupted. Cancelling by default.")
            logger.warning("User validation input interrupted. Defaulting to rejection.")
            return False


# ==========================================
# 4. Baseline Main Check Block
# ==========================================

if __name__ == "__main__":
    print("=" * 65)
    print("PacePilot - Phase 3 Validation Gatekeeper Unit Test")
    print("=" * 65)
    
    # Mock target draft for testing
    mock_draft = WorkoutDraft(
        original_workout="60-minute Threshold Tempo Run",
        adjusted_workout="30-minute Active Recovery Walk",
        target_zone=1,
        duration_minutes=30,
        rationale=(
            "Combined physiological under-recovery markers (HRV: UNBALANCED, Sleep Score: 50/100) "
            "and elevated local temperature (32.0°C) exceed baseline safety parameters. Performing "
            "intense training under these conditions risks heat stress and delays muscle adaptation."
        )
    )

    # Trigger interactive check
    is_approved = prompt_user_validation(mock_draft)
    print(f"\nResulting approval decision: {is_approved}")
    print("=" * 65)
