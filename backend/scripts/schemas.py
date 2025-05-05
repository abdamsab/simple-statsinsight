# backend/config/schemas.py

# This file contains JSON schemas defining the expected structure of AI output.
# These can be defined as dictionaries here or loaded from a configuration source.

# Since your schemas are loaded from the DB parameters, these could be default values
# or just serve as documentation.

# Example Match Prediction Schema (Use this as a default if DB loading fails or for documentation)
MATCH_PREDICTION_SCHEMA = {
  "type": "object",
  "properties": {
    "match_predictions": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "predicted_event_name": {"type": "string", "description": "e.g. Both Teams To Score, Over 2.5 Goals"},
          "predicted_outcome": {"type": "string", "description": "e.g. Yes, No, Over, Under, Home Win, Away Win, Draw"},
          "confidence_score": {"type": "string", "description": "Confidence score (e.g., High, Medium, Low)"},
          "reasoning": {"type": "string", "description": "Brief explanation for the prediction based on stats provided"}
        },
        "required": ["predicted_event_name", "predicted_outcome", "confidence_score", "reasoning"]
      }
    }
  },
  "required": ["match_predictions"]
}

# You can define other schemas here (e.g., for post-match analysis)
# POST_MATCH_ANALYSIS_SCHEMA = {
#     "type": "object",
#     "properties": {
#         "analysis_summary": {"type": "string"},
#         "key_events": {"type": "array", "items": {"type": "string"}}
#         # etc.
#     },
#     "required": ["analysis_summary"]
# }