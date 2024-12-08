from typing import Optional
from .models import MealAnalysis, Ingredient
import uuid
from datetime import datetime


class MealService:
    def __init__(self):
        # In a real app, this would be a database
        self.analyses = {}

    async def create_analysis(self, user_id: str) -> MealAnalysis:
        meal_id = str(uuid.uuid4())
        analysis = MealAnalysis(
            meal_id=meal_id,
            ingredients=[],
            created_at=datetime.utcnow(),
            user_id=user_id,
        )
        self.analyses[meal_id] = analysis
        return analysis

    async def get_analysis(self, meal_id: str) -> Optional[MealAnalysis]:
        return self.analyses.get(meal_id)

    async def update_analysis(
        self, meal_id: str, ingredients: list[Ingredient]
    ) -> Optional[MealAnalysis]:
        if meal_id not in self.analyses:
            return None

        analysis = self.analyses[meal_id]
        analysis.ingredients = ingredients
        analysis.status = "completed"
        return analysis
