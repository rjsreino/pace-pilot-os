import os
from dotenv import load_dotenv

def main():
    print("=" * 50)
    print("PacePilot - Agentic Running Coach Initialization")
    print("=" * 50)
    
    # Load environment variables from .env
    dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
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
            
    print("\n" + "=" * 50)
    if status_ready:
        print("STATUS: Environment is fully ready and configured!")
    else:
        print("STATUS: Basic setup is ready. Please configure missing variables in .env.")
    print("=" * 50)

if __name__ == "__main__":
    main()
