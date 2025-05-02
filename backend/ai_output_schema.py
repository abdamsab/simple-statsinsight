
# --- JSON Schema for Match Prediction Output ---
MATCH_PREDICTION_SCHEMA = {
  "type": "object",
  "properties": {
    "predictions": { # Key for the array of predictions
      "type": "array",
      "description": "A list of individual predictions for the match.",
      "items": { # Schema for each item in the array
        "type": "object",
        "properties": {
          "market_category": {
            "type": "string",
            "description": "The category of the betting market, e.g., 'Popular Markets', 'Goals', 'Corners'."
          },
          "event": {
            "type": "string",
            "description": "The specific prediction event, e.g., 'Over 2.5 Goals', 'Both Teams to Score', 'Home Win'."
          },
          "confidence_score": {
            "type": "number",
            "format": "float", # Specify float format
            "description": "A numerical score representing the confidence in this specific prediction (e.g., out of 10)."
          },
          "reason": {
            "type": "string",
            "description": "A brief explanation or reasoning behind this specific prediction."
          }
        },
        "required": [
          "market_category",
          "event",
          "confidence_score",
          "reason"
        ]
      }
    },
    "overall_match_confidence_score": {
      "type": "number",
      "format": "float", # Specify float format
      "description": "A numerical score representing the overall confidence in the match assessment (e.g., out of 10)."
    },
    "general_assessment": {
      "type": "string",
      "description": "A general commentary or assessment of the match context, team form, table position, etc."
    }
  },
  "required": [
    "predictions",
    "overall_match_confidence_score",
    "general_assessment"
  ]
}

# --- JSON Schema for Post-Match Analysis Output ---
POST_MATCH_ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "analysis": {
            "type": "array",
            "description": "Analysis of how each pre-match prediction compared to the actual outcome.",
            "items": {
                "type": "object",
                "properties": {
                    "market_category": {
                        "type": "string",
                        "description": "The category of the original pre-match betting market."
                    },
                    "event": {
                        "type": "string",
                        "description": "The specific pre-match prediction event."
                    },
                    "confidence_score": {
                        "type": "number",
                        "description": "The confidence score from the pre-match prediction."
                    },
                    "outcome": {
                        "type": "string",
                        "description": "Indicates if the prediction was correct or incorrect.",
                        "enum": ["Yes", "No"] # Restrict to these two values
                    },
                    "comment": {
                        "type": "string",
                        "description": "A concise comment explaining the outcome."
                    }
                },
                "required": [
                    "market_category",
                    "event",
                    "confidence_score",
                    "outcome",
                    "comment"
                ]
            }
        },
        "home_team_goal": {
            "type": "object",
            "description": "Details about goals scored by the home team.",
            "properties": {
                "goal": {
                    "type": "number", # Should probably be integer for goal count
                    "description": "The number of goals scored by the home team."
                },
                "scorer": {
                    "type": "array",
                    "description": "A list of scorers and the minute they scored (e.g., 'name (minute)').",
                    "items": {
                        "type": "string"
                    }
                }
            },
            "required": [
                "goal",
                "scorer"
            ]
        },
        "away_team_goal": {
            "type": "object",
            "description": "Details about goals scored by the away team.",
            "properties": {
                "goal": {
                    "type": "number", # Should probably be integer for goal count
                    "description": "The number of goals scored by the away team."
                },
                "scorer": {
                    "type": "array",
                    "description": "A list of scorers and the minute they scored (e.g., 'name (minute)').",
                    "items": {
                        "type": "string"
                    }
                }
            },
            "required": [
                "goal",
                "scorer"
            ]
        },
        "overall_accuracy": {
            "type": "string", # Schema shows "XX.XX%" string format
            "description": "The calculated overall prediction accuracy as a percentage string (e.g., '68.75%')."
        },
        "analysis_summary": {
            "type": "string",
            "description": "A general summary of the post-match analysis."
        }
    },
    "required": [
        "analysis",
        "home_team_goal",
        "away_team_goal",
        "overall_accuracy",
        "analysis_summary"
    ]
}