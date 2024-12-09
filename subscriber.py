#!/usr/bin/env python3
import asyncio
import aiohttp
import argparse
import json
from datetime import datetime


# local: "ws://localhost:8080/ws"
BACKEND = "ws://localhost:8080/ws"


async def subscribe_to_meals(jwt_token: str):
    """Subscribe to meal analysis updates via WebSocket"""
    url = f"{BACKEND}?token={jwt_token}"

    async with aiohttp.ClientSession() as session:
        try:
            async with session.ws_connect(url) as ws:
                print("Connected to WebSocket server")
                print("Waiting for messages...")

                async for msg in ws:
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        try:
                            data = json.loads(msg.data)
                            timestamp = datetime.fromisoformat(
                                data["data"]["timestamp"]
                            )
                            print("\nReceived message at", timestamp)
                            print(json.dumps(data, indent=2))
                        except Exception as e:
                            print(f"Error parsing message: {e}")
                            print("Raw message:", msg.data)
                    elif msg.type == aiohttp.WSMsgType.ERROR:
                        print(f"WebSocket error: {ws.exception()}")
                        break
                    elif msg.type == aiohttp.WSMsgType.CLOSED:
                        print("WebSocket connection closed")
                        break
        except aiohttp.ClientError as e:
            print(f"Connection error: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Subscribe to Calorily meal analysis updates"
    )
    parser.add_argument("jwt", help="JWT token for authentication")
    args = parser.parse_args()

    try:
        asyncio.run(subscribe_to_meals(args.jwt))
    except KeyboardInterrupt:
        print("\nSubscriber stopped by user")


if __name__ == "__main__":
    main()
