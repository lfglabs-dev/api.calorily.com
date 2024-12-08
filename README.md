# Calorily API Documentation

API endpoint: `api.calorily.com`

## Authentication
All authenticated endpoints require a JWT token in the Authorization header:
```
Authorization: Bearer <jwt_token>
```

## Endpoints

### 1. Create Session (Apple Auth)
Creates an authenticated session using Apple Sign In.

**Endpoint:** `/auth/apple`  
**Method:** `POST`  

**Request Body:**
```json
{
    "identity_token": "apple_identity_token"
}
```

**Response:**
```json
{
    "jwt": "string",
    "user_id": "string"
}
```

### 2. Create Dev Session
Creates an authenticated session for testing (dev enabled in config only).

**Endpoint:** `/auth/dev`  
**Method:** `POST`  

**Request Body:**
```json
{
    "user_id": "string"
}
```

**Response:**
```json
{
    "jwt": "string",
    "user_id": "string"
}
```

### 3. Analyze Food Image
Analyzes a food image and returns nutritional information.

**Endpoint:** `/meals`  
**Method:** `POST`  
**Authentication:** Required  

**Request Body:**
```json
{
    "meal_id": "uuid",
    "b64_img": "base64_encoded_image_string"
}
```

**Response:**
```json
{
    "meal_id": "uuid",
    "status": "processing"
}
```

### 4. Submit Meal Feedback
Submits user feedback for a specific meal analysis.

**Endpoint:** `/meals/feedback`  
**Method:** `POST`  
**Authentication:** Required

**Request Body:**
```json
{
    "feedback": "string"
}
```

**Response:**
```json
{
    "meal_id": "uuid",
    "status": "processing"
}
```

### 5. WebSocket Updates
Connects to WebSocket to receive real-time updates for meal analyses.

**Endpoint:** `/ws`  
**Protocol:** `WSS`  
**Authentication:** Required (JWT as query parameter)

**Connection URL:**
```
wss://api.calorily.com/ws?token=<jwt_token>
```

**Message Format (Server → Client):**
```json
{
    "meal_id": "uuid",
    "event": "analysis_complete|feedback_processed",
    "data": {
        "ingredients": [
            {
                "name": "string",
                "amount": "number",
                "carbs": "number",
                "proteins": "number",
                "fats": "number"
            }
        ]
    }
}
```

## CORS
The API supports Cross-Origin Resource Sharing (CORS) with all origins (*) allowed.

## Notes
- All images must be base64 encoded
- The API uses GPT Vision for analysis
- Response times may vary based on image complexity
- WebSocket connections will automatically close after 24 hours of inactivity
- All timestamps are in ISO 8601 format
