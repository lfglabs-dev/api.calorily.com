import re


def clean_json(json_string):
    # Remove single-line comments
    cleaned_string = re.sub(r"//.*", "", json_string)

    # Extract JSON object
    match = re.search(r"\{.*\}", cleaned_string, re.DOTALL)
    return match.group().strip() if match else ""


def extract_float(s):
    match = re.search(r"[-+]?\d*\.\d+|\d+", s)
    return float(match.group()) if match else None


def calculate_calories(carbs, proteins, fats):
    return (carbs * 4) + (proteins * 4) + (fats * 9)
