from pydantic import BaseModel, Field
from typing import Literal, List

class UserSettings(BaseModel):
    distance_goal: Literal["5K", "10K", "HALF", "MARATHON"] = Field(..., description="Target running distance goal")
    target_weekly_mileage: float = Field(..., description="Target weekly running mileage in kilometers")

class WorkoutDraft(BaseModel):
    original_workout: str = Field(..., description="The name or description of the planned workout")
    adjusted_workout: str = Field(..., description="The name or description of the modified workout")
    target_zone: int = Field(..., description="Target training heart rate zone (1 to 5)")
    duration_minutes: int = Field(..., description="Target duration of the workout in minutes")
    rationale: str = Field(..., description="Detailed explanation of physiological or environmental adjustments")
    scheduled_start_iso: str = Field(default="", description="ISO 8601 string representing when the run is scheduled to begin")
    physiological_focus: str = Field(default="Autonomic baseline assessment", description="Primary physiological factor being evaluated or protected")
    session_slot: str = Field(default="", description="The designated training slot name, e.g., 'Day 1: Speed', 'Day 4 (AM): Recovery Flush'")

class WeeklyScheduleDraft(BaseModel):
    schedule: List[WorkoutDraft] = Field(..., description="List of scheduled workouts for the week")


