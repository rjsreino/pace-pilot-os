import os
import uuid
import logging
import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from core.models import WorkoutDraft

# Set up logging
logger = logging.getLogger("PacePilot.Execution")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# Define Google Calendar scopes
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

def execute_final_action(draft: WorkoutDraft) -> bool:
    """
    Executes final action for an approved WorkoutDraft:
    1. Generates local iCalendar (.ics) event and writes it to workspace root.
    2. Scaffolds authentication and service creation for Google Calendar API.
    """
    logger.info(f"Executing final actions for workout: '{draft.adjusted_workout}'")
    
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    
    # ==========================================
    # Action 1: Local iCalendar (.ics) Generation
    # ==========================================
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        dtstamp = now.strftime("%Y%m%dT%H%M%SZ")
        if draft.scheduled_start_iso:
            start_time = datetime.datetime.fromisoformat(draft.scheduled_start_iso)
        else:
            start_time = now
        start_utc = start_time.astimezone(datetime.timezone.utc)
        dtstart = start_utc.strftime("%Y%m%dT%H%M%SZ")
        end_utc = start_utc + datetime.timedelta(minutes=draft.duration_minutes)
        dtend = end_utc.strftime("%Y%m%dT%H%M%SZ")
        uid = f"pacepilot-{uuid.uuid4()}"
        
        # Clean rationale newlines for single-line string encoding in ICS description field
        clean_rationale = draft.rationale.replace("\r", "").replace("\n", " ")
        description_text = (
            f"Target Heart Rate Zone: Zone {draft.target_zone}\\n"
            f"Target Duration: {draft.duration_minutes} minutes\\n"
            f"Original Workout: {draft.original_workout}\\n"
            f"Physiological Focus: {getattr(draft, 'physiological_focus', 'Autonomic baseline assessment')}\\n\\n"
            f"Rationale: {clean_rationale}"
        )
        
        ics_lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//PacePilot//Running Coach//EN",
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{dtstamp}",
            f"DTSTART:{dtstart}",
            f"DTEND:{dtend}",
            f"SUMMARY:PacePilot: {draft.adjusted_workout}",
            f"DESCRIPTION:{description_text}",
            "STATUS:CONFIRMED",
            "END:VEVENT",
            "END:VCALENDAR"
        ]
        ics_content = "\r\n".join(ics_lines) + "\r\n"
        
        ics_path = os.path.join(root_dir, "pacepilot_workout.ics")
        with open(ics_path, "w", encoding="utf-8") as f:
            f.write(ics_content)
        logger.info(f"Successfully generated local iCalendar event: '{ics_path}'")
        
    except Exception as e:
        logger.error(f"Failed to generate local iCalendar event: {e}")
        return False

    # ==========================================
    # Action 2: Google Calendar Integration
    # ==========================================
    calendar_id = os.getenv("GOOGLE_CALENDAR_ID") or "primary"
    credentials_path = os.path.join(root_dir, "credentials.json")
    
    if not os.path.exists(credentials_path):
        logger.warning(
            "Google Cloud credentials.json not found. Safely relying on local "
            "iCalendar (.ics) generation engine for course demonstration."
        )
        return True

    try:
        logger.info("Initializing Google Calendar client...")
        creds = None
        token_path = os.path.join(root_dir, "token.json")
        
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
            
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES)
                creds = flow.run_local_server(port=0)
            with open(token_path, "w") as token:
                token.write(creds.to_json())
                
        service = build("calendar", "v3", credentials=creds)
        logger.info(f"Google Calendar service authenticated successfully for Calendar ID: {calendar_id}")
        
        # Calculate start and end times
        if draft.scheduled_start_iso:
            start_time = datetime.datetime.fromisoformat(draft.scheduled_start_iso)
        else:
            start_time = datetime.datetime.now(datetime.timezone.utc)
        start_utc = start_time.astimezone(datetime.timezone.utc)
        end_utc = start_utc + datetime.timedelta(minutes=draft.duration_minutes)
        
        # Format workout description
        description_text = (
            f"Target Heart Rate Zone: Zone {draft.target_zone}\n"
            f"Target Duration: {draft.duration_minutes} minutes\n"
            f"Original Workout: {draft.original_workout}\n"
            f"Physiological Focus: {getattr(draft, 'physiological_focus', 'Autonomic baseline assessment')}\n\n"
            f"Rationale: {draft.rationale}"
        )
        
        # Construct event body
        event_body = {
            "summary": f"PacePilot: {draft.adjusted_workout}",
            "description": description_text,
            "start": {
                "dateTime": start_utc.isoformat(),
                "timeZone": "UTC"
            },
            "end": {
                "dateTime": end_utc.isoformat(),
                "timeZone": "UTC"
            }
        }
        
        logger.info(f"Dispatching event payload to Google Calendar ID: {calendar_id}...")
        created_event = service.events().insert(calendarId=calendar_id, body=event_body).execute()
        
        logger.info(
            f"[SUCCESS] Workout event successfully injected into Google Calendar! "
            f"Link: {created_event.get('htmlLink')}"
        )
        
    except Exception as e:
        logger.error(f"Error during Google Calendar execution: {e}")
        return True
        
    return True

def sync_workout_to_calendar(draft: WorkoutDraft) -> bool:
    """Wrapper function to maintain backward compatibility."""
    return execute_final_action(draft)
