from aiohttp import web
import aiohttp_cors
import traceback
import aiohttp
from gpt_api import send_image_to_gpt_api


class WebServer:
    def __init__(self, config) -> None:
        self.api_key = config["openai"]["api_key"]
        self.session = aiohttp.ClientSession()

    async def food_data(self, request):
        data = await request.json()
        base64_image = data.get("b64_img", None)
        if not base64_image:
            return web.json_response({"error": "invalid input or empty b64_img"})

        try:
            # Use the shared session
            food_data = await send_image_to_gpt_api(
                self.session, self.api_key, base64_image
            )
            return web.json_response(food_data)

        except Exception:
            traceback.print_exc()
            return web.json_response({"error": "an unexpected error happened"})

    def build_app(self):
        app = web.Application(client_max_size=100000000)

        # Add a cleanup context for closing the session on shutdown
        async def close_session(app):
            await self.session.close()

        app.on_cleanup.append(close_session)

        app.add_routes(
            [
                web.post("/food_data", self.food_data),
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
