# backend/features/football_analytics/routes.py

# This file defines FastAPI API endpoints specific to the football analytics feature
# and delegates requests to the football analytics service layer.

from fastapi import APIRouter, HTTPException, status, BackgroundTasks, Request # Import Request
from pymongo.collection import Collection # Import Collection for type hinting
from google import genai # Import genai for type hinting
from typing import Dict, Any # Import Dict, Any

# --- Import service functions from the feature's service layer ---
from . import orchestration as football_analytics_orchestration     # Relative import within the same feature folder

# --- Import Settings for type hinting ---
from ...config.settings import Settings


# --- Define API Router for this feature ---
router = APIRouter(
    prefix="/analytic",                 # Example prefix - uncomment and adjust if desired
    tags=["football_analytics"]         # Optional: Add tags for OpenAPI documentation
)


# --- Endpoint to Trigger Analysis and Predictions (Modified to use Request and pass state) ---
@router.post("/run-predictions")
async def run_predictions_endpoint(background_tasks: BackgroundTasks, request: Request):
    """Endpoint to trigger the full pre-match prediction process in the background."""
    # Access state from the Request object
    settings: Settings = request.app.state.settings
    db_parameters: Dict[str, Any] | None = request.app.state.db_parameters
    genai_client: genai.Client | None = request.app.state.genai_client
    competitions_collection: Collection | None = request.app.state.competitions_collection
    predictions_collection: Collection | None = request.app.state.predictions_collection

    # Basic checks to ensure necessary components were initialized during startup (from app.state)
    # These checks ensure the service function won't be called if core dependencies are missing.
    if settings is None or db_parameters is None or genai_client is None or competitions_collection is None or predictions_collection is None:
        print("Endpoint /run-predictions called, but one or more critical components are missing from app.state.")
        print(f"Debug app.state check: settings is None: {settings is None}, db_parameters is None: {db_parameters is None}, genai_client is None: {genai_client is None}, competitions_collection is None: {competitions_collection is None}, predictions_collection is None: {predictions_collection is None}")
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Backend is not fully initialized. Critical components are missing. Check startup logs.")


    # If all critical components are initialized, add the service orchestration function to background tasks.
    # Pass the necessary objects explicitly to the service function.
    background_tasks.add_task(
        football_analytics_orchestration.run_full_prediction_process,
        settings=settings, # Pass settings
        db_parameters=db_parameters, # Pass parameters from DB
        genai_client=genai_client, # Pass AI client
        competitions_collection=competitions_collection, # Pass collections
        predictions_collection=predictions_collection
    )

    # Return an immediate success response.
    return {"message": "Football prediction process started in the background. Check server logs for progress and results saved to DB."}


# --- Add other endpoints for this feature here ---
# Example: Endpoint to get recent predictions (Modified to use Request and app.state)
# @router.get("/predictions") # Using router now
# async def get_predictions_endpoint(request: Request): # Accept Request object
#     predictions_collection_instance: Collection | None = request.app.state.predictions_collection # Get collection from app.state
#     if predictions_collection_instance is None:
#         raise HTTPException(
#             status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
#             detail="Database predictions collection not available."
#         )
#     try:
#         # Use find_many from database module (imported implicitly via startup process)
#         # We don't need to import database module here if we only use collection instance.
#         # However, if find_many is in db/mongo_client.py, you'd import it:
#         from ...db import mongo_client as database
#         # from bson import ObjectId # Import ObjectId if needed
#         recent_predictions = await database.find_many( # Call the function using the imported module
#             predictions_collection_instance,
#             {},
#             options={"limit": 20, "sort": [("date", -1), ("time", 1)]}
#         )
#         # Convert ObjectId to string if necessary before returning
#         # for doc in recent_predictions:
#         #     if '_id' in doc and isinstance(doc['_id'], ObjectId):
#         #         doc['_id'] = str(doc['_id'])
#
#         return recent_predictions
#     except Exception as e:
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail=f"Error fetching predictions: {e}"
#         )

# Example: Endpoint to trigger re-analysis for a specific match (future feature)
# @router.post("/run-prediction/{match_id}")
# async def rerun_prediction_endpoint(match_id: str, background_tasks: BackgroundTasks, request: Request):
#     # Access state from Request
#     settings: Settings = request.app.state.settings
#     db_parameters: Dict[str, Any] | None = request.app.state.db_parameters
#     genai_client: genai.Client | None = request.app.state.genai_client
#     predictions_collection: Collection | None = request.app.state.predictions_collection
#
#     if settings is None or db_parameters is None or genai_client is None or predictions_collection is None:
#          raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Backend is not fully initialized.")
#
#     # This endpoint would call a service function specifically designed
#     # to find a match by ID, retrieve its markdown (if saved), and trigger analysis.
#     # background_tasks.add_task(
#     #     football_analytics_services.run_single_match_prediction,
#     #     match_id, settings, db_parameters, genai_client, predictions_collection # Pass necessary objects
#     # )
#     # return {"message": f"Prediction process started for match ID: {match_id}."}
#     pass # Implement this later