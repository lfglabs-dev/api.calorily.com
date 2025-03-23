from typing import Optional, Dict
from .models import Ingredient, AnalysisResult, FeedbackEntry, MealData
from datetime import datetime
from motor.motor_asyncio import AsyncIOMotorClient
from motor.core import AgnosticDatabase, AgnosticCollection
import asyncio
from aiohttp import web
import json
import aiohttp
from ...gpt_api import analyze_meal
import traceback
import base64
from bson.objectid import ObjectId
import re
from PIL import Image
import io
import time
from functools import lru_cache


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
        # Create an in-memory cache for processed images
        self._image_cache = {}

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
                    "meal_name": latest_analysis["meal_name"],
                    "ingredients": latest_analysis["ingredients"],
                    "timestamp": latest_analysis["timestamp"],
                }
                if latest_analysis
                else None
            ),
            "feedback_history": feedback_history,
        }

    async def add_analysis(
        self,
        meal_id: str,
        meal_name: str,
        ingredients: list[Ingredient],
        timestamp: datetime = None,
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
                "meal_name": meal_name,
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
        """Start an async task to analyze the meal image."""

        async def analyze_task():
            try:
                # Get the API key from the app config
                api_key = self.app["config"]["openai"]["api_key"]

                async with aiohttp.ClientSession() as session:
                    # Send image to Vision API
                    result = await analyze_meal(session, api_key, meal_data)

                    if result is None:
                        print(
                            f"Analysis error: GPT API returned None for meal {meal_data['meal_id']}"
                        )
                        await self.notify_user(
                            meal_data["user_id"],
                            {
                                "meal_id": meal_data["meal_id"],
                                "event": "analysis_failed",
                                "error": "GPT API returned no response",
                            },
                        )
                        return

                    if "error" in result:
                        error_msg = f"Analysis error for meal {meal_data['meal_id']}: {result['error']}"
                        print(error_msg)
                        await self.notify_user(
                            meal_data["user_id"],
                            {
                                "meal_id": meal_data["meal_id"],
                                "event": "analysis_failed",
                                "error": result["error"],
                            },
                        )
                        return

                    timestamp = datetime.utcnow()
                    print(
                        f"Got analysis result for meal {meal_data['meal_id']}: {result}"
                    )

                    # Send notification first
                    notification = {
                        "meal_id": meal_data["meal_id"],
                        "event": "analysis_complete",
                        "data": {
                            "meal_name": result["meal_name"],
                            "ingredients": result["ingredients"],
                            "timestamp": timestamp.isoformat(),
                        },
                    }
                    print(f"Sending notification: {notification}")
                    await self.notify_user(meal_data["user_id"], notification)

                    # Then store in database
                    print(f"Storing analysis in database...")
                    stored = await self.add_analysis(
                        meal_data["meal_id"],
                        result["meal_name"],
                        result["ingredients"],
                        timestamp,
                    )
                    print(f"Analysis stored: {stored}")

            except Exception as e:
                error_msg = (
                    f"Analysis task error for meal {meal_data['meal_id']}: {str(e)}"
                )
                print(error_msg)
                traceback.print_exc()
                await self.notify_user(
                    meal_data["user_id"],
                    {
                        "meal_id": meal_data["meal_id"],
                        "event": "analysis_failed",
                        "error": "Internal server error during analysis",
                    },
                )

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
                    "meal_name": "$latest_analysis.meal_name",
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

    async def get_meal_analysis(self, meal_id: str) -> dict:
        """Get the latest analysis for a specific meal."""
        analysis = await self.analysis.find_one(
            {"meal_id": meal_id}, sort=[("timestamp", -1)]
        )

        if not analysis:
            return None

        # Remove MongoDB _id field and convert datetime to ISO string
        analysis.pop("_id", None)
        if "timestamp" in analysis:
            analysis["timestamp"] = analysis["timestamp"].isoformat()

        # Ensure all required fields are present
        expected_fields = {"meal_id", "meal_name", "ingredients", "timestamp"}
        if not all(field in analysis for field in expected_fields):
            print(f"Warning: Analysis missing fields. Found: {set(analysis.keys())}")

        return analysis

    @lru_cache(maxsize=100)  # Cache up to 100 different image variations
    def _get_cache_key(
        self, meal_id: str, max_size: Optional[int], quality: int
    ) -> str:
        return f"{meal_id}_{max_size}_{quality}"

    async def get_meal_image(
        self,
        meal_id: str,
        max_size: Optional[int] = None,
        quality: Optional[int] = None,
    ) -> tuple[bytes, str]:
        """Get the meal image and optionally resize/compress it."""
        start_time = time.time()
        cache_key = self._get_cache_key(meal_id, max_size, quality)

        # Debug MongoDB query
        print(f"[MongoDB Debug] Checking indexes...")
        indexes = await self.meals.index_information()
        print(f"[MongoDB Debug] Available indexes: {indexes}")

        # Explain the query
        explanation = await self.meals.find(
            {"meal_id": meal_id}, projection={"b64_img": 1, "_id": 0}
        ).explain()
        print(f"[MongoDB Debug] Query explanation: {explanation}")

        # Fetch only the b64_img field from DB
        meal = await self.meals.find_one(
            {"meal_id": meal_id}, projection={"b64_img": 1, "_id": 0}
        )
        db_time = time.time() - start_time
        print(f"[Image Timing] DB fetch: {db_time:.3f}s")

        if not meal or not meal.get("b64_img"):
            return None, None

        # Extract format and header
        format_start = time.time()
        b64_img = meal["b64_img"]
        format_match = re.match(r"data:image/(\w+);base64,", b64_img)

        if format_match:
            image_format = format_match.group(1)
            b64_img = b64_img.split(",")[1]
        else:
            image_format = "jpeg"
        format_time = time.time() - format_start
        print(f"[Image Timing] Format detection: {format_time:.3f}s")

        try:
            # Decode base64
            decode_start = time.time()
            image_bytes = base64.b64decode(b64_img)
            decode_time = time.time() - decode_start
            print(f"[Image Timing] Base64 decode: {decode_time:.3f}s")

            # Only process image if resize or quality is requested
            if max_size is not None or quality is not None:
                # Load image
                load_start = time.time()
                image = Image.open(io.BytesIO(image_bytes))
                load_time = time.time() - load_start
                print(f"[Image Timing] Image load: {load_time:.3f}s")

                # Resize if needed
                resize_start = time.time()
                if max_size:
                    original_size = max(image.size)
                    if original_size > max_size:
                        ratio = max_size / original_size
                        new_size = tuple(int(dim * ratio) for dim in image.size)
                        image = image.resize(new_size, Image.Resampling.LANCZOS)
                resize_time = time.time() - resize_start
                print(f"[Image Timing] Resize: {resize_time:.3f}s")

                # Save with quality if specified
                save_start = time.time()
                output = io.BytesIO()
                save_params = {"optimize": True}
                if quality is not None:
                    save_params["quality"] = quality

                if image_format.lower() in ("jpg", "jpeg"):
                    image = image.convert("RGB")
                    image.save(output, format="JPEG", **save_params)
                else:
                    image.save(output, format="PNG", optimize=True)
                output.seek(0)
                save_time = time.time() - save_start
                print(f"[Image Timing] Save/compress: {save_time:.3f}s")

                image_bytes = output.getvalue()

            total_time = time.time() - start_time
            print(f"[Image Timing] Total processing: {total_time:.3f}s")

            return image_bytes, f"image/{image_format}"

        except Exception as e:
            print(f"Error processing image: {e}")
            return None, None

    async def delete_meal(self, meal_id: str) -> bool:
        """Delete a meal and all associated data (analysis, feedback)"""
        try:
            # Delete from all collections
            meal_result = await self.meals.delete_one({"meal_id": meal_id})
            await self.analysis.delete_many({"meal_id": meal_id})
            await self.feedback.delete_many({"meal_id": meal_id})

            # Clear from image cache if present
            for key in list(self._image_cache.keys()):
                if key.startswith(f"{meal_id}_"):
                    self._image_cache.pop(key, None)

            # Return True if the meal was found and deleted
            return meal_result.deleted_count > 0

        except Exception as e:
            print(f"Error deleting meal {meal_id}: {e}")
            traceback.print_exc()
            return False
