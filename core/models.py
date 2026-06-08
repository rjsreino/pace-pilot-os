from pydantic import BaseModel, Field

class WorkoutDraft(BaseModel):
    original_workout: str = Field(..., description="The name or description of the planned workout")
    adjusted_workout: str = Field(..., description="The name or description of the modified workout")
    target_zone: int = Field(..., description="Target training heart rate zone (1 to 5)")
    duration_minutes: int = Field(..., description="Target duration of the workout in minutes")
    rationale: str = Field(..., description="Detailed explanation of physiological or environmental adjustments")
    scheduled_start_iso: str = Field(default="", description="ISO 8601 string representing when the run is scheduled to begin")

