import aiohttp
import json
from typing import TypedDict, Dict, Any, Optional, Union
from .utils import clean_json, ensure_typing
from .features.meals.models import MealData
import traceback


class AnalysisResponse(TypedDict):
    meal_name: str
    ingredients: list[Dict[str, Any]]


class AnalysisError(TypedDict):
    error: str
    response: str


async def analyze_meal(
    session: aiohttp.ClientSession,
    api_key: str,
    meal_data: MealData,
) -> Union[AnalysisResponse, AnalysisError]:
    """Analyze a meal image using GPT-4 Vision, with optional feedback consideration"""
    print(f"[GPT Debug] Starting analysis for meal {meal_data['meal_id']}")
    print(f"[GPT Debug] Has feedback: {bool(meal_data.get('feedback_history'))}")

    # Build the prompt
    try:
        # Determine if this is a feedback-based analysis
        has_feedback = (
            meal_data.get("feedback_history") and len(meal_data["feedback_history"]) > 0
        )
        latest_feedback = (
            meal_data["feedback_history"][-1]["feedback"] if has_feedback else None
        )
        previous_analysis = meal_data.get("latest_analysis")

        # Build the appropriate prompt
        if has_feedback and previous_analysis:
            print(f"[GPT Debug] Using feedback: {latest_feedback}")
            print(f"[GPT Debug] Previous analysis: {previous_analysis}")
            # Convert datetime to string in previous analysis
            serializable_analysis = {
                "ingredients": previous_analysis["ingredients"],
                "timestamp": previous_analysis["timestamp"].isoformat(),
            }
            prompt = f"""You previously analyzed this food image but received feedback. Please provide an updated analysis in JSON format.
Previous analysis: {json.dumps(serializable_analysis)}
Feedback: "{latest_feedback}"
"""
        else:
            prompt = "Analyze this food image and provide a detailed breakdown in JSON format."
        print(f"[GPT Debug] Using prompt: {prompt}")

        # Prepare API request
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        payload = {
            "model": "gpt-4o",
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{meal_data['b64_img']}",
                                "detail": "high",
                            },
                        },
                    ],
                }
            ],
            "max_tokens": 2500,
        }
        print(f"[GPT Debug] Sending request to OpenAI API...")

        async with session.post(
            "https://api.openai.com/v1/chat/completions", headers=headers, json=payload
        ) as response:
            if response.status != 200:
                error_text = await response.text()
                print(f"[GPT Debug] OpenAI API Error: Status {response.status}")
                print(f"[GPT Debug] Error response: {error_text}")
                return {
                    "error": f"API Error {response.status}",
                    "response": f"OpenAI API error: {error_text}",
                }

            response_data = await response.json()
            print(f"[GPT Debug] Got response from OpenAI: {response_data}")

            if "choices" not in response_data:
                print("[GPT Debug] No choices in response")
                return {"error": "Invalid API response", "response": str(response_data)}

            message_content = response_data["choices"][0]["message"]["content"]
            print(f"[GPT Debug] Message content: {message_content}")

            try:
                output = json.loads(clean_json(message_content))
                print(f"[GPT Debug] Parsed JSON output: {output}")

                if "error" in output:
                    return {"error": "model_error", "response": output["error"]}

                # Validate required fields
                if "meal_name" not in output or "ingredients" not in output:
                    print("[GPT Debug] Missing required fields in output")
                    return {
                        "error": "Missing required fields",
                        "response": message_content,
                    }

                return ensure_typing(output)

            except Exception as parsing_error:
                print(f"[GPT Debug] JSON parsing error: {parsing_error}")
                return {"error": str(parsing_error), "response": message_content}

    except Exception as e:
        print(f"[GPT Debug] Unexpected error: {e}")
        traceback.print_exc()
        return {"error": str(e), "response": "API call failed"}
