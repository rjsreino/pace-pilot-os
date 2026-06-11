import re

def parse_workout_details(workout_name: str) -> tuple[int, int]:
    """
    Parses common running community target zones and duration in minutes
    from standard workout titles (e.g. '60-minute Threshold Tempo Run').
    """
    # Default parameters
    default_zone = 2
    default_duration = 45

    # 1. Parse Duration
    duration_match = re.search(r"(\d+)\s*-?\s*minute", workout_name, re.IGNORECASE)
    if duration_match:
        duration = int(duration_match.group(1))
    else:
        min_match = re.search(r"(\d+)\s*(?:min|mins)", workout_name, re.IGNORECASE)
        if min_match:
            duration = int(min_match.group(1))
        else:
            duration = default_duration

    # 2. Parse Zone using standard running terminologies
    name_lower = workout_name.lower()
    if "zone 5" in name_lower or "threshold" in name_lower or "interval" in name_lower:
        zone = 5
    elif "zone 4" in name_lower or "uptempo" in name_lower:
        zone = 4
    elif "zone 3" in name_lower or "tempo" in name_lower:
        zone = 3
    elif "zone 2" in name_lower or "easy" in name_lower:
        zone = 2
    elif "zone 1" in name_lower or "recovery" in name_lower:
        zone = 1
    else:
        zone = default_zone

    return zone, duration


def rebuild_workout_name(workout_name: str, new_duration: int, prefix: str = "") -> str:
    """
    Cleans any existing duration prefix (e.g. '36-minute', '36 min') and prepends
    the new target duration and optional intensity modifier to prevent conflicts.
    """
    name_clean = workout_name.strip()
    
    # 1. Strip common modifier prefixes first to expose duration
    modifiers = ["Reduced Intensity", "Heat-adjusted", "Biometrically-Capped"]
    for mod in modifiers:
        name_clean = re.sub(r"^" + re.escape(mod) + r"\s*", "", name_clean, flags=re.IGNORECASE).strip()
        
    # 2. Strip duration prefix (e.g., "36-minute", "30 minute")
    duration_pattern = r"^\d+\s*(?:-?\s*minute|-?\s*min|-?\s*mins)\s*"
    name_clean = re.sub(duration_pattern, "", name_clean, flags=re.IGNORECASE).strip()
    
    # 3. Strip modifiers again in case they were after duration (e.g., "36-minute Reduced Intensity...")
    for mod in modifiers:
        name_clean = re.sub(r"^" + re.escape(mod) + r"\s*", "", name_clean, flags=re.IGNORECASE).strip()
        
    # 4. Construct new name
    if prefix:
        return f"{new_duration}-minute {prefix.strip()} {name_clean}"
    else:
        return f"{new_duration}-minute {name_clean}"


def parse_day_offset(day_key: str) -> int:
    """
    Parses the day number from a key like 'Day 4 (AM): Recovery Flush' -> 4.
    If no day number is found, defaults to 0.
    """
    match = re.search(r"Day\s*(\d+)", day_key, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return 0

