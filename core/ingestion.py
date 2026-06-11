import os
import json
import logging
import datetime
from typing import Optional, Any
import requests
from pydantic import BaseModel, Field
from garminconnect import Garmin

# Set up logging
logger = logging.getLogger("PacePilot.Ingestion")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

# Ensure Garmin token directory is set to a secure, ignored project path
if "GARMINTOKENS" not in os.environ:
    token_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "venv", ".garmin_tokens"))
    os.makedirs(token_dir, exist_ok=True)
    os.environ["GARMINTOKENS"] = token_dir

# WMO weather code descriptions map (Open-Meteo)
WMO_CODE_MAP = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Drizzle: Light intensity",
    53: "Drizzle: Moderate intensity",
    55: "Drizzle: Dense intensity",
    56: "Freezing Drizzle: Light intensity",
    57: "Freezing Drizzle: Dense intensity",
    61: "Rain: Slight intensity",
    63: "Rain: Moderate intensity",
    65: "Rain: Heavy intensity",
    66: "Freezing Rain: Light intensity",
    67: "Freezing Rain: Heavy intensity",
    71: "Snow fall: Slight intensity",
    73: "Snow fall: Moderate intensity",
    75: "Snow fall: Heavy intensity",
    77: "Snow grains",
    80: "Rain showers: Slight",
    81: "Rain showers: Moderate",
    82: "Rain showers: Violent",
    85: "Snow showers: Slight",
    86: "Snow showers: Heavy",
    95: "Thunderstorm: Slight or moderate",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail"
}


# ==========================================
# 1. Data Models (Type Safety - Pydantic v2)
# ==========================================

class BiometricData(BaseModel):
    sleep_score: int = Field(..., description="Sleep score out of 100")
    hrv_status: str = Field(..., description="Heart Rate Variability readiness status (e.g. BALANCED, UNBALANCED)")
    acute_training_load: Optional[float] = Field(None, description="Acute training load value based on EPOC")


class WeatherData(BaseModel):
    temperature_c: float = Field(..., description="Current temperature in Celsius")
    humidity: int = Field(..., description="Relative humidity percentage")
    summary: str = Field(..., description="Text summary of weather conditions")


class EnvironmentState(BaseModel):
    biometric: BiometricData
    weather: WeatherData
    iso_timestamp: str = Field(..., description="ISO 8601 timestamp of data ingestion")


# ==========================================
# Helper Utilities
# ==========================================

def find_key_recursive(data: Any, target_key: str) -> Optional[Any]:
    """
    Recursively scans nested dictionaries and lists to find a specific key.
    Provides schema-change resilience for unofficial internal API scraping.
    """
    if isinstance(data, dict):
        if target_key in data:
            return data[target_key]
        for key, val in data.items():
            res = find_key_recursive(val, target_key)
            if res is not None:
                return res
    elif isinstance(data, list):
        for item in data:
            res = find_key_recursive(item, target_key)
            if res is not None:
                return res
    return None


# ==========================================
# 2. Garmin Connect Client Module
# ==========================================

def get_mock_biometrics() -> BiometricData:
    """Provides fallback biometric values in case of API failure."""
    logger.info("Using fallback biometric data.")
    return BiometricData(
        sleep_score=75,
        hrv_status="BALANCED",
        acute_training_load=480.0
    )


def get_garmin_biometrics(email: Optional[str], password: Optional[str], fallback_sleep: int = 75, fallback_hrv: str = "BALANCED") -> BiometricData:
    """
    Attempts to fetch biometric data from Garmin Connect.
    If login or data extraction fails, falls back gracefully to override values.
    """
    if not email or not password:
        logger.warning("Garmin email or password environment variables are not set.")
        return BiometricData(
            sleep_score=fallback_sleep,
            hrv_status=fallback_hrv,
            acute_training_load=480.0
        )

    try:
        logger.info(f"Initializing Garmin Connect client for {email}...")
        client = Garmin(email, password)
        logger.info("Authenticating with Garmin...")
        client.login()
        logger.info("Garmin authentication successful.")

        today_str = datetime.date.today().isoformat()
        
        # 1. Fetch Sleep Score
        sleep_score = fallback_sleep
        try:
            sleep_data = client.get_sleep_data(today_str)
            score = find_key_recursive(sleep_data, "sleepScore")
            if score is not None:
                sleep_score = int(score)
                logger.info(f"Extracted Garmin sleep score: {sleep_score}")
            else:
                logger.warning("Could not locate sleep score in Garmin response.")
        except Exception as e:
            logger.error(f"Failed to fetch or parse Garmin sleep data: {e}")

        # 2. Fetch HRV Status
        hrv_status = fallback_hrv
        try:
            hrv_data = client.get_hrv_data(today_str)
            status = find_key_recursive(hrv_data, "hrvReadinessStatus")
            if status is not None:
                hrv_status = str(status)
                logger.info(f"Extracted Garmin HRV status: {hrv_status}")
            else:
                logger.warning("Could not locate HRV readiness status in Garmin response.")
        except Exception as e:
            logger.error(f"Failed to fetch or parse Garmin HRV data: {e}")

        # 3. Fetch Acute Training Load
        acute_training_load = 480.0
        try:
            training_status = client.get_training_status(today_str)
            load = find_key_recursive(training_status, "acuteTrainingLoad")
            if isinstance(load, dict):
                load = load.get("currentLoad")
            if load is not None:
                acute_training_load = float(load)
                logger.info(f"Extracted Garmin acute training load: {acute_training_load}")
            else:
                logger.warning("Could not locate acute training load in Garmin training status response.")
        except Exception as e:
            logger.error(f"Failed to fetch or parse Garmin training status: {e}")

        return BiometricData(
            sleep_score=sleep_score,
            hrv_status=hrv_status,
            acute_training_load=acute_training_load
        )

    except Exception as e:
        logger.error(f"Garmin ingestion flow failed: {e}")
        return BiometricData(
            sleep_score=fallback_sleep,
            hrv_status=fallback_hrv,
            acute_training_load=480.0
        )


# ==========================================
# 3. Weather Client Module
# ==========================================

def get_mock_weather() -> WeatherData:
    """Provides fallback weather values in case of API failure."""
    logger.info("Using fallback weather data.")
    return WeatherData(
        temperature_c=18.0,
        humidity=60,
        summary="Partly cloudy (Mocked)"
    )


def get_weather_data(latitude: float, longitude: float) -> WeatherData:
    """
    Fetches real-time weather forecasts from Open-Meteo API.
    Gracefully falls back to mock values on failure.
    """
    url = "https://api.open-meteo.com/v1/forecast"
    # We pass current_weather=true as requested, and request current relative humidity.
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current_weather": "true",
        "current": "relative_humidity_2m"
    }

    try:
        logger.info(f"Querying Open-Meteo at ({latitude}, {longitude})...")
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        current_w = data.get("current_weather", {})
        temperature = float(current_w.get("temperature", 18.0))
        wmo_code = int(current_w.get("weathercode", 0))
        summary = WMO_CODE_MAP.get(wmo_code, "Unknown weather conditions")

        # Extraction of humidity
        humidity = 60
        current_data = data.get("current", {})
        if "relative_humidity_2m" in current_data:
            humidity = int(current_data["relative_humidity_2m"])
        else:
            # Secondary check: Check hourly arrays
            hourly_data = data.get("hourly", {})
            relative_humidity_list = hourly_data.get("relative_humidity_2m", [])
            if relative_humidity_list:
                humidity = int(relative_humidity_list[0])
                logger.info("Extracted humidity from fallback hourly data array.")

        logger.info(f"Weather fetched: {temperature}°C, {humidity}% humidity, {summary}")
        return WeatherData(
            temperature_c=temperature,
            humidity=humidity,
            summary=summary
        )

    except Exception as e:
        logger.error(f"Failed to fetch or parse weather data: {e}")
        return get_mock_weather()


# ==========================================
# 4. Data Aggregation & Persistence
# ==========================================

def fetch_daily_context(lat: float, lon: float, fallback_sleep: int = 75, fallback_hrv: str = "BALANCED") -> EnvironmentState:
    """
    Central coordinator executing biometric and weather context ingestion.
    Combines observations into EnvironmentState and writes to state.json.
    """
    logger.info("Initializing environment context acquisition...")

    # Extract credentials from local env
    email = os.getenv("GARMIN_EMAIL")
    password = os.getenv("GARMIN_PASSWORD")

    # Ingest components sequentially
    biometric = get_garmin_biometrics(email, password, fallback_sleep, fallback_hrv)
    weather = get_weather_data(lat, lon)

    # Wrap in EnvironmentState
    iso_timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    state = EnvironmentState(
        biometric=biometric,
        weather=weather,
        iso_timestamp=iso_timestamp
    )

    # Save to state.json in root path
    root_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    state_path = os.path.join(root_dir, "state.json")

    try:
        state_dict = state.model_dump()
        with open(state_path, "w", encoding="utf-8") as f:
            json.dump(state_dict, f, indent=2, ensure_ascii=False)
        logger.info(f"Environment state snapshot written to {state_path}")
    except Exception as e:
        logger.error(f"Failed to write environment state to disk: {e}")

    return state
