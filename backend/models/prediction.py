# backend/models/prediction.py

# Pydantic models for structuring prediction and analysis data, including RBAC 'allow' flags.

from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import datetime

# Model for an individual prediction event within the 'predictions' list
class PredictionEventResponse(BaseModel):
    market_category: Optional[str] = Field(None, description="The category of the betting market.")
    event: Optional[str] = Field(None, description="The specific prediction event.")
    confidence_score: Optional[float] = Field(None, description="Confidence score out of 10.")
    reason: Optional[str] = Field(None, description="Reasoning behind the prediction.")
    allow: bool = Field(True, description="Indicates if this prediction event is allowed for the current user's access level.")

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "market_category": "Popular Markets",
                "event": "1X2: Home Win",
                "confidence_score": 7.5,
                "reason": "Home team has strong home form.",
                "allow": True
            }
        }
    )

# Model for the nested 'predictions' object within the main match document
class MatchPredictionsDataResponse(BaseModel):
     predictions: List[PredictionEventResponse] = Field([], description="A list of individual prediction events.")
     overall_match_confidence_score: Optional[float] = Field(None, description="Overall match confidence score.")
     general_assessment: Optional[str] = Field(None, description="General assessment of the match.")
     allow: bool = Field(True, description="Indicates if the prediction data for this match is allowed for the current user's access level.") # Allow flag for the entire predictions object


# Model for the nested 'post_match_analysis.analysis' list items
class AnalysisEvent(BaseModel):
     market_category: Optional[str] = Field(None, description="Category of the original prediction.")
     event: Optional[str] = Field(None, description="Original prediction event.")
     confidence_score: Optional[float] = Field(None, description="Original confidence score.")
     outcome: Optional[str] = Field(None, description="Outcome of the prediction (Yes/No).")
     comment: Optional[str] = Field(None, description="Comment on the outcome.")


# Model for the nested 'post_match_analysis' object
class MatchAnalysisResponse(BaseModel):
    analysis: List[AnalysisEvent] = Field([], description="Analysis of how each prediction compared to the outcome.")
    home_team_goal: Optional[Dict[str, Any]] = Field(None, description="Details about home team goals.") # Using Dict[str, Any] as structure is known but nested models might be overkill here
    away_team_goal: Optional[Dict[str, Any]] = Field(None, description="Details about away team goals.") # Using Dict[str, Any]
    overall_accuracy: Optional[str] = Field(None, description="Overall prediction accuracy percentage.")
    analysis_summary: Optional[str] = Field(None, description="Summary of the post-match analysis.")
    allow: bool = Field(True, description="Indicates if the post-match analysis for this match is allowed (should typically be True as it's free).")


# Model for the main match prediction document (response structure)
class MatchPredictionResponse(BaseModel):
    id: str = Field(..., alias="_id", description="MongoDB document ID as a string.") # Map _id to id
    competition: Optional[str] = Field(None, description="Competition name.")
    date: Optional[str] = Field(None, description="Match date (DD-MM-YYYY).")
    time: Optional[str] = Field(None, description="Match time (HH:MM).")
    home_team: Optional[str] = Field(None, description="Home team name.")
    away_team: Optional[str] = Field(None, description="Away team name.")
    stats_link: Optional[str] = Field(None, description="Link to match statistics.")
    predict_status: Optional[bool] = Field(None, description="Status indicating if pre-match predictions are available.")
    post_match_analysis_status: Optional[bool] = Field(None, description="Status indicating if post-match analysis is available.")
    timestamp: Optional[datetime] = Field(None, description="Timestamp of when the data was generated.")
    predictions: Optional[MatchPredictionsDataResponse] = Field(None, description="Pre-match prediction data (includes nested allow flags).") # Use the nested model
    post_match_analysis: Optional[MatchAnalysisResponse] = Field(None, description="Post-match analysis data (includes nested allow flag).") # Use the nested model
    error_details: Optional[Dict[str, Any]] = Field(None, description="Details of any errors during processing.")
    status: Optional[str] = Field(None, description="Overall status of the match document.")

    model_config = ConfigDict(
        populate_by_name=True, # Allows mapping alias (_id) to field name (id)
        json_schema_extra={
            "example": {
                "_id": "681755d6335a8053230db5e2",
                "competition": "England - Premier League",
                "date": "05-05-2025",
                "time": "14:00",
                "home_team": "Brentford",
                "away_team": "Manchester Utd",
                "stats_link": "...",
                "predict_status": True,
                "post_match_analysis_status": False, # Example for pre-match data
                "timestamp": "2025-05-05T14:00:00Z",
                "predictions": {
                    "predictions": [
                        {"market_category": "Popular Markets", "event": "1X2: Brentford", "confidence_score": 7.5, "reason": "...", "allow": True},
                        {"market_category": "Popular Markets", "event": "Over/Under – Goal: Over 2.5", "confidence_score": 7.0, "reason": "...", "allow": False}, # Example of a restricted event
                    ],
                    "overall_match_confidence_score": 6.2,
                    "general_assessment": "Bees strong at home...",
                    "allow": True # Example where predictions for this match are allowed
                },
                "post_match_analysis": None, # Not available in this example
                "error_details": None,
                "status": "predictions_complete"
            }
        }
    )

# Optional: Model if you decide to group matches by competition in the response
class CompetitionPredictionResponse(BaseModel):
    competition_name: str = Field(..., description="The name of the competition.")
    matches: List[MatchPredictionResponse] = Field([], description="A list of matches within this competition.")
    allow: bool = Field(True, description="Indicates if this competition is allowed for the current user's access level (relevant for free users).") # Allow flag for the entire competition