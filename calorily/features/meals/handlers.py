from aiohttp import web
from .service import MealService
import traceback
import json


class MealHandlers:
    def __init__(self, meal_service: MealService):
        self.meal_service = meal_service

    async def analyze_meal(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
            user_id = request["user"]["user_id"]

            analysis = await self.meal_service.create_analysis(user_id)

            return web.json_response(
                {"meal_id": analysis.meal_id, "status": analysis.status}
            )
        except Exception:
            traceback.print_exc()
            return web.json_response(
                {"error": "an unexpected error happened"}, status=500
            )

    async def submit_feedback(self, request: web.Request) -> web.Response:
        try:
            meal_id = request.match_info.get("meal_id")
            analysis = await self.meal_service.get_analysis(meal_id)

            if not analysis:
                return web.json_response({"error": "meal not found"}, status=404)

            return web.json_response({"meal_id": meal_id, "status": analysis.status})
        except Exception:
            traceback.print_exc()
            return web.json_response(
                {"error": "an unexpected error happened"}, status=500
            )

    async def websocket_handler(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse()
        await ws.prepare(request)

        user_id = request["user"]["user_id"]

        # Mock sending an analysis complete message
        analysis = await self.meal_service.create_analysis(user_id)
        mock_ingredients = [
            {
                "name": "mock ingredient",
                "amount": 100,
                "carbs": 20,
                "proteins": 10,
                "fats": 5,
            }
        ]

        updated_analysis = await self.meal_service.update_analysis(
            analysis.meal_id, mock_ingredients
        )

        await ws.send_json(
            {
                "meal_id": analysis.meal_id,
                "event": "analysis_complete",
                "data": {"ingredients": mock_ingredients},
            }
        )

        await ws.close()
        return ws
