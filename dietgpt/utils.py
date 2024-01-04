import re


def clean_json(json_string):
    # Remove single-line comments
    cleaned_string = re.sub(r"//.*", "", json_string)

    # Extract JSON object
    match = re.search(r"\{.*\}", cleaned_string, re.DOTALL)
    return match.group().strip() if match else ""


def calculate_calories(carbs, proteins, fats):
    return (carbs * 4) + (proteins * 4) + (fats * 9)


def ensure_typing(data):
    if "ingredients" in data:
        for ingredient in data["ingredients"]:
            ingredient["carbs"] = extract_float(ingredient.get("carbs", 0))
            ingredient["proteins"] = extract_float(ingredient.get("proteins", 0))
            ingredient["fats"] = extract_float(ingredient.get("fats", 0))
    return data


def extract_float(value):
    if isinstance(value, float):
        return value
    if isinstance(value, str):
        match = re.search(r"\d+(\.\d+)?", value)
        return float(match.group()) if match else 0.0
    return 0.0
