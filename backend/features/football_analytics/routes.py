# backend/features/football_analytics/routes.py

# This file defines FastAPI API endpoints specific to the football analytics feature
# and delegates requests to the football analytics orchestration layer.
# Includes endpoints to trigger processes and fetch results.

import datetime # Import datetime for date validation
from fastapi import APIRouter, HTTPException, status, BackgroundTasks, Request, Query # Import Query and status
from pymongo.collection import Collection # Import Collection for type hinting
from google import genai # Import genai for type hinting
from typing import Dict, Any, Optional, List, Union # Import Optional, List, Union for type hinting

# Import ObjectId from bson for validating/using MongoDB IDs
from bson import ObjectId
from pymongo.errors import PyMongoError # Import MongoDB specific errors

# --- Import orchestration functions from the feature's orchestration layer ---
from . import orchestration as football_analytics_orchestration # Relative import within the same feature folder

# --- Import database module ---
from ...db import mongo_client as database # Import database module

# --- Import Settings for type hinting ---
from ...config.settings import Settings



# --- Define API Router for this feature ---
router = APIRouter(
    prefix="/api/match",                 # Set prefix to /analytic based on user's successful call
    tags=["football_analytics"]         # Optional: Add tags for OpenAPI documentation
)


# --- Endpoint to Trigger Pre-Match Prediction Process ---
@router.post("/run-predictions")
async def run_predictions_endpoint(background_tasks: BackgroundTasks, request: Request):
    """Endpoint to trigger the full pre-match prediction process in the background."""
    print("Received request to run pre-match predictions.")
    # Access state from the Request object
    settings: Settings = request.app.state.settings
    db_parameters: Dict[str, Any] | None = request.app.state.db_parameters
    genai_client: genai.Client | None = request.app.state.genai_client
    competitions_collection: Collection | None = request.app.state.competitions_collection
    predictions_collection: Collection | None = request.app.state.predictions_collection

    # Basic check for critical dependencies before starting background task
    if settings is None or db_parameters is None or genai_client is None or competitions_collection is None or predictions_collection is None:
         print("Dependency missing for pre-match process. Returning 503.")
         raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Backend is not fully initialized. Critical components are missing for pre-match process.")

    print("Starting pre-match prediction background task.")
    # Add the orchestration function as a background task, passing the necessary state
    background_tasks.add_task(
        football_analytics_orchestration.run_full_prediction_process,
        settings, # Pass settings
        db_parameters, # Pass db_parameters
        genai_client, # Pass genai_client
        competitions_collection, # Pass competitions_collection
        predictions_collection # Pass predictions_collection
    )

    return {"message": "Pre-match prediction process started in the background."}


# --- Endpoint to Trigger Post-Match Analysis Process ---
@router.post("/run-post-match-analysis/{target_date}")
async def run_post_match_analysis_endpoint(target_date: str, background_tasks: BackgroundTasks, request: Request):
     """
     Endpoint to trigger the post-match analysis process for a specific date in the background.
     target_date should be in DD-MM-YYYY format.
     """
     print(f"Received request to run post-match analysis for date: {target_date}.")

     # Access state from the Request object
     settings: Settings = request.app.state.settings
     db_parameters: Dict[str, Any] | None = request.app.state.db_parameters
     genai_client: genai.Client | None = request.app.state.genai_client
     predictions_collection: Collection | None = request.app.state.predictions_collection

     # Basic check for critical dependencies before starting background task
     if settings is None or db_parameters is None or genai_client is None or predictions_collection is None:
          print("Dependency missing for post-match process. Returning 503.")
          raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Backend is not fully initialized. Critical components are missing for post-match analysis.")

     # Basic validation for target_date format (simple check)
     try:
         datetime.datetime.strptime(target_date, '%d-%m-%Y')
     except ValueError:
         raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid date format. Please use DD-MM-YYYY.")


     print(f"Starting post-match analysis background task for date: {target_date}.")
     # Add the post-match orchestration function as a background task, passing the necessary state and the date
     background_tasks.add_task(
         football_analytics_orchestration.run_post_match_analysis_process,
         settings, # Pass settings
         db_parameters, # Pass db_parameters
         genai_client, # Pass genai_client
         predictions_collection, # Pass predictions_collection
         target_date # Pass the target date string
     )

     return {"message": f"Post-match analysis process started in the background for date {target_date}."}


# --- NEW Endpoint to Fetch Predictions with Flexible Filters ---
@router.get("/predictions")
async def get_predictions_endpoint(
    request: Request,
    target_date: Optional[str] = Query(None, description="Filter by match date (DD-MM-YYYY)"),
    home_team: Optional[str] = Query(None, description="Filter by home team name (case-insensitive)"),
    away_team: Optional[str] = Query(None, description="Filter by away team name (case-insensitive)"),
    predict_status: Optional[bool] = Query(None, description="Filter by pre-match prediction status (true/false)"),
    post_match_analysis_status: Optional[bool] = Query(None, description="Filter by post-match analysis status (true/false)"),
    status: Optional[str] = Query(None, description="Filter by overall match status string"), # Added overall status filter
    competition: Optional[str] = Query(None, description="Filter by competition name"), # Added competition filter
    # Add other optional filter parameters as needed...
    limit: int = Query(100, description="Limit the number of results"), # Optional limit
    skip: int = Query(0, description="Skip a number of results for pagination") # Optional skip
) -> List[Dict[str, Any]]:
    """
    Endpoint to fetch prediction documents from the database with various filters.
    Returns a list of documents matching the criteria.
    """
    print(f"Received request to fetch predictions with filters: Date={target_date}, Home={home_team}, Away={away_team}, PredictStatus={predict_status}, PostMatchStatus={post_match_analysis_status}, Status={status}, Competition={competition}, Limit={limit}, Skip={skip}")

    predictions_collection: Collection | None = request.app.state.predictions_collection

    if predictions_collection is None:
         print("Predictions collection not available for fetching predictions. Returning 503.")
         raise HTTPException(
             status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
             detail="Database collection not available."
         )

    # Build the MongoDB query dictionary based on provided filters
    query: Dict[str, Any] = {}

    if target_date:
        # Basic validation for target_date format (DD-MM-YYYY)
        try:
            datetime.datetime.strptime(target_date, '%d-%m-%Y') # Corrected format string
            query["date"] = target_date
            print(f"Adding date filter: {target_date}")
        except ValueError:
            print(f"Invalid target_date format provided: {target_date}. Returning 400.")
            # Raising HTTPException for invalid date format
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid target_date format. Please use DD-MM-YYYY.")


    if home_team:
        # Consider using case-insensitive regex for more flexible team name matching
        # query["home_team"] = {"$regex": home_team, "$options": "i"} # Example case-insensitive regex
        query["home_team"] = home_team # Exact match for now as per original code
        print(f"Adding home_team filter: {home_team}")

    if away_team:
        # Consider using case-insensitive regex
        # query["away_team"] = {"$regex": away_team, "$options": "i"} # Example case-insensitive regex
        query["away_team"] = away_team # Exact match for now as per original code
        print(f"Adding away_team filter: {away_team}")

    if predict_status is not None: # Check specifically for None, as False is a valid filter
        query["predict_status"] = predict_status
        print(f"Adding predict_status filter: {predict_status}")

    if post_match_analysis_status is not None: # Check specifically for None
        query["post_match_analysis_status"] = post_match_analysis_status
        print(f"Adding post_match_analysis_status filter: {post_match_analysis_status}")

    if status: # Filter by overall status string if provided
        query["status"] = status
        print(f"Adding status filter: {status}")

    if competition: # Filter by competition string if provided
        query["competition"] = competition
        print(f"Adding competition filter: {competition}")


    print(f"Constructed query: {query}")

    try:
        # Use database.find_many with the constructed query and pagination options
        # Ensure database module is imported at the top of the file
        # from ...db import mongo_client as database # This import is now at the top

        # Pass limit and skip via the options dictionary as required by mongo_client.find_many
        options = {"limit": limit, "skip": skip}
        # Add a default sort order, e.g., by date and time
        options["sort"] = [("date", -1), ("time", 1)] # Sort by date descending, time ascending

        results = await database.find_many(predictions_collection, query, options=options)

        if not results:
            print("No documents found matching the filter criteria. Returning empty list.")
            return [] # Return empty list if no results

        # Convert ObjectId to string for JSON serialization
        # This should ideally be handled in the mongo_client.py find functions,
        # but doing it here ensures the API returns string IDs.
        for doc in results:
             if '_id' in doc and isinstance(doc['_id'], ObjectId):
                 doc['_id'] = str(doc['_id'])

        print(f"Successfully fetched {len(results)} documents.")
        return results # Return the list of documents

    except PyMongoError as e:
        print(f"MongoDB Error fetching predictions with filters: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error fetching predictions: {e}"
        )
    except Exception as e:
        print(f"An unexpected error occurred fetching predictions with filters: {e}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {e}"
        )


# --- Endpoint to Fetch Post-Match Analysis Results (MODIFIED for flexible filters) ---
# Renamed to fetch-results for broader use as requested
@router.get("/fetch-results")
async def get_football_analysis_results_endpoint( # Renamed function for clarity
    request: Request,
    target_date: Optional[str] = Query(None, description="Filter by match date (DD-MM-YYYY)"),
    match_id: Optional[str] = Query(None, description="Fetch result for a specific match ID"),
    home_team: Optional[str] = Query(None, description="Filter by home team name (case-insensitive)"),
    away_team: Optional[str] = Query(None, description="Filter by away team name (case-insensitive)"),
    predict_status: Optional[bool] = Query(None, description="Filter by pre-match prediction status (true/false)"), # Added predict_status filter
    post_match_analysis_status: Optional[bool] = Query(None, description="Filter by post-match analysis status (true/false)"), # Added post_match_analysis_status filter
    status: Optional[str] = Query(None, description="Filter by overall match status string"), # Added overall status filter
    competition: Optional[str] = Query(None, description="Filter by competition name"), # Added competition filter
    # Add other optional filter parameters as needed...
    limit: int = Query(100, description="Limit the number of results (only applies to date/filter queries, not single ID)"), # Optional limit
    skip: int = Query(0, description="Skip a number of results for pagination (only applies to date/filter queries, not single ID)") # Optional skip
) -> Union[List[Dict[str, Any]], Dict[str, Any]]: # Use Union to indicate possible return types (list or dict)
    """
    Endpoint to fetch prediction and analysis documents from the database with flexible filters.
    Can filter by date OR match_id, and optionally by other criteria, including analysis status.
    Returns a list of results for a date/filter query, or a single result for an ID query.
    This endpoint does NOT enforce post_match_analysis_status=True by default.
    """
    print(f"Received request to fetch results with flexible filters. Date: {target_date}, ID: {match_id}, Home: {home_team}, Away: {away_team}, PredictStatus={predict_status}, PostMatchStatus={post_match_analysis_status}, Status={status}, Competition={competition}, Limit: {limit}, Skip: {skip}")

    predictions_collection: Collection | None = request.app.state.predictions_collection

    if predictions_collection is None:
         print("Predictions collection not available for fetching results. Returning 503.")
         raise HTTPException(
             status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
             detail="Database collection not available."
         )

    # Build the base query - NO LONGER hardcoding any status
    query: Dict[str, Any] = {}

    # Handle the mutually exclusive target_date or match_id parameters
    if target_date and match_id:
         print("Both target_date and match_id provided. Returning 400.")
         raise HTTPException(
              status_code=status.HTTP_400_BAD_REQUEST,
              detail="Please provide either target_date or match_id, not both."
         )

    if match_id:
        # If a specific ID is provided, add it to the query
        if not ObjectId.is_valid(match_id):
             print(f"Invalid match_id format: {match_id}. Returning 400.")
             raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid match_id format.")
        query["_id"] = ObjectId(match_id)
        print(f"Adding match_id filter: {match_id}")

    elif target_date:
        # If a date is provided, add it to the query
        try:
            datetime.datetime.strptime(target_date, '%d-%m-%Y') # Corrected format string
            query["date"] = target_date
            print(f"Adding date filter: {target_date}")
        except ValueError:
            print(f"Invalid target_date format provided: {target_date}. Returning 400.")
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid target_date format. Please use DD-MM-YYYY.")

    # If neither date nor ID is provided, the query will fetch all documents matching other filters.
    # This is now allowed based on the request for flexible filtering.


    # Add other optional filters to the query if they are provided
    if home_team:
        # Consider using case-insensitive regex for more flexible team name matching
        # query["home_team"] = {"$regex": home_team, "$options": "i"} # Example case-insensitive regex
        query["home_team"] = home_team # Exact match for now as per original code
        print(f"Adding home_team filter: {home_team}")

    if away_team:
        # Consider using case-insensitive regex
        # query["away_team"] = {"$regex": away_team, "$options": "i"} # Example case-insensitive regex
        query["away_team"] = away_team # Exact match for now as per original code
        print(f"Adding away_team filter: {away_team}")

    # ADDED: Include predict_status and post_match_analysis_status filters if provided
    if predict_status is not None: # Check specifically for None
        query["predict_status"] = predict_status
        print(f"Adding predict_status filter: {predict_status}")

    if post_match_analysis_status is not None: # Check specifically for None
        query["post_match_analysis_status"] = post_match_analysis_status
        print(f"Adding post_match_analysis_status filter: {post_match_analysis_status}")

    if status: # Filter by overall status string if provided
        query["status"] = status
        print(f"Adding status filter: {status}")

    if competition: # Filter by competition string if provided
        query["competition"] = competition
        print(f"Adding competition filter: {competition}")


    print(f"Constructed query: {query}")

    try:
        # Ensure database module is imported at the top of the file
        # from ...db import mongo_client as database # This import is now at the top

        # Prepare options for find_many (only applicable for date/filter queries, not single ID)
        options: Dict[str, Any] = {}
        # Apply limit/skip only if NOT fetching by ID (i.e., fetching a list)
        if not match_id:
             options["limit"] = limit
             options["skip"] = skip
             # Add a default sort order, e.g., by date and time
             options["sort"] = [("date", -1), ("time", 1)] # Sort by date descending, time ascending


        # Call the appropriate database function based on whether an ID was provided
        if match_id:
            # If fetching by ID, use find_one
            result = await database.find_one(predictions_collection, query)
            if result:
                 result['_id'] = str(result['_id']) # Convert ObjectId to string
                 print(f"Found single result for ID {match_id} matching filters.")
                 return result # Return the single document
            else:
                 print(f"No document found for match ID {match_id} matching filters. Returning 404.")
                 # Return 404 Not Found if a specific ID was requested but not found
                 raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"No document found for match ID {match_id} matching filters.")

        else:
            # If fetching by date or other filters (returning a list), use find_many
            results = await database.find_many(predictions_collection, query, options=options)
            # Convert ObjectIds to strings for easier JSON serialization
            for doc in results:
                 if '_id' in doc and isinstance(doc['_id'], ObjectId):
                     doc['_id'] = str(doc['_id'])

            print(f"Found {len(results)} results matching criteria.")
            return results # Return list of documents (could be empty)


    except HTTPException:
        # Re-raise HTTPException raised within this block (e.g., from parameter validation or explicit 400/404)
        raise
    except Exception as e:
        # Catch any other unexpected errors during the endpoint execution
        print(f"An unexpected error occurred in fetch-results endpoint: {e}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {e}"
        )
