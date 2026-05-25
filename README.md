# PacePilot: An Adaptive Agentic AI Running Coach

PacePilot is an agentic AI system developed as an Operating Systems course project. It replaces static, rigid training plans with an intelligent, feedback-driven scheduler that adapts to your body and your environment in real time. 

By executing an autonomous **Observe → Think → Act** control loop, PacePilot synthesizes internal physiological biometrics (extracted via Garmin Connect) with localized external climate conditions (fetched via Open-Meteo) to dynamically calibrate running volume and intensity, preventing overtraining and optimizing athletic adaptation.

---

## 🚀 Features

- **Multi-Source Observation:** Programmatic fetching of personal recovery metrics (Sleep Score, HRV status, Acute Training Load) and hyper-local hourly weather data (temperature, humidity).
- **Dual-Layered Reasoning:** Integrates a rule-based **Climate-Biometric Heuristic Algorithm** with a **Lightweight LLM Orchestration Layer (GPT-4o-mini)** to analyze training constraints and generate customized workout adjustments.
- **Human-in-the-Loop Validation:** Safety gate that presents the modified schedule along with an explicit decision rationale, pausing for user approval (`[Y/N]`) before execution.
- **Autonomous Synchronization:** Automatically updates changes directly across your digital ecosystem via the **Google Calendar API** and pushes customized workouts back to the **Garmin Cloud**.

---

## 🏗 Architecture & Control Loop

PacePilot organizes its operations across four clean engineering phases:

1. **Phase 1: Data Ingestion (Observe)** Queries the `python-garminconnect` consumer wrapper and weather endpoints to construct a local daily context snapshot (`state.json`).
2. **Phase 2: Reasoning Engine (Think)** Evaluates variables against physical thresholds (e.g., auto-downgrading intensity when ambient temperatures exceed 28°C or HRV drops below baseline) and drafts a tailored schedule.
3. **Phase 3: Validation Gatekeeper (Human-in-the-Loop)** Displays an interactive prompt explaining the scientific rationale behind any training mutations.
4. **Phase 4: Target Execution (Act)** Performs downstream API pushes to Google Calendar and Garmin calendars simultaneously upon authorization.

---

## 🛠 Project Structure

```text
pacepilot/
├── .env.example         # Template for secure credentials
├── .gitignore           # Keeps API keys, venv, and cache out of source control
├── README.md            # Project documentation and assignment overview
├── requirements.txt     # Python dependency manifest
├── main.py              # Application entry point and control loop coordinator
└── core/                # Core system modules (to be implemented)
    ├── ingestion.py     # Garmin and Weather API integrations
    ├── engine.py        # Heuristic and LLM reasoning logic
    └── execution.py     # Google & Garmin calendar synchronization handles
```
