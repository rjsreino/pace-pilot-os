import os
import json
import datetime
import uuid
import streamlit as st

# Ensure root directory is in python module search path
import sys
root_dir = os.path.abspath(os.path.dirname(__file__))
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

# Load environment variables from .env
from dotenv import load_dotenv
load_dotenv(os.path.join(root_dir, '.env'))

from core.ingestion import fetch_daily_context, EnvironmentState
from core.models import UserSettings, WeeklyScheduleDraft, WorkoutDraft
from core.engine import generate_weekly_schedule_draft, regenerate_weekly_schedule_with_feedback
from core.parser import parse_day_offset
from core.execution import execute_final_action

# Predefined Global City Database (50 Cities)
city_db = {
    "Seoul": (37.5665, 126.9780),
    "Tokyo": (35.6762, 139.6503),
    "Jakarta": (-6.2088, 106.8456),
    "Amsterdam": (52.3676, 4.9041),
    "London": (51.5074, -0.1278),
    "New York": (40.7128, -74.0060),
    "Paris": (48.8566, 2.3522),
    "Sydney": (-33.8688, 151.2093),
    "Singapore": (1.3521, 103.8198),
    "Berlin": (52.5200, 13.4050),
    "Boston": (42.3601, -71.0589),
    "Chicago": (41.8781, -87.6298),
    "Los Angeles": (34.0522, -118.2437),
    "San Francisco": (37.7749, -122.4194),
    "Seattle": (47.6062, -122.3321),
    "Vancouver": (49.2827, -123.1207),
    "Toronto": (43.6532, -79.3832),
    "Montreal": (45.5017, -73.5673),
    "Mexico City": (19.4326, -99.1332),
    "São Paulo": (-23.5505, -46.6333),
    "Buenos Aires": (-34.6037, -58.3816),
    "Cape Town": (-33.9249, 18.4241),
    "Cairo": (30.0444, 31.2357),
    "Nairobi": (-1.2921, 36.8219),
    "Dubai": (25.2048, 55.2708),
    "Mumbai": (19.0760, 72.8777),
    "New Delhi": (28.6139, 77.2090),
    "Bangkok": (13.7563, 100.5018),
    "Kuala Lumpur": (3.1390, 101.6869),
    "Manila": (14.5995, 120.9842),
    "Hong Kong": (22.3193, 114.1694),
    "Taipei": (25.0330, 121.5654),
    "Melbourne": (-37.8136, 144.9631),
    "Auckland": (-36.8485, 174.7633),
    "Rome": (41.9028, 12.4964),
    "Madrid": (40.4168, -3.7038),
    "Lisbon": (38.7223, -9.1393),
    "Vienna": (48.2082, 16.3738),
    "Zurich": (47.3769, 8.5417),
    "Geneva": (46.2044, 6.1432),
    "Brussels": (50.8503, 4.3517),
    "Copenhagen": (55.6761, 12.5683),
    "Stockholm": (59.3293, 18.0686),
    "Oslo": (59.9139, 10.7522),
    "Helsinki": (60.1699, 24.9384),
    "Dublin": (53.3498, -6.2603),
    "Edinburgh": (55.9533, -3.1883),
    "Reykjavik": (64.1466, -21.9426),
    "Munich": (48.1351, 11.5820),
    "Frankfurt": (50.1109, 8.6821)
}


# Set page configs
st.set_page_config(page_title="PacePilot Dashboard", layout="wide", page_icon="🏃‍♂️")

# Custom Styles for premium aesthetics
st.markdown("""
<style>
    /* Dark glassmorphic headers */
    .title-banner {
        background: linear-gradient(135deg, #1e293b, #10b981);
        padding: 35px;
        border-radius: 16px;
        color: white;
        text-align: center;
        margin-bottom: 30px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.3);
    }
    .title-banner h1 {
        font-family: 'Outfit', 'Inter', sans-serif;
        font-weight: 800;
        margin: 0;
        font-size: 2.8em;
    }
    .title-banner p {
        font-family: 'Inter', sans-serif;
        font-weight: 300;
        margin-top: 10px;
        font-size: 1.1em;
        opacity: 0.9;
    }
    /* Workout card styling */
    .workout-card {
        background: rgba(30, 41, 59, 0.45);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 14px;
        padding: 22px;
        margin-bottom: 20px;
        backdrop-filter: blur(12px);
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.3);
        transition: transform 0.2s ease, border-color 0.2s ease;
    }
    .workout-card:hover {
        transform: translateY(-2px);
        border-color: rgba(16, 185, 129, 0.4);
    }
    .card-title {
        color: #10b981;
        font-family: 'Outfit', sans-serif;
        font-size: 1.4em;
        font-weight: 700;
        margin-bottom: 10px;
    }
    .card-meta {
        font-family: 'Inter', sans-serif;
        font-size: 0.95em;
        color: #94a3b8;
        margin-bottom: 14px;
        background: rgba(16, 185, 129, 0.08);
        padding: 8px 12px;
        border-radius: 8px;
        border-left: 3px solid #10b981;
    }
    .card-focus {
        color: #38bdf8;
        font-family: 'Inter', sans-serif;
        font-weight: 600;
        font-size: 0.95em;
        margin-bottom: 12px;
    }
    .card-rationale {
        border-left: 2px solid rgba(255, 255, 255, 0.2);
        padding-left: 12px;
        font-size: 0.92em;
        color: #cbd5e1;
        line-height: 1.5;
    }
    /* Enlarge Streamlit Radio and Selection Component Font Sizes */
    .stRadio [data-testid="stMarkdownContainer"] p {
        font-size: 20px !important;
        font-weight: 600 !important;
    }
    /* Add high-visibility highlight padding to the authorization box */
    div[data-testid="stForm"] {
        border: 2px solid #ff4b4b !important;
        padding: 20px !important;
        border-radius: 10px !important;
    }
</style>
""", unsafe_allow_html=True)

# Title Banner
st.markdown("""
<div class="title-banner">
    <h1>🏃‍♂️ PacePilot Web Dashboard</h1>
    <p>Premium Agentic Macro-Cycle Weekly Training Coordinator & Sync Engine</p>
</div>
""", unsafe_allow_html=True)

# Sidebar configuration
st.sidebar.header("👤 Athlete Settings")

distance_goal = st.sidebar.selectbox(
    "Target Goal Distance",
    options=["5K", "10K", "HALF", "MARATHON"],
    index=2  # default to HALF
)

target_weekly_mileage = st.sidebar.slider(
    "Target Weekly Volume (km)",
    min_value=5.0,
    max_value=150.0,
    value=40.0,
    step=1.0
)

# Advanced Configuration
with st.sidebar.expander("⚙️ Advanced Coordinates & Credentials"):
    selected_city = st.selectbox("Select Target Training Location Location:", options=list(city_db.keys()), index=0)
    lat, lon = city_db[selected_city]
    st.write(f"📍 Coordinates: **{lat:.4f}, {lon:.4f}**")
    
    st.write("---")
    st.write("🔑 Credentials Overrides")
    
    garmin_email = st.text_input("Garmin Connect Email", value=os.getenv("GARMIN_EMAIL", ""))
    garmin_password = st.text_input("Garmin Connect Password", value=os.getenv("GARMIN_PASSWORD", ""), type="password")
    calendar_id = st.text_input("Google Calendar ID", value=os.getenv("GOOGLE_CALENDAR_ID", "primary"))
    gemini_key = st.text_input("Gemini API Key", value=os.getenv("GEMINI_API_KEY", ""), type="password")
    
    # Save inputs back to environment
    if garmin_email:
        os.environ["GARMIN_EMAIL"] = garmin_email
    if garmin_password:
        os.environ["GARMIN_PASSWORD"] = garmin_password
    if calendar_id:
        os.environ["GOOGLE_CALENDAR_ID"] = calendar_id
    if gemini_key:
        os.environ["GEMINI_API_KEY"] = gemini_key

# Check status of configuration
if not os.getenv("GARMIN_EMAIL") or not os.getenv("GARMIN_PASSWORD"):
    st.sidebar.warning("⚠️ No Garmin credentials set. Pipeline will fall back to local offline biometric metrics.")
if not os.getenv("GEMINI_API_KEY"):
    st.sidebar.warning("⚠️ No Gemini API key set. Pipeline will fall back to local offline reasoning models.")

# Initialize session state variables
if "state" not in st.session_state:
    st.session_state["state"] = None
if "draft_1" not in st.session_state:
    st.session_state["draft_1"] = None
if "draft_2" not in st.session_state:
    st.session_state["draft_2"] = None
if "selected_draft_key" not in st.session_state:
    st.session_state["selected_draft_key"] = "Draft 1"

# ----------------------------------------------------
# Phase 1: Context Ingestion
# ----------------------------------------------------
st.header("⚡ Phase 1: Multi-Source Data Ingestion")
with st.container():
    st.write("### 🛠️ Ingestion Manual Overrides & Fallback Options")
    override_col1, override_col2 = st.columns(2)
    with override_col1:
        manual_sleep = st.slider("Manual Override: Sleep Score", min_value=0, max_value=100, value=75)
    with override_col2:
        manual_hrv = st.selectbox("Manual Override: HRV Status", options=["BALANCED", "LOW", "UNBALANCED"], index=0)

    st.write("")
    col1, col2 = st.columns([1, 4])
    with col1:
        ingest_btn = st.button("🔄 Ingest Current Context", use_container_width=True)
    
    # Check if we have state loaded from file
    state_file = os.path.join(root_dir, "state.json")
    if ingest_btn:
        with st.spinner("Ingesting biometrics (Garmin) and climate data (Open-Meteo)..."):
            try:
                state = fetch_daily_context(lat, lon, fallback_sleep=manual_sleep, fallback_hrv=manual_hrv)
                st.session_state["state"] = state
                st.session_state["draft_1"] = None  # Reset recommendation
                st.session_state["draft_2"] = None  # Reset feedback adjustment
                st.success("✅ Context successfully ingested!")
            except Exception as e:
                st.error(f"❌ Ingestion Failed: {e}")
    
    # Load state.json if it exists and session_state is empty
    if st.session_state["state"] is None and os.path.exists(state_file):
        try:
            with open(state_file, "r", encoding="utf-8") as f:
                raw = json.load(f)
            st.session_state["state"] = EnvironmentState.model_validate(raw)
        except Exception:
            pass

    # Display Metrics if state exists
    state = st.session_state["state"]
    if state:
        st.write("### Current Physiological and Environmental Context")
        mcol1, mcol2, mcol3, mcol4 = st.columns(4)
        with mcol1:
            st.metric("💤 Sleep Score", f"{state.biometric.sleep_score}/100")
        with mcol2:
            st.metric("💓 HRV Status", state.biometric.hrv_status)
        with mcol3:
            st.metric("🌡️ Temperature", f"{state.weather.temperature_c} °C")
        with mcol4:
            st.metric("💧 Humidity", f"{state.weather.humidity} %")
            
        st.info(f"**Weather Summary:** {state.weather.summary} | **Ingested at (UTC):** {state.iso_timestamp}")
    else:
        st.warning("⚠️ No context data ingested yet. Click the button above to fetch data.")

# ----------------------------------------------------
# Phase 2 & 3: Weekly Planning & Validation
# ----------------------------------------------------
if state:
    st.write("---")
    st.header("🧠 Phase 2 & 3: Weekly Plan Generation & Reversion-Cache")
    
    # Generate Draft 1 if it doesn't exist
    if st.session_state["draft_1"] is None:
        with st.spinner("Generating initial weekly recommendations..."):
            settings = UserSettings(distance_goal=distance_goal, target_weekly_mileage=target_weekly_mileage)
            draft_1 = generate_weekly_schedule_draft(settings, state)
            st.session_state["draft_1"] = draft_1
            st.session_state["draft_2"] = None
            st.session_state["selected_draft_key"] = "Draft 1"

    # Display plan card renderer
    def render_schedule_cards(draft: WeeklyScheduleDraft):
        num_sessions = len(draft.schedule)
        if num_sessions > 0:
            card_cols = st.columns(num_sessions)
            for idx, workout in enumerate(draft.schedule):
                day_key = workout.session_slot
                with card_cols[idx]:
                    st.markdown(f"""
                    <div class="workout-card">
                        <div class="card-title">{day_key}</div>
                        <div class="card-meta"><b>Target:</b> {workout.adjusted_workout} <br><b>Zone:</b> {workout.target_zone} | <b>Duration:</b> {workout.duration_minutes} mins</div>
                        <div class="card-focus">🔬 Focus: {workout.physiological_focus}</div>
                        <div class="card-rationale"><b>Rationale:</b> {workout.rationale}</div>
                        <p style='font-size:0.82em; color:#64748b; margin-top:14px; border-top:1px solid rgba(255,255,255,0.06); padding-top:10px;'>Original Plan: {workout.original_workout}</p>
                    </div>
                    """, unsafe_allow_html=True)

    # Subjective Feedback Loop Panel
    st.write("### 🔁 Re-evaluate with Subjective Feedback")
    
    feedback_text = st.text_area(
        "How do you feel? (e.g. 'legs sore', 'feeling energized and fresh')",
        placeholder="Add details about fatigue, soreness, or general health here...",
        key="user_feedback"
    )
    
    readjust_btn = st.button("🔄 Readjust Schedule")
    
    if readjust_btn:
        if feedback_text.strip():
            with st.spinner("Regenerating weekly plan incorporating feedback..."):
                try:
                    settings = UserSettings(distance_goal=distance_goal, target_weekly_mileage=target_weekly_mileage)
                    draft_2 = regenerate_weekly_schedule_with_feedback(
                        state_file,
                        settings,
                        feedback_text.strip(),
                        st.session_state["draft_1"]
                    )
                    st.session_state["draft_2"] = draft_2
                    st.session_state["selected_draft_key"] = "Draft 2"
                    st.success("✅ Feedback-adjusted plan generated!")
                except Exception as e:
                    st.error(f"❌ Feedback adjustment failed: {e}")
        else:
            st.warning("⚠️ Please enter subjective feedback text before requesting readjustment.")

    # Render Plans for Comparison
    draft_1 = st.session_state["draft_1"]
    draft_2 = st.session_state["draft_2"]

    if draft_2:
        st.write("### ⚖️ Proposed Plan Comparison")
        with st.container():
            st.write("#### 📋 Draft 2: Feedback-Adjusted Plan")
            render_schedule_cards(draft_2)
            
        st.divider()
        
        with st.container():
            st.write("#### 📋 Draft 1: Initial Recommendation")
            render_schedule_cards(draft_1)
    else:
        st.write("### 📋 Current Recommended Plan")
        with st.container():
            render_schedule_cards(draft_1)

# ----------------------------------------------------
# Phase 4: Execution / Authorization
# ----------------------------------------------------
if state and st.session_state["draft_1"]:
    st.write("---")
    st.header("📅 Phase 4: Temporal Window & Calendar Sync")
    
    now = datetime.datetime.now().astimezone()
    is_temporal_cap = now.hour >= 20
    if is_temporal_cap:
        st.warning("⚠️ **[TEMPORAL CAP]** It is past optimal training hours. Shifting baseline options to tomorrow.")

    tcol1, tcol2 = st.columns(2)
    with tcol1:
        window_selection = st.selectbox(
            "Select Target Workout Window",
            options=[
                "Morning Window (Tomorrow at 7:00 AM) - Heat mitigation",
                "Evening Window (Tomorrow at 6:00 PM) - Cool post-class window",
                "Custom Time Slot (Specify Days Offset & Hour)"
            ]
        )
        
        # Calculate base_time
        if "Morning Window" in window_selection:
            tomorrow = now + datetime.timedelta(days=1)
            base_time = tomorrow.replace(hour=7, minute=0, second=0, microsecond=0)
        elif "Evening Window" in window_selection:
            tomorrow = now + datetime.timedelta(days=1)
            base_time = tomorrow.replace(hour=18, minute=0, second=0, microsecond=0)
        else:
            days_offset = st.number_input("Days Offset from Today", min_value=0, value=1)
            hour_of_day = st.slider("Hour of the Day (0-23)", min_value=0, max_value=23, value=9)
            target_date = now + datetime.timedelta(days=days_offset)
            base_time = target_date.replace(hour=hour_of_day, minute=0, second=0, microsecond=0)
            
        st.write(f"📅 **Selected Week Start Date (Base):** {base_time.strftime('%Y-%m-%d %I:%M %p %Z')}")

    with tcol2:
        st.write("🚀 **Authorized Event Schedule Summary**")
        active_draft = st.session_state["draft_2"] if st.session_state["selected_draft_key"] == "Draft 2" else st.session_state["draft_1"]
        
        # Display chronological order list of dates
        for workout in active_draft.schedule:
            day_key = workout.session_slot
            offset = parse_day_offset(day_key)
            w_date = base_time + datetime.timedelta(days=offset)
            if "(AM)" in day_key:
                w_date = w_date.replace(hour=8, minute=0, second=0, microsecond=0)
            elif "(PM)" in day_key:
                w_date = w_date.replace(hour=18, minute=0, second=0, microsecond=0)
            st.write(f"- **{w_date.strftime('%a, %b %d')}** | {workout.adjusted_workout} ({workout.duration_minutes}m, Z{workout.target_zone})")

    # Authorize Form
    st.write("")
    with st.form("authorization_form"):
        selected_draft_choice = st.radio(
            "👉 Select Your Verified Training Protocol to Synchronize:",
            options=["Draft 1 (Original)", "Draft 2 (Feedback-adjusted)"] if draft_2 else ["Draft 1 (Original)"],
            index=1 if (draft_2 and st.session_state.get("selected_draft_key") == "Draft 2") else 0
        )
        push_btn = st.form_submit_button("🟢 Authorize & Push Weekly Training to Google Calendar", use_container_width=True)
    
    if push_btn:
        selected_draft_key = "Draft 2" if "Draft 2" in selected_draft_choice else "Draft 1"
        st.session_state["selected_draft_key"] = selected_draft_key
        
        with st.spinner("Pushing weekly schedule to local .ics file and Google Calendar..."):
            try:
                active_draft = st.session_state["draft_2"] if selected_draft_key == "Draft 2" else st.session_state["draft_1"]
                final_weekly_draft = active_draft.model_copy(deep=True)
                
                # Assign dates
                for workout in final_weekly_draft.schedule:
                    day_key = workout.session_slot
                    offset = parse_day_offset(day_key)
                    w_date = base_time + datetime.timedelta(days=offset)
                    if "(AM)" in day_key:
                        w_date = w_date.replace(hour=8, minute=0, second=0, microsecond=0)
                    elif "(PM)" in day_key:
                        w_date = w_date.replace(hour=18, minute=0, second=0, microsecond=0)
                    workout.scheduled_start_iso = w_date.isoformat()
                
                # Execute action
                success = execute_final_action(final_weekly_draft)
                if success:
                    st.balloons()
                    st.success("🎉 **Success!** PacePilot weekly training plan successfully synchronized!")
                    st.markdown("""
                    - **Local iCalendar File (`pacepilot_workout.ics`)** has been refreshed in the root directory.
                    - **Google Calendar Events** have been dispatched over the network.
                    """)
                else:
                    st.error("❌ Synchronization failed during calendar generation.")
            except Exception as e:
                st.error(f"❌ Error executing calendar injection: {e}")
