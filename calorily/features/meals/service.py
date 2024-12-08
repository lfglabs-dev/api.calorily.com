from typing import Optional, Dict
from .models import Ingredient, AnalysisResult, FeedbackEntry, MealData
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from motor.core import AgnosticDatabase, AgnosticCollection
import asyncio
from aiohttp import web
import json
import aiohttp


class MealService:
    def __init__(self, mongo_uri: str, database: str, app: web.Application = None):
        # Use Motor for async MongoDB operations
        self.client = AsyncIOMotorClient(mongo_uri)
        self.db: AgnosticDatabase = self.client[database]
        self.meals: AgnosticCollection = self.db.meals
        self.analysis: AgnosticCollection = self.db.analysis
        self.feedback: AgnosticCollection = self.db.feedback
        # WebSocket connections mapped by user_id
        self.ws_connections: Dict[str, set[web.WebSocketResponse]] = {}
        self.app = app

    async def register_ws_connection(
        self, user_id: str, ws: web.WebSocketResponse
    ) -> None:
        """Register a new WebSocket connection for a user"""
        if user_id not in self.ws_connections:
            self.ws_connections[user_id] = set()
        self.ws_connections[user_id].add(ws)

    async def unregister_ws_connection(
        self, user_id: str, ws: web.WebSocketResponse
    ) -> None:
        """Unregister a WebSocket connection for a user"""
        if user_id in self.ws_connections:
            self.ws_connections[user_id].discard(ws)
            if not self.ws_connections[user_id]:
                del self.ws_connections[user_id]

    async def notify_user(self, user_id: str, message: dict) -> None:
        """Send a notification to all WebSocket connections for a user"""
        if user_id not in self.ws_connections:
            return

        dead_connections = set()
        for ws in self.ws_connections[user_id]:
            try:
                await ws.send_json(message)
            except Exception:
                dead_connections.add(ws)

        # Clean up dead connections
        for ws in dead_connections:
            await self.unregister_ws_connection(user_id, ws)

    async def initialize(self):
        """Initialize database settings like indexes"""
        # Create indexes
        await self.meals.create_index("meal_id", unique=True)
        await self.meals.create_index("user_id")  # For user-specific queries
        await self.analysis.create_index(
            [("meal_id", 1), ("timestamp", -1)]
        )  # For efficient latest analysis lookup
        await self.feedback.create_index(
            [("meal_id", 1), ("timestamp", -1)]
        )  # For efficient feedback lookup

    async def create_meal(
        self, meal_id: str, user_id: str, b64_img: str
    ) -> Optional[str]:
        """Create a new meal entry with the provided image. Returns None if meal_id already exists."""
        try:
            await self.meals.insert_one(
                {
                    "meal_id": meal_id,
                    "user_id": user_id,
                    "b64_img": b64_img,
                    "created_at": datetime.utcnow(),
                }
            )
            return meal_id
        except Exception:  # Duplicate key error
            return None

    async def fetch_meal(self, meal_id: str) -> Optional[MealData]:
        """Fetch comprehensive meal data including image, latest analysis and feedback history"""
        # Get the meal document
        meal_doc = await self.meals.find_one({"meal_id": meal_id})
        if not meal_doc:
            return None

        # Get the latest analysis
        latest_analysis = await self.analysis.find_one(
            {"meal_id": meal_id}, sort=[("timestamp", -1)]
        )

        # Get all feedback entries
        feedback_cursor = self.feedback.find(
            {"meal_id": meal_id}, sort=[("timestamp", -1)]
        )
        feedback_history = [
            {"feedback": doc["feedback"], "timestamp": doc["timestamp"]}
            async for doc in feedback_cursor
        ]

        return {
            "meal_id": meal_doc["meal_id"],
            "user_id": meal_doc["user_id"],
            "b64_img": meal_doc["b64_img"],
            "created_at": meal_doc["created_at"],
            "latest_analysis": (
                {
                    "ingredients": latest_analysis["ingredients"],
                    "timestamp": latest_analysis["timestamp"],
                }
                if latest_analysis
                else None
            ),
            "feedback_history": feedback_history,
        }

    async def add_analysis(
        self, meal_id: str, ingredients: list[Ingredient], timestamp: datetime = None
    ) -> bool:
        """Add a new analysis for a meal"""
        # Verify meal exists
        meal = await self.meals.find_one({"meal_id": meal_id})
        if not meal:
            return False

        if timestamp is None:
            timestamp = datetime.utcnow()

        # Insert the analysis
        await self.analysis.insert_one(
            {
                "meal_id": meal_id,
                "ingredients": ingredients,
                "timestamp": timestamp,
            }
        )
        return True

    async def add_feedback(self, meal_id: str, feedback: str) -> bool:
        """Add feedback for a meal"""
        # Verify meal exists
        meal_exists = await self.meals.find_one({"meal_id": meal_id}) is not None
        if not meal_exists:
            return False

        await self.feedback.insert_one(
            {"meal_id": meal_id, "feedback": feedback, "timestamp": datetime.utcnow()}
        )
        return True

    async def request_analysis(self, meal_data: MealData) -> None:
        """Start an async task to analyze the meal image (mock implementation)."""

        async def analyze_task():
            try:
                # Mock analysis result
                mock_ingredients = [
                    {
                        "name": "mock ingredient",
                        "amount": 100,
                        "carbs": 20,
                        "proteins": 10,
                        "fats": 5,
                    }
                ]

                timestamp = datetime.utcnow()

                # Send notification first
                notification = {
                    "meal_id": meal_data["meal_id"],
                    "event": "analysis_complete",
                    "data": {
                        "ingredients": mock_ingredients,
                        "timestamp": timestamp.isoformat(),
                    },
                }
                await self.notify_user(meal_data["user_id"], notification)

                # Then store in database
                await self.add_analysis(
                    meal_data["meal_id"], mock_ingredients, timestamp
                )

            except Exception as e:
                print(f"Analysis task error: {str(e)}")

        # Start the analysis task without awaiting it
        asyncio.create_task(analyze_task())

    async def fetch_analyses_since(self, user_id: str, since: datetime) -> list[dict]:
        """Fetch all meal analyses for a user that have been updated since the given timestamp"""
        # First get all meals for this user
        user_meals = self.meals.find({"user_id": user_id})
        meal_ids = [meal["meal_id"] async for meal in user_meals]

        if not meal_ids:
            return []

        # Then get the latest analysis for each meal that's newer than since
        pipeline = [
            {"$match": {"meal_id": {"$in": meal_ids}, "timestamp": {"$gt": since}}},
            {
                # Group by meal_id and get the latest analysis
                "$group": {"_id": "$meal_id", "latest_analysis": {"$max": "$$ROOT"}}
            },
            {
                # Reshape the output
                "$project": {
                    "_id": 0,
                    "meal_id": "$_id",
                    "ingredients": "$latest_analysis.ingredients",
                    "timestamp": "$latest_analysis.timestamp",
                }
            },
        ]

        cursor = self.analysis.aggregate(pipeline)
        analyses = [doc async for doc in cursor]

        # Convert datetime to ISO format string
        for analysis in analyses:
            analysis["timestamp"] = analysis["timestamp"].isoformat()

        return analyses
