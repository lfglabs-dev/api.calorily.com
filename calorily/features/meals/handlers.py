from aiohttp import web
from ..meals.service import MealService
from datetime import datetime
import traceback
import uuid


class MealHandlers:
    def __init__(self, meal_service: MealService):
        self.meal_service = meal_service

    async def submit_meal(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            user_id = request["user"]["user_id"]
            b64_img = data.get("b64_img")
            meal_id = data.get("meal_id", str(uuid.uuid4()))

            if not b64_img:
                return web.json_response({"error": "b64_img is required"}, status=400)

            result = await self.meal_service.create_meal(meal_id, user_id, b64_img)

            if not result:
                return web.json_response({"error": "meal already exists"}, status=409)

            # Create MealData for analysis request
            meal_data = {
                "meal_id": meal_id,
                "user_id": user_id,
                "b64_img": b64_img,
                "created_at": datetime.utcnow(),
                "latest_analysis": None,
                "feedback_history": [],
            }

            # Start analysis task
            await self.meal_service.request_analysis(meal_data)

            return web.json_response({"meal_id": meal_id, "status": "processing"})

        except Exception:
            traceback.print_exc()
            return web.json_response(
                {"error": "an unexpected error occurred"}, status=500
            )

    async def submit_feedback(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            meal_id = data.get("meal_id")
            feedback_text = data.get("feedback")

            if not meal_id:
                return web.json_response({"error": "meal_id is required"}, status=400)

            if not feedback_text:
                return web.json_response({"error": "feedback is required"}, status=400)

            # First fetch the meal to ensure it exists
            meal_data = await self.meal_service.fetch_meal(meal_id)
            if not meal_data:
                return web.json_response({"error": "meal not found"}, status=404)

            # Add the feedback
            success = await self.meal_service.add_feedback(meal_id, feedback_text)
            if not success:
                return web.json_response(
                    {"error": "failed to add feedback"}, status=500
                )

            # Add new feedback to meal_data optimistically
            meal_data["feedback_history"].insert(
                0, {"feedback": feedback_text, "timestamp": datetime.utcnow()}
            )

            # Request a new analysis with updated feedback
            await self.meal_service.request_analysis(meal_data)

            return web.json_response({"meal_id": meal_id, "status": "processing"})

        except Exception:
            traceback.print_exc()
            return web.json_response(
                {"error": "an unexpected error occurred"}, status=500
            )

    async def websocket_handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        user_id = request["user"]["user_id"]
        await self.meal_service.register_ws_connection(user_id, ws)

        try:
            async for msg in ws:
                if msg.type == web.WSMsgType.ERROR:
                    print(
                        f"WebSocket connection closed with exception {ws.exception()}"
                    )
        finally:
            await self.meal_service.unregister_ws_connection(user_id, ws)

        return ws

    async def sync_analyses(self, request: web.Request) -> web.Response:
        try:
            # Get since parameter from query string
            since_str = request.query.get("since")
            if not since_str:
                return web.json_response(
                    {"error": "since parameter is required"}, status=400
                )

            try:
                since = datetime.fromisoformat(since_str.replace("Z", "+00:00"))
            except ValueError:
                return web.json_response(
                    {"error": "invalid timestamp format, use ISO 8601"}, status=400
                )

            user_id = request["user"]["user_id"]
            analyses = await self.meal_service.fetch_analyses_since(user_id, since)

            return web.json_response({"analyses": analyses})

        except Exception:
            traceback.print_exc()
            return web.json_response(
                {"error": "an unexpected error occurred"}, status=500
            )
