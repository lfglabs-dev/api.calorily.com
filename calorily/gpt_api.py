import aiohttp
import asyncio
import json
from utils import clean_json, ensure_typing


async def send_image_to_gpt_api(session, api_key, encoded_image):
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    payload = {
        "model": "gpt-4-vision-preview",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": """Analyze the food image provided and output your best estimation in this structured format, don't output the unit. When unsure, make up something plausible. Give an estimation of the quantities for the portion shown in the picture only. If impossible, just output the reason in field "error". {"name": "Name of the food (e.g., Pizza)", "ingredients": [{"name": "Name of the ingredient", "amount": "Estimated amount of this ingredient in grams (g)", "carbs": Float value representing the carbohydrates in grams (g), "proteins": Float value representing the proteins in grams (g), "fats": Float value representing the fats in grams (g)}]}""",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{encoded_image}"},
                    },
                ],
            }
        ],
        "max_tokens": 3000,
    }

    try:
        async with session.post(
            "https://api.openai.com/v1/chat/completions", headers=headers, json=payload
        ) as response:
            response_data = await response.json()
            message_content = response_data["choices"][0]["message"]["content"]
            print("ORIGINAL MESSAGE NORMAL:", message_content)
            try:
                output = json.loads(clean_json(message_content))
            except Exception as parsingException:
                return {"error": str(parsingException), "response": message_content}
            print("JSONED MESSAGED:", output)
            ensure_typed = ensure_typing(output)
            print("TYPED MESSAGE:", ensure_typed)
            return ensure_typed

    except Exception as e:
        return {"error": str(e), "response": await response.text()}


async def send_improve_image_to_gpt_api(
    session, api_key, prev_response, remark, encoded_image
):
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    payload = {
        "model": "gpt-4-turbo",
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": """You already analyzed the food image provided but made a mistake. Output your best estimation in a structured format, don't output the units. When unsure, make up something plausible.
Previous response:
"""
                        + str(prev_response)
                        + 'Remark:\n"'
                        + str(remark)
                        + """\"\nExpected format:
{"name": "Name of the food (e.g., Pizza)", "ingredients": [{"name": "Name of the ingredient", "amount": "Estimated amount of this ingredient in grams (g)", "carbs": Float value representing the carbohydrates in grams (g), "proteins": Float value representing the proteins in grams (g), "fats": Float value representing the fats in grams (g)}]}""",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{encoded_image}"},
                    },
                ],
            }
        ],
        "max_tokens": 2500,
    }

    try:
        async with session.post(
            "https://api.openai.com/v1/chat/completions", headers=headers, json=payload
        ) as response:
            response_data = await response.json()
            message_content = response_data["choices"][0]["message"]["content"]
            print("ORIGINAL MESSAGE:", message_content)
            try:
                output = json.loads(clean_json(message_content))
            except Exception as parsingException:
                return {"error": str(parsingException), "response": message_content}
            return ensure_typing(output)

    except Exception as e:
        return {"error": str(e), "response": await response.text()}
