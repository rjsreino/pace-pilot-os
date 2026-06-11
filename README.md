# PacePilot: An Adaptive Agentic AI Running Coach

PacePilot is an agentic AI running coach system developed to replace static, rigid training plans with a dynamic, feedback-driven macro-cycle scheduler that adapts to your body and your environment in real time. 

By executing an autonomous **Observe → Think → Act** control loop, PacePilot synthesizes physiological biometrics (extracted via Garmin Connect) with localized climate conditions (fetched via Open-Meteo) to dynamically calibrate running frequency, volume, and intensity, preventing overtraining and optimizing athletic adaptation.

---

## 🚀 Key Features

- **Observe: Multi-Source Ingestion & Overrides**
  - Programmatic fetching of personal recovery metrics (Sleep Score, HRV status, Acute Training Load) and hyper-local hourly weather data (temperature, humidity, condition summary).
  - **Ingestion Manual Overrides:** Sidebar sliders for Sleep Score and HRV status to serve as robust fallbacks when Garmin APIs rate-limit or fail.
  - **Global City Coordinator:** A database of 15 major international cities (Seoul, Tokyo, Jakarta, Amsterdam, London, New York, etc.) mapped directly in the sidebar, dynamically resolving coordinates for weather forecasts.
- **Think: Adaptive Weekly Macro Planning**
  - **Dynamic Frequency Scaling:** Scales weekly training frequency from 3 to 7 sessions based on target mileage, preventing orthopedic overreaching.
  - **Heuristics & LLM Orchestration:** Combines a deterministic **Climate-Biometric Heuristic Algorithm** with a gatekeeper LLM (defaulting to `gemma-4-31b-it`) using Pydantic JSON validation schemas.
  - **Rigid Duration Constraints:** Baseline workout durations are computed deterministically in Python first and injected as rigid prompt constraints, completely eliminating LLM duration inflation under heat conditions.
  - **Sanitization Parsing Defenses:** Regular expression filter strips markdown code blocks (```json ... ```) and conversational prefixes/suffixes to protect JSON parsing.
- **Human-in-the-Loop Validation Gatekeeper**
  - **Premium Streamlit Web Dashboard:** Wide layout design utilizing glassmorphism styling, clean workout cards, and font scaling.
  - **Inverted UX Comparison Loop:** Relies on `st.session_state` caching. If Draft 2 (feedback-adjusted) is generated, it renders Draft 2 at the very top of the page, followed by a divider and Draft 1 below.
  - **Interactive Readjustment:** Subjective feedback text input (e.g., *"legs are stiff"*) triggers negation-aware sentiment parsing to down-regulate intensity, or scale up workouts to safety bounds.
- **Act: Google Calendar & Local Synchronization**
  - **Garmin-Inspired Color Coding:** Automatically maps target heart rate zones (Zones 1-5) to Google Calendar API `colorId` values (Graphite, Blueberry, Basil, Tangerine, Tomato).
  - **Temporal Windows & Form Wrapping:** Phase 4 validation is wrapped in a standard `st.form` block. Adjusts schedule times based on temporal caps (past 8:00 PM shifts suggestions to tomorrow) with Morning, Evening, and Custom slots.
  - **Dual Synchronization:** Sequentially generates a combined local `pacepilot_workout.ics` calendar file in the workspace root and pushes batch event payloads to Google Calendar.

---

## 🏗 System Architecture & Control Loop

PacePilot organizes its operations across four clean engineering phases:

1. **Phase 1: Context Ingestion (Observe):** Sequentially queries Garmin Connect and Open-Meteo, using recursive key parsing (`find_key_recursive`) to persist an aggregated snapshot in `state.json`.
2. **Phase 2: Reasoning Engine (Think):** Validates target parameters against environmental caps (e.g., >28°C triggers a 20% volume cap; under-recovery restricts heart rate zones) and generates a weekly plan.
3. **Phase 3: Validation Gatekeeper (Human-in-the-Loop):** Streamlit dashboard renders the plans, allowing the user to provide subjective details, compare schedules, and select the final plan.
4. **Phase 4: Target Execution (Act):** Packages workouts, assigns dates and start hours (supporting AM/PM double sessions on high-volume slots), injects Garmin intensity color codes, and dispatches batch events.

---

## 🛠 Project Structure

```text
pace-pilot-os/
├── .env.example                # Template for environment variables and API keys
├── .gitignore                  # Keeps local tokens, credentials, and cache out of git
├── README.md                   # Project documentation and lifecycle summary
├── requirements.txt            # Python dependency manifest (streamlit, google-api, etc.)
├── app.py                      # Robust Streamlit Web UI and state-cached coordinator
├── main.py                     # CLI pipeline entry point and console coordinator
├── pacepilot_workout.ics       # Generated combined local iCalendar schedule file
├── scratch/
│   ├── verify_weekly.py        # End-to-end weekly integration verification script
│   └── test_sentiment.py       # Sentiment regression test suite (30 test phrases)
└── core/                       # Core modular package submodules
    ├── __init__.py             # Package initializer
    ├── models.py               # Explicit Pydantic v2 schemas (UserSettings, WorkoutDraft, WeeklyScheduleDraft)
    ├── parser.py               # Running terminology detail parsers and name builders
    ├── sentiment.py            # Negation-aware token sentiment classifier with suffix stemming
    ├── heuristics.py           # Climate and biometric safety cap heuristics
    ├── fallback.py             # Offline deterministic generators and split math formulas
    ├── engine.py               # Orchestrator routing API requests and sanitizing JSON strings
    ├── validation.py           # Terminal validation state-machine gatekeeper loop
    └── execution.py            # Event packaging, color-coding mappings, and Calendar dispatchers
```
