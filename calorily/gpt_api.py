import aiohttp
import json
from typing import TypedDict, Dict, Any, Optional, Union
from .utils import clean_json, ensure_typing
from .features.meals.models import MealData


class AnalysisResponse(TypedDict):
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
        prompt = (
            "Analyze this food image and provide a detailed breakdown in JSON format."
        )

    prompt += """
Respond with a JSON object in this format:
{
    "ingredients": [
        {
            "name": "ingredient name",
            "amount": number (grams),
            "carbs": number (grams),
            "proteins": number (grams),
            "fats": number (grams)
        }
    ]
}

Requirements:
- List each visible ingredient
- Estimate amounts in grams
- Calculate macronutrients in grams
- Be precise with numbers
- Don't include units
- Make reasonable estimates when unsure
- Respond only with valid JSON"""

    # Prepare API request
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
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

    try:
        async with session.post(
            "https://api.openai.com/v1/chat/completions", headers=headers, json=payload
        ) as response:
            response_data = await response.json()
            message_content = response_data["choices"][0]["message"]["content"]
            print("GPT Analysis Response:", message_content)

            try:
                output = json.loads(clean_json(message_content))
                if "error" in output:
                    return {"error": "model_error", "response": output["error"]}

                return ensure_typing(output)

            except Exception as parsing_error:
                return {"error": str(parsing_error), "response": message_content}

    except Exception as e:
        return {"error": str(e), "response": "API call failed"}
