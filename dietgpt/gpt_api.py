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
                        "text": """Analyze the food image provided and output your best estimation in this structured format. When unsure, make up something plausible. Give the quantities for the portion shown in the picture only.
{
  "type": "Type of the food (Breakfast, Lunch, Dinner, or Snacks)",
  "name": "Name of the food (e.g., Pizza)",
  "ingredients": [
    {
      "name": "Name of the ingredient",
      "amount": "Estimated amount of this ingredient",
      "carbs": Float value representing the carbohydrates in grams (g),
      "proteins": Float value representing the proteins in grams (g),
      "fats": Float value representing the fats in grams (g)
    }
    // Repeat for the most important ingredients
  ]
}""",
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
            output = json.loads(clean_json(message_content))
            return ensure_typing(output)

    except Exception as e:
        return {"error": str(e), "response": await response.text()}


async def send_improve_image_to_gpt_api(
    session, api_key, prev_response, remark, encoded_image
):
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    payload = {
        "model": "gpt-4-vision-preview",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": """You already analyzed the food image provided but made a mistake. Output your best estimation in a structured format. When unsure, make up something plausible.
Previous response:
"""
                        + str(prev_response)
                        + "Remark:\n\""
                        + str(remark)
                        + """\"\nExpected format:
{
  "type": "Type of the food (Breakfast, Lunch, Dinner, or Snacks)",
  "name": "Name of the food (e.g., Pizza)",
  "ingredients": [
    {
      "name": "Name of the ingredient",
      "amount": "Estimated amount of this ingredient",
      "carbs": Float value representing the carbohydrates in grams (g),
      "proteins": Float value representing the proteins in grams (g),
      "fats": Float value representing the fats in grams (g)
    }
    // Repeat for the most important ingredients
  ]
}""",
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

    print(payload)

    try:
        async with session.post(
            "https://api.openai.com/v1/chat/completions", headers=headers, json=payload
        ) as response:
            response_data = await response.json()
            message_content = response_data["choices"][0]["message"]["content"]
            output = json.loads(clean_json(message_content))
            return ensure_typing(output)

    except Exception as e:
        return {"error": str(e), "response": await response.text()}
