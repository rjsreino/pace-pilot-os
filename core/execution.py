import os
import uuid
import logging
import datetime
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from core.models import WorkoutDraft, WeeklyScheduleDraft
from core.parser import parse_day_offset

# Set up logging
logger = logging.getLogger("PacePilot.Execution")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# Define Google Calendar scopes
SCOPES = ["https://www.googleapis.com/auth/calendar.events"]

def execute_final_action(draft: WeeklyScheduleDraft | WorkoutDraft) -> bool:
    """
    Executes final action for an approved WeeklyScheduleDraft or WorkoutDraft:
    1. Generates local iCalendar (.ics) event(s) and writes to workspace root.
    2. Batch inserts events to Google Calendar.
    """
    if isinstance(draft, WorkoutDraft):
        if not draft.session_slot:
            draft.session_slot = "Workout"
        draft = WeeklyScheduleDraft(schedule=[draft])
        
    logger.info("Executing final actions for weekly schedule")
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    
    # ==========================================
    # Action 1: Local iCalendar (.ics) Generation
    # ==========================================
    try:
        now = datetime.datetime.now(datetime.timezone.utc)
        dtstamp = now.strftime("%Y%m%dT%H%M%SZ")
        
        ics_lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//PacePilot//Running Coach//EN"
        ]
        
        for workout in draft.schedule:
            day_key = workout.session_slot
            if workout.scheduled_start_iso:
                start_time = datetime.datetime.fromisoformat(workout.scheduled_start_iso)
            else:
                offset = parse_day_offset(day_key)
                start_time = now + datetime.timedelta(days=offset)
                if "(AM)" in day_key:
                    start_time = start_time.replace(hour=8, minute=0, second=0, microsecond=0)
                elif "(PM)" in day_key:
                    start_time = start_time.replace(hour=18, minute=0, second=0, microsecond=0)
                
            start_utc = start_time.astimezone(datetime.timezone.utc)
            dtstart = start_utc.strftime("%Y%m%dT%H%M%SZ")
            end_utc = start_utc + datetime.timedelta(minutes=workout.duration_minutes)
            dtend = end_utc.strftime("%Y%m%dT%H%M%SZ")
            uid = f"pacepilot-{uuid.uuid4()}"
            
            clean_rationale = workout.rationale.replace("\r", "").replace("\n", " ")
            description_text = (
                f"Target Heart Rate Zone: Zone {workout.target_zone}\\n"
                f"Target Duration: {workout.duration_minutes} minutes\\n"
                f"Original Workout: {workout.original_workout}\\n"
                f"Physiological Focus: {workout.physiological_focus}\\n\\n"
                f"Rationale: {clean_rationale}"
            )
            
            event_lines = [
                "BEGIN:VEVENT",
                f"UID:{uid}",
                f"DTSTAMP:{dtstamp}",
                f"DTSTART:{dtstart}",
                f"DTEND:{dtend}",
                f"SUMMARY:PacePilot: {workout.adjusted_workout}",
                f"DESCRIPTION:{description_text}",
                "STATUS:CONFIRMED",
                "END:VEVENT"
            ]
            ics_lines.extend(event_lines)
            
        ics_lines.append("END:VCALENDAR")
        ics_content = "\r\n".join(ics_lines) + "\r\n"
        
        ics_path = os.path.join(root_dir, "pacepilot_workout.ics")
        with open(ics_path, "w", encoding="utf-8") as f:
            f.write(ics_content)
        logger.info(f"Successfully generated local iCalendar schedule file: '{ics_path}'")
        
    except Exception as e:
        logger.error(f"Failed to generate local iCalendar events: {e}")
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
        
        for workout in draft.schedule:
            day_key = workout.session_slot
            if workout.scheduled_start_iso:
                start_time = datetime.datetime.fromisoformat(workout.scheduled_start_iso)
            else:
                offset = parse_day_offset(day_key)
                start_time = now + datetime.timedelta(days=offset)
                if "(AM)" in day_key:
                    start_time = start_time.replace(hour=8, minute=0, second=0, microsecond=0)
                elif "(PM)" in day_key:
                    start_time = start_time.replace(hour=18, minute=0, second=0, microsecond=0)
                
            start_utc = start_time.astimezone(datetime.timezone.utc)
            end_utc = start_utc + datetime.timedelta(minutes=workout.duration_minutes)
            
            description_text = (
                f"Target Heart Rate Zone: Zone {workout.target_zone}\n"
                f"Target Duration: {workout.duration_minutes} minutes\n"
                f"Original Workout: {workout.original_workout}\n"
                f"Physiological Focus: {workout.physiological_focus}\n\n"
                f"Rationale: {workout.rationale}"
            )
            
            # Map target_zone to Google Calendar API colorIds:
            # - Zone 1: Graphite / Grey (colorId: "8")
            # - Zone 2: Blueberry / Blue (colorId: "9")
            # - Zone 3: Basil / Green (colorId: "10")
            # - Zone 4: Tangerine / Orange (colorId: "6")
            # - Zone 5: Tomato / Red (colorId: "11")
            zone = workout.target_zone
            if zone == 1:
                color_id = "8"
            elif zone == 2:
                color_id = "9"
            elif zone == 3:
                color_id = "10"
            elif zone == 4:
                color_id = "6"
            elif zone == 5:
                color_id = "11"
            else:
                color_id = "8"
            
            event_body = {
                "summary": f"PacePilot: {workout.adjusted_workout}",
                "description": description_text,
                "start": {
                    "dateTime": start_utc.isoformat(),
                    "timeZone": "UTC"
                },
                "end": {
                    "dateTime": end_utc.isoformat(),
                    "timeZone": "UTC"
                },
                "colorId": color_id
            }
            
            logger.info(f"Dispatching event payload for '{workout.adjusted_workout}' to Google Calendar ID: {calendar_id}...")
            created_event = service.events().insert(calendarId=calendar_id, body=event_body).execute()
            logger.info(
                f"[SUCCESS] Workout event successfully injected into Google Calendar! "
                f"Link: {created_event.get('htmlLink')}"
            )
            
    except Exception as e:
        logger.error(f"Error during Google Calendar execution: {e}")
        return True
        
    return True

def sync_workout_to_calendar(draft) -> bool:
    """Wrapper function to maintain backward compatibility."""
    return execute_final_action(draft)

