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

### 3. Register Meal
Registers a new meal and starts an asynchronous analysis. The analysis results will be sent through the WebSocket connection.

**Endpoint:** `/meals`  
**Method:** `POST`  
**Authentication:** Required  

**Request Body:**
```json
{
    "meal_id": "uuid",  // Optional, will be generated if not provided
    "b64_img": "base64_encoded_image_string"
}
```

**Response:**
```json
{
    "meal_id": "uuid",
    "status": "processing"  // Analysis will be sent through WebSocket
}
```

### 4. Submit Meal Feedback
Submits feedback for a meal and triggers a new analysis. The new analysis results will be sent through the WebSocket connection.

**Endpoint:** `/meals/feedback`  
**Method:** `POST`  
**Authentication:** Required

**Request Body:**
```json
{
    "meal_id": "uuid",
    "feedback": "string"
}
```

**Response:**
```json
{
    "meal_id": "uuid",
    "status": "processing"  // New analysis will be sent through WebSocket
}
```

### 5. Sync Meal Analyses
Get the latest analysis for each meal that has been updated since a given timestamp.

**Endpoint:** `/meals/sync`  
**Method:** `GET`  
**Authentication:** Required

**Query Parameters:**
```
since=2024-01-20T15:30:45.123Z  // ISO 8601 timestamp
```

**Response:**
```json
{
    "analyses": [
        {
            "meal_id": "uuid",
            "meal_name": "string",
            "ingredients": [
                {
                    "name": "string",
                    "amount": "number",
                    "carbs": "number",
                    "proteins": "number",
                    "fats": "number"
                }
            ],
            "timestamp": "datetime"
        }
    ]
}
```

### 6. WebSocket Updates
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
    "event": "analysis_complete",
    "data": {
        "meal_name": "string",
        "ingredients": [
            {
                "name": "string",
                "amount": "number",
                "carbs": "number",
                "proteins": "number",
                "fats": "number"
            }
        ],
        "timestamp": "datetime"
    }
}
```

## Development

### Testing WebSocket Connection
An example WebSocket subscriber script is provided to help test the real-time meal analysis updates during development.

1. First, get a JWT token by creating a dev session:
```bash
curl -X POST http://localhost:8080/auth/dev \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test-user-123"}'
```

2. Run the example subscriber with your JWT token:
```bash
python subscriber.py <your-jwt-token>
```

The subscriber will:
- Connect to your local WebSocket server
- Listen for meal analysis updates
- Print received messages in a formatted way
- Handle connection errors gracefully
- Exit cleanly with Ctrl+C

Example output:
```
Connected to WebSocket server
Waiting for messages...

Received message at 2024-01-20 15:30:45
{
  "meal_id": "123e4567-e89b-12d3-a456-426614174000",
  "event": "analysis_complete",
  "data": {
    "meal_name": "Chocolate Cake",
    "ingredients": [
      {
        "name": "mock ingredient",
        "amount": 100,
        "carbs": 20,
        "proteins": 10,
        "fats": 5
      }
    ],
    "timestamp": "2024-01-20T15:30:45.123456"
  }
}
```

3. To test the full flow:
   - Keep the subscriber running
   - Submit a meal using the `/meals` endpoint
   - Watch the analysis results arrive in real-time
   - Submit feedback using `/meals/feedback` to see updated analysis

## CORS
The API supports Cross-Origin Resource Sharing (CORS) with all origins (*) allowed.

## Notes
- All images must be base64 encoded
- The API uses GPT Vision for analysis
- Analysis results are delivered asynchronously through WebSocket
- Each feedback submission triggers a new analysis
- WebSocket connections will automatically close after 24 hours of inactivity
- All timestamps are in ISO 8601 format

## Database Schema

The application uses MongoDB with the following collections:

### Collection: meals
```json
{
    "meal_id": "uuid",
    "user_id": "string",
    "b64_img": "string",
    "created_at": "datetime"
}
```

### Collection: analysis
```json
{
    "meal_id": "uuid",
    "meal_name": "string",
    "ingredients": [
        {
            "name": "string",
            "amount": "number",
            "carbs": "number",
            "proteins": "number",
            "fats": "number"
        }
    ],
    "timestamp": "datetime"
}
```

### Collection: feedback
```json
{
    "meal_id": "uuid",
    "feedback": "string",
    "timestamp": "datetime"
}
```
