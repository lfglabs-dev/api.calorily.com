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

    # Determine if this is a feedback-based analysis
    has_feedback = (
        meal_data.get("feedback_history") and len(meal_data["feedback_history"]) > 0
    )
    latest_feedback = (
        meal_data["feedback_history"][-1]["feedback"] if has_feedback else None
    )

    # Build the appropriate prompt
    if has_feedback:
        print(f"[GPT Debug] Using feedback: {latest_feedback}")
        prompt = f"""You are analyzing a food image. The previous analysis received feedback indicating it might be incorrect.

User feedback states: "{latest_feedback}"

Please provide a new analysis, taking this feedback into account. If this is not a food image, respond with an error message.
Your response must be a valid JSON object matching the format below.
"""
    else:
        prompt = """You are analyzing a food image. Please identify the meal and its ingredients. If this is not a food image, respond with an error message.
Your response must be a valid JSON object matching the format below."""

    prompt += """
Required JSON format:
{
    "meal_name": "Short name (2-3 words max)",
    "ingredients": [
        {
            "name": "Ingredient name",
            "weight": 0.0,
            "carbs": 0.0,
            "proteins": 0.0,
            "fats": 0.0
        }
    ]
}

Alternative format for non-food images or errors:
{
    "error": "Clear explanation of why analysis cannot be performed"
}

Important requirements:
1. Always respond with valid JSON
2. Keep meal_name very short (2-3 words maximum)
3. List all visible ingredients
4. All numbers must be floating point (e.g., 100.0 not 100)
5. Weight in grams
6. Macronutrients in grams with one decimal
7. Make reasonable estimates if unsure
8. Never include units in the numbers
9. Never include additional fields or explanations outside the JSON"""

    print(f"[GPT Debug] Using prompt: {prompt}")

    # Prepare API request (Responses API)
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    payload = {
        "model": "gpt-5",
        "text": {"format": {"type": "json_object"}},
        "reasoning": {"effort": "minimal"},
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": prompt},
                    {
                        "type": "input_image",
                        "image_url": f"data:image/jpeg;base64,{meal_data['b64_img']}",
                    },
                ],
            }
        ],
        # "max_output_tokens": 2500,
    }
    print(f"[GPT Debug] Sending request to OpenAI Responses API...")

    try:
        async with session.post(
            "https://api.openai.com/v1/responses", headers=headers, json=payload
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
            print(
                f"[GPT Debug] Got response from OpenAI Responses API: {response_data}"
            )

            # Extract assistant text from Responses API
            if "output" not in response_data:
                print("[GPT Debug] No output in response")
                return {"error": "Invalid API response", "response": str(response_data)}

            def extract_output_text(data: Dict[str, Any]) -> Optional[str]:
                try:
                    output_items = data.get("output") or []
                    for item in output_items:
                        if (
                            item.get("type") == "message"
                            and item.get("role") == "assistant"
                        ):
                            content_list = item.get("content") or []
                            texts: list[str] = []
                            for c in content_list:
                                if c.get("type") == "output_text" and isinstance(
                                    c.get("text"), str
                                ):
                                    texts.append(c["text"])
                            if texts:
                                return "".join(texts)
                    # Fallback: sometimes models put text directly at top-level convenience fields (SDKs), but
                    # in raw HTTP it's usually within output -> message -> content
                    return None
                except Exception:
                    return None

            message_content = extract_output_text(response_data)
            print(f"[GPT Debug] Message content: {message_content}")

            # Check for None content or refusal-like responses
            if message_content is None:
                # Try to surface any error field if present
                if "error" in response_data and isinstance(
                    response_data["error"], dict
                ):
                    refusal_text = response_data["error"].get(
                        "message", "No response from model"
                    )
                else:
                    refusal_text = "No response from model"
                print(f"[GPT Debug] Model returned no assistant text: {refusal_text}")
                return {
                    "error": "Model returned no assistant text",
                    "response": refusal_text,
                }

            try:
                output = json.loads(clean_json(message_content))
                print(f"[GPT Debug] Parsed JSON output: {output}")

                # Check if the model returned an error
                if "error" in output:
                    return {"error": "analysis_error", "response": output["error"]}

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
