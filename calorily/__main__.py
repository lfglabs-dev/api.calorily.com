from server import WebServer
from aiohttp import web
from typing import Any
import toml
import asyncio
import os


async def start_server(config: dict[str, Any]):
    app = WebServer(config).build_app()
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, port=config["server"]["port"]).start()
    stop_event = asyncio.Event()
    await stop_event.wait()


async def main():
    config = toml.load("config.toml")
    server_task = start_server(config)
    await asyncio.gather(server_task)


asyncio.run(main())
