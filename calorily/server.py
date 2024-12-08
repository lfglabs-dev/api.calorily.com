from aiohttp import web
import aiohttp_cors
import traceback
import aiohttp
from jwt import PyJWT
import uuid
from datetime import datetime, timedelta
import json
from typing import Callable, Optional
from aiohttp.web import middleware
import jwt.exceptions
from features.meals.service import MealService
from features.meals.handlers import MealHandlers


@middleware
async def jwt_middleware(request: web.Request, handler: Callable) -> web.Response:
    # Skip middleware for non-protected routes
    if request.path in ["/auth/apple", "/auth/dev"]:
        return await handler(request)

    # Handle WebSocket authentication differently (token in query params)
    if request.path == "/ws":
        token = request.query.get("token")
        if not token:
            return web.json_response({"error": "unauthorized"}, status=401)
    else:
        # Get token from Authorization header
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return web.json_response({"error": "unauthorized"}, status=401)
        token = auth_header.split(" ")[1]

    try:
        # Verify and decode the token
        payload = request.app["jwt"].decode(
            token, request.app["jwt_secret"], algorithms=["HS256"]
        )
        # Add user info to request
        request["user"] = payload
    except jwt.exceptions.ExpiredSignatureError:
        return web.json_response({"error": "token expired"}, status=401)
    except jwt.exceptions.InvalidTokenError:
        return web.json_response({"error": "invalid token"}, status=401)
    except Exception:
        return web.json_response({"error": "unauthorized"}, status=401)

    return await handler(request)


class WebServer:
    def __init__(self, config) -> None:
        self.api_key = config["openai"]["api_key"]
        self.jwt_secret = config["server"]["jwt_secret"]
        self.dev_mode = config["server"]["dev"]
        self.session = aiohttp.ClientSession()
        self.jwt = PyJWT()

        # Initialize services
        self.meal_service = MealService()
        self.meal_handlers = MealHandlers(self.meal_service)

    async def create_apple_session(self, request):
        try:
            if not request.content_type == "application/json":
                return web.json_response(
                    {"error": "Content-Type must be application/json"}, status=400
                )

            try:
                data = await request.json()
            except json.JSONDecodeError:
                return web.json_response(
                    {"error": "Invalid JSON in request body"}, status=400
                )

            identity_token = data.get("identity_token")
            if not identity_token:
                return web.json_response({"error": "invalid input"}, status=400)

            user_id = str(uuid.uuid4())

            token = self.jwt.encode(
                {"user_id": user_id, "exp": datetime.utcnow() + timedelta(days=7)},
                self.jwt_secret,
                algorithm="HS256",
            )

            return web.json_response({"jwt": token, "user_id": user_id})
        except Exception:
            traceback.print_exc()
            return web.json_response(
                {"error": "an unexpected error happened"}, status=500
            )

    async def create_dev_session(self, request):
        if not self.dev_mode:
            return web.json_response({"error": "dev mode disabled"}, status=403)

        try:
            if not request.content_type == "application/json":
                return web.json_response(
                    {"error": "Content-Type must be application/json"}, status=400
                )

            try:
                data = await request.json()
            except json.JSONDecodeError:
                return web.json_response(
                    {"error": "Invalid JSON in request body"}, status=400
                )

            user_id = data.get("user_id")
            if not user_id:
                return web.json_response({"error": "invalid input"}, status=400)

            token = self.jwt.encode(
                {"user_id": user_id, "exp": datetime.utcnow() + timedelta(days=7)},
                self.jwt_secret,
                algorithm="HS256",
            )

            return web.json_response({"jwt": token, "user_id": user_id})
        except Exception:
            traceback.print_exc()
            return web.json_response(
                {"error": "an unexpected error happened"}, status=500
            )

    def build_app(self):
        app = web.Application(middlewares=[jwt_middleware], client_max_size=100000000)

        app["jwt"] = self.jwt
        app["jwt_secret"] = self.jwt_secret

        async def close_session(app):
            await self.session.close()

        app.on_cleanup.append(close_session)

        # Updated routes
        app.add_routes(
            [
                web.post("/auth/apple", self.create_apple_session),
                web.post("/auth/dev", self.create_dev_session),
                web.post("/meals", self.meal_handlers.analyze_meal),
                web.post("/meals/feedback", self.meal_handlers.submit_feedback),
                web.get("/ws", self.meal_handlers.websocket_handler),
            ]
        )

        cors = aiohttp_cors.setup(
            app,
            defaults={
                "*": aiohttp_cors.ResourceOptions(
                    allow_credentials=True,
                    expose_headers="*",
                    allow_headers="*",
                )
            },
        )
        for route in list(app.router.routes()):
            cors.add(route)

        return app
