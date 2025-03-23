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
from .features.meals.service import MealService
from .features.meals.handlers import MealHandlers
from jwt.algorithms import RSAAlgorithm
import logging
from time import time
from typing import Dict


@middleware
async def jwt_middleware(request: web.Request, handler: Callable) -> web.Response:
    # Skip middleware for non-protected routes
    if (
        request.path in ["/auth/apple", "/auth/dev"]
        or request.path.startswith("/meals/")
        and request.method == "GET"
    ):
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
        self.config = config
        self.apple_bundle_id = config["apple"]["bundle_id"]
        self.apple_keys_cache: Dict[str, dict] = {}
        self.apple_keys_expiry = 0
        self.APPLE_KEYS_TTL = 24 * 60 * 60  # 24 hours in seconds

    async def load_apple_keys(self) -> None:
        """Load Apple's public keys into cache."""
        try:
            async with self.session.get(
                "https://appleid.apple.com/auth/keys"
            ) as response:
                if response.status != 200:
                    logging.error("Failed to fetch Apple public keys")
                    return

                keys = await response.json()
                # Index keys by kid for faster lookup
                self.apple_keys_cache = {key["kid"]: key for key in keys["keys"]}
                self.apple_keys_expiry = time() + self.APPLE_KEYS_TTL
                logging.info("Successfully cached Apple public keys")
        except Exception as e:
            logging.error(f"Error loading Apple public keys: {e}")

    async def get_apple_public_key(self, kid: str) -> Optional[dict]:
        """Get Apple's public key from cache or fetch if needed."""
        current_time = time()

        # Refresh cache if expired or empty
        if current_time > self.apple_keys_expiry or not self.apple_keys_cache:
            await self.load_apple_keys()

        return self.apple_keys_cache.get(kid)

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

            # Decode the token header without verification to get the key ID
            try:
                header = jwt.get_unverified_header(identity_token)
                kid = header["kid"]
            except Exception as e:
                logging.error(f"Error decoding token header: {e}")
                return web.json_response({"error": "invalid token"}, status=400)

            # Get the public key from Apple
            key_data = await self.get_apple_public_key(kid)
            if not key_data:
                return web.json_response(
                    {"error": "unable to verify token"}, status=400
                )

            # Convert the JWK to PEM format
            public_key = RSAAlgorithm.from_jwk(json.dumps(key_data))

            try:
                # Verify and decode the token
                payload = jwt.decode(
                    identity_token,
                    public_key,
                    algorithms=["RS256"],
                    audience=self.apple_bundle_id,
                    issuer="https://appleid.apple.com",
                )
            except jwt.exceptions.InvalidTokenError as e:
                logging.error(f"Token validation failed: {e}")
                return web.json_response({"error": "invalid token"}, status=400)

            # Extract the stable user ID from Apple's sub claim
            user_id = payload["sub"]

            # Log the successful authentication
            logging.info(f"Apple Sign In successful for user: {user_id}")

            # Create our own JWT
            token = self.jwt.encode(
                {"user_id": user_id, "exp": datetime.utcnow() + timedelta(days=7)},
                self.jwt_secret,
                algorithm="HS256",
            )

            return web.json_response({"jwt": token, "user_id": user_id})

        except Exception as e:
            logging.error(f"Unexpected error in create_apple_session: {e}")
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

    async def build_app(self):
        # create db indexes
        app = web.Application(middlewares=[jwt_middleware], client_max_size=100000000)
        app["jwt"] = self.jwt
        app["jwt_secret"] = self.jwt_secret
        app["config"] = self.config

        # Initialize services
        self.meal_service = MealService(
            mongo_uri=self.config["mongodb"]["connection_string"],
            database=self.config["mongodb"]["database"],
            app=app,
        )
        await self.meal_service.initialize()

        self.meal_handlers = MealHandlers(self.meal_service)

        async def close_session(app):
            await self.session.close()

        app.on_cleanup.append(close_session)

        # Load Apple keys at startup
        await self.load_apple_keys()

        # Updated routes
        app.add_routes(
            [
                web.post("/auth/apple", self.create_apple_session),
                web.post("/auth/dev", self.create_dev_session),
                web.post("/meals", self.meal_handlers.submit_meal),
                web.post("/meals/feedback", self.meal_handlers.submit_feedback),
                web.get("/meals/sync", self.meal_handlers.sync_analyses),
                web.get("/meals/{meal_id}", self.meal_handlers.get_meal_analysis),
                web.get("/meals/{meal_id}/image", self.meal_handlers.get_meal_image),
                web.get("/ws", self.meal_handlers.websocket_handler),
                web.delete("/meals/{meal_id}", self.meal_handlers.delete_meal),
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
