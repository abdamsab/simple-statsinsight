# backend/features/football_analytics/routes.py

# This file defines FastAPI API endpoints specific to the football analytics feature
# and delegates requests to the football analytics orchestration layer.
# Includes endpoints to trigger processes and fetch results.

import datetime # Import datetime for date validation
import random # Import random for sampling - ADDED IMPORT
# Modified import to include Depends
from fastapi import APIRouter, HTTPException, status, BackgroundTasks, Request, Query, Depends # MODIFIED IMPORT - added Depends
from pymongo.collection import Collection # Import Collection for type hinting
from google import genai # Import genai for type hinting
# Modified import for Optional, List, Union (already there, just ensuring clarity)
from typing import Dict, Any, Optional, List, Union

# Import ObjectId from bson for validating/using MongoDB IDs (already there)
from bson import ObjectId
from pymongo.errors import PyMongoError # Import MongoDB specific errors
from pymongo.cursor import Cursor # Import Cursor for type hinting - ADDED IMPORT needed for type hints

# --- Import orchestration functions from the feature's orchestration layer ---
from . import orchestration as football_analytics_orchestration # Relative import within the same feature folder

# --- Import database module ---
from ...db import mongo_client as database # Import database module
# Explicitly import getter functions needed by this file
from ...db.mongo_client import ( # MODIFIED IMPORT - added specific getters
    get_competitions_collection,
    get_parameters_collection,
    get_predictions_collection, # ADDED IMPORT for predictions collection getter
)


# Import Pydantic models for authentication dependency (needed for Depends)
from ...models.auth import TokenData # ADDED IMPORT

# Import the get_current_user dependency (needed for Depends)
from ...features.user.auth.dependencies import get_current_user # ADDED IMPORT

# Import Pydantic models for prediction data structure (from the new backend/models/prediction.py)
from ...models.prediction import ( # ADDED IMPORT
    PredictionEventResponse,
    MatchPredictionsDataResponse,
    MatchPredictionResponse,
    CompetitionPredictionResponse, # If grouping by comp
    AnalysisEvent,
    MatchAnalysisResponse
)


# --- Import Settings for type hinting ---
from ...config.settings import Settings # Already existing import


# --- Define API Router for this feature ---
# PREFIX IS NOW /api/match
router = APIRouter(
    prefix="/api/match", # Prefix changed to /api/match
    tags=["football_analytics"]
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


# --- MODIFIED Endpoint to Fetch Predictions & Analysis with RBAC (/api/match/predictions) ---
# Added Depends(get_current_user) and implemented RBAC logic
# REPLACE the entire existing @router.get("/predictions") function definition with this code:
@router.get("/predictions", response_model=List[MatchPredictionResponse]) # Specify response model
async def get_predictions_and_analysis_endpoint(
    request: Request,
    target_date: str = Query(..., description="Fetch data for a specific date (DD-MM-YYYY)"), # Require date
    current_user: TokenData = Depends(get_current_user), # Protect endpoint and get user - ADDED DEPENDENCY
):
    """
    Endpoint to fetch match data (predictions or analysis) for a specific date
    based on status flags and apply RBAC for free users on prediction data.
    Returns a list of documents for the date.
    """
    print(f"Received request for match data for date: {target_date} by user ID: {current_user.user_id}, Role: {current_user.role}")

    # Get collections and parameters using the getter functions from mongo_client
    competitions_collection: Collection | None = get_competitions_collection()
    predictions_collection: Collection | None = get_predictions_collection() # Get predictions collection using getter
    parameters_document: Dict[str, Any] | None = request.app.state.db_parameters # Get the loaded parameters from app.state

    # Check for critical dependencies
    if competitions_collection is None or predictions_collection is None or parameters_document is None:
         print("Critical dependency missing (collections or parameters). Returning 503.")
         raise HTTPException(
             status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
             detail="Backend is not fully initialized or configuration is missing."
         )

    # Validate target_date format
    try:
        datetime.datetime.strptime(target_date, '%d-%m-%Y')
    except ValueError:
        print(f"Invalid target_date format provided: {target_date}. Returning 400.")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid target_date format. Please use DD-MM-YYYY.")

    # Build query to fetch matches for the specific date
    query: Dict[str, Any] = {"date": target_date}

    print(f"Fetching match documents for date: {target_date}")

    try:
        # Fetch match documents for the date using the database helper function
        # Use asyncio.to_thread as find_many is blocking in your mongo_client
        match_documents = await database.find_many(predictions_collection, query)


        if not match_documents:
            print(f"No match documents found for date: {target_date}. Returning empty list.")
            return [] # Return empty list if no documents for the date

        print(f"Found {len(match_documents)} match documents for date: {target_date}.")

        # --- Prepare RBAC related data ---
        user_role = current_user.role
        # Get limits from parameters, handling BSON $numberInt and 0 means unlimited
        free_user_match_limit_raw = parameters_document.get("number_allow_match", 0)
        free_user_event_limit_raw = parameters_document.get("number_allow_event", 0)

        # Convert potential BSON $numberInt to Python int, handle missing/invalid types, and 0=unlimited
        free_user_match_limit = float('inf') # Default to unlimited
        if isinstance(free_user_match_limit_raw, (int, float)): # Check for int or float directly
             free_user_match_limit = free_user_match_limit_raw if free_user_match_limit_raw > 0 else float('inf')
        elif isinstance(free_user_match_limit_raw, dict) and '$numberInt' in free_user_match_limit_raw: # Handle BSON $numberInt
             try:
                  int_val = int(free_user_match_limit_raw['$numberInt'])
                  free_user_match_limit = int_val if int_val > 0 else float('inf')
             except (ValueError, TypeError):
                  print(f"Warning: Could not convert '$numberInt' for 'number_allow_match': {free_user_match_limit_raw}. Treating as unlimited.")
                  free_user_match_limit = float('inf')
        else:
             print(f"Warning: 'number_allow_match' parameter is not a recognized type ({type(free_user_match_limit_raw)}). Treating as unlimited.")
             free_user_match_limit = float('inf')

        free_user_event_limit = float('inf') # Default to unlimited
        if isinstance(free_user_event_limit_raw, (int, float)): # Check for int or float directly
            free_user_event_limit = free_user_event_limit_raw if free_user_event_limit_raw > 0 else float('inf')
        elif isinstance(free_user_event_limit_raw, dict) and '$numberInt' in free_user_event_limit_raw: # Handle BSON $numberInt
             try:
                  int_val = int(free_user_event_limit_raw['$numberInt'])
                  free_user_event_limit = int_val if int_val > 0 else float('inf')
             except (ValueError, TypeError):
                  print(f"Warning: Could not convert '$numberInt' for 'number_allow_event': {free_user_event_limit_raw}. Treating as unlimited.")
                  free_user_event_limit = float('inf')
        else:
             print(f"Warning: 'number_allow_event' parameter is not a recognized type ({type(free_user_event_limit_raw)}). Treating as unlimited.")
             free_user_event_limit = float('inf')


        print(f"User Role: {user_role}. Configured Free Limits - Matches: {free_user_match_limit}, Events per Match: {free_user_event_limit}")


        allowed_free_competitions: List[str] = []
        if user_role == 'free':
            try:
                # Fetch names of competitions where 'allow' is true using the database helper function
                # Use asyncio.to_thread as find_many is blocking
                allowed_comp_docs = await database.find_many(get_competitions_collection(), {"allow": True}, options={"projection": {"name": 1}}) # Project only name
                allowed_free_competitions = [doc["name"] for doc in allowed_comp_docs if "name" in doc]
                print(f"Free user allowed competitions: {allowed_free_competitions}")
            except Exception as e:
                 print(f"Error fetching allowed competitions for free user: {e}")
                 # On error, treat no competitions as allowed
                 allowed_free_competitions = []


        # --- Process each match document based on status flags and RBAC ---
        processed_matches: List[MatchPredictionResponse] = []

        # Filter matches for free user based on allowed competitions BEFORE applying daily match limit + sampling
        # This ensures sampling only happens among matches from allowed competitions
        allowed_comp_matches_for_free: List[Dict[str, Any]] = []
        disallowed_comp_matches_for_free: List[Dict[str, Any]] = []

        if user_role == 'free':
            for doc in match_documents:
                 comp_name = doc.get("competition")
                 if comp_name in allowed_free_competitions:
                      allowed_comp_matches_for_free.append(doc)
                 else:
                      disallowed_comp_matches_for_free.append(doc)
            print(f"Free User: {len(allowed_comp_matches_for_free)} matches in allowed comps, {len(disallowed_comp_matches_for_free)} in disallowed comps.")
        else:
            # Paid or Admin user - all matches are treated as 'allowed' for processing purposes
            allowed_comp_matches_for_free = match_documents # Process all matches
            disallowed_comp_matches_for_free = [] # No disallowed comps for paid/admin


        # Apply overall daily match limit and sampling for free users *within* allowed competitions
        matches_to_sample_from = allowed_comp_matches_for_free
        sampled_allowed_matches: List[Dict[str, Any]] = []

        if user_role == 'free' and free_user_match_limit < float('inf') and len(matches_to_sample_from) > free_user_match_limit:
             print(f"Free user. Applying overall daily match limit ({free_user_match_limit}) with random sampling from {len(matches_to_sample_from)} allowed matches.")
             # Ensure we don't try to sample more matches than available
             num_samples = min(len(matches_to_sample_from), int(free_user_match_limit))
             sampled_allowed_matches = random.sample(matches_to_sample_from, num_samples)
        elif user_role != 'free' or (user_role == 'free' and free_user_match_limit >= float('inf')):
             # Paid/Admin gets all matches OR Free user with unlimited match access
             sampled_allowed_matches = match_documents # Process all original matches if paid/admin or unlimited free match access
             if user_role != 'free':
                  print(f"User is paid/admin. Processing all {len(match_documents)} matches for the day.")
             else:
                  print(f"Free user with unlimited match access or not enough allowed matches ({len(allowed_comp_matches_for_free)}) to sample. Including all allowed matches.")


        # Create a set of the match IDs that ARE allowed for predictions by RBAC (based on sampling/filtering)
        allowed_prediction_match_ids = {str(doc.get('_id')) for doc in sampled_allowed_matches}


        # Process ALL matches for the day to ensure both predictions (with RBAC) and analysis are included
        # Process matches in their original order to maintain display consistency
        for doc in match_documents:
            doc_id = str(doc.get("_id")) # Get and convert ObjectId to string
            comp_name = doc.get("competition")


            # Determine what data to include based on status flags in the document
            include_predictions_logic = doc.get("predict_status", False) and not doc.get("post_match_analysis_status", False)
            include_analysis_logic = doc.get("post_match_analysis_status", False)

            processed_predictions_data: Optional[MatchPredictionsDataResponse] = None
            processed_analysis_data: Optional[MatchAnalysisResponse] = None


            # --- Process Analysis Data (Always Allowed) ---
            if include_analysis_logic:
                 raw_analysis = doc.get("post_match_analysis", {})
                 if raw_analysis:
                      try:
                          # Map raw analysis data to Pydantic model - Analysis is always allowed
                          # Need to handle potential BSON types in raw_analysis if they exist
                          processed_analysis_data = MatchAnalysisResponse(
                              analysis=[
                                   {"market_category": a.get("market_category"), "event": a.get("event"), "confidence_score": a.get("confidence_score"), "outcome": a.get("outcome"), "comment": a.get("comment")}
                                   for a in raw_analysis.get("analysis", [])
                              ],
                              home_team_goal=raw_analysis.get("home_team_goal", {}),
                              away_team_goal=raw_analysis.get("away_team_goal", {}),
                              overall_accuracy=raw_analysis.get("overall_accuracy"),
                              analysis_summary=raw_analysis.get("analysis_summary"),
                              allow=True # Analysis is always allowed
                          )
                          print(f"Match {doc_id}: Including post-match analysis (always allowed).")
                      except Exception as e:
                           print(f"Error processing post-match analysis for match {doc_id}: {e}")
                           processed_analysis_data = None # Set to None on error
                 else:
                     print(f"Match {doc_id}: post_match_analysis_status is true, but analysis data is missing.")


            # --- Process Prediction Data (RBAC Applied Here) ---
            if include_predictions_logic: # Only process predictions if status flags indicate pre-match
                 raw_predictions_data = doc.get("predictions", {})
                 raw_prediction_events = raw_predictions_data.get("predictions", [])

                 processed_prediction_events: List[PredictionEventResponse] = []
                 predictions_allow_status_for_match = False # Assume predictions for this match are not allowed initially

                 # Check if predictions for THIS match document should be allowed based on RBAC
                 # This check is now simplified using the allowed_prediction_match_ids set
                 is_match_predictions_allowed_by_rbac = doc_id in allowed_prediction_match_ids

                 if is_match_predictions_allowed_by_rbac:
                      print(f"Match {doc_id}: Predictions allowed by RBAC.")
                      # Apply event limit and sampling if applicable
                      events_to_process = raw_prediction_events
                      if user_role == 'free' and free_user_event_limit < float('inf') and len(raw_prediction_events) > free_user_event_limit:
                           print(f"Match {doc_id}: Free user. Applying event limit ({free_user_event_limit}) with random sampling.")
                           # Ensure we don't try to sample more events than available
                           num_samples = min(len(raw_prediction_events), int(free_user_event_limit))
                           sampled_events = random.sample(raw_prediction_events, num_samples)
                           processed_prediction_events = [
                                PredictionEventResponse(
                                    market_category=p.get("market_category"),
                                    event=p.get("event"),
                                    confidence_score=p.get("confidence_score"),
                                    reason=p.get("reason"),
                                    allow=True # Sampled events are allowed
                                ) for p in sampled_events
                           ]
                           # Add remaining predictions with allow=False so frontend knows they exist but are restricted
                           sampled_events_set = {tuple(p.items()) for p in sampled_events} # Use tuples for hashable set comparison
                           for p in raw_prediction_events:
                                if tuple(p.items()) not in sampled_events_set:
                                     processed_prediction_events.append(
                                           PredictionEventResponse(
                                               market_category=p.get("market_category"),
                                               event=p.get("event"),
                                               confidence_score=p.get("confidence_score"),
                                               reason=p.get("reason"),
                                               allow=False # Not sampled, not allowed
                                           )
                                     )
                           predictions_allow_status_for_match = True if len(sampled_events) > 0 else False # Match predictions allowed if any events were sampled
                      else: # User is paid/admin OR free user with unlimited event access or sample size <= limit
                           print(f"Match {doc_id}: User is paid/admin, or free user with unlimited event access or sample size <= limit. Including all prediction events.")
                           processed_prediction_events = [
                               PredictionEventResponse(
                                   market_category=p.get("market_category"),
                                   event=p.get("event"),
                                   confidence_score=p.get("confidence_score"),
                                   reason=p.get("reason"),
                                   allow=True # All predictions are allowed
                               ) for p in raw_prediction_events
                           ]
                           predictions_allow_status_for_match = True if len(raw_prediction_events) > 0 else False

                      # Structure the predictions data response part
                      processed_predictions_data = MatchPredictionsDataResponse(
                           predictions=processed_prediction_events,
                           overall_match_confidence_score=raw_predictions_data.get("overall_match_confidence_score"),
                           general_assessment=raw_predictions_data.get("general_assessment"),
                           allow=predictions_allow_status_for_match # Allow status for the predictions part of the match
                      )

                 else: # Predictions for this match are NOT allowed by RBAC
                      print(f"Match {doc_id}: Predictions not allowed by RBAC. Including prediction data structure but marking as not allowed.")
                      # Include the full list of prediction events, but mark all as allow=False
                      raw_predictions_data = doc.get("predictions", {})
                      raw_prediction_events = raw_predictions_data.get("predictions", [])
                      processed_prediction_events_not_allowed = [
                           PredictionEventResponse(
                               market_category=p.get("market_category"),
                               event=p.get("event"),
                               confidence_score=p.get("confidence_score"),
                               reason=p.get("reason"),
                               allow=False # Not allowed by RBAC
                           ) for p in raw_prediction_events
                      ]
                      processed_predictions_data = MatchPredictionsDataResponse(
                           predictions=processed_prediction_events_not_allowed,
                           overall_match_confidence_score=raw_predictions_data.get("overall_match_confidence_score"),
                           general_assessment=raw_predictions_data.get("general_assessment"),
                           allow=False # Predictions for this match are NOT allowed by RBAC
                      )


            # Create the final response model for this match
            processed_match = MatchPredictionResponse(
                id=doc_id,
                competition=doc.get("competition"),
                date=doc.get("date"),
                time=doc.get("time"),
                home_team=doc.get("home_team"),
                away_team=doc.get("away_team"),
                stats_link=doc.get("stats_link"),
                predict_status=doc.get("predict_status", False),
                post_match_analysis_status=doc.get("post_match_analysis_status", False),
                timestamp=doc.get("timestamp"), # Check if timestamp needs conversion if it's BSON date
                # Include predictions if predictions data was processed (either allowed or not allowed but structured)
                predictions=processed_predictions_data if include_predictions_logic else None,
                post_match_analysis=processed_analysis_data, # Include analysis part if available
                error_details=doc.get("error_details"),
                status=doc.get("status"),
            )
            processed_matches.append(processed_match) # Add this processed match to the list


        print(f"Finished processing matches. Returning {len(processed_matches)} results.")
        return processed_matches # Return the list of processed match documents

    except PyMongoError as e:
        print(f"MongoDB Error fetching or processing match data for date {target_date}: {e}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error fetching match data: {e}"
        )
    except Exception as e:
        print(f"An unexpected error occurred fetching or processing match data for date {target_date}: {e}")
        import traceback
        print(traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred: {e}"
        )


# --- Endpoint to Fetch Prediction and Analysis Results by various filters (Retained) ---
# This endpoint is kept for experimental purposes as requested.
# It does NOT apply the RBAC logic from the /predictions endpoint.
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
