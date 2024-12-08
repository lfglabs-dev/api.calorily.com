from typing import List, Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Ingredient:
    name: str
    amount: float
    carbs: float
    proteins: float
    fats: float


@dataclass
class MealAnalysis:
    meal_id: str
    ingredients: List[Ingredient]
    created_at: datetime
    user_id: str
    status: str = "processing"
