from typing import TypedDict, Optional, List
from datetime import datetime


class Ingredient(TypedDict):
    name: str
    weight: float
    carbs: float
    proteins: float
    fats: float


class AnalysisResult(TypedDict):
    meal_name: str
    ingredients: List[Ingredient]
    timestamp: datetime


class FeedbackEntry(TypedDict):
    feedback: str
    timestamp: datetime


class MealData(TypedDict):
    meal_id: str
    user_id: str
    b64_img: str
    created_at: datetime
    latest_analysis: Optional[AnalysisResult]
    feedback_history: List[FeedbackEntry]
