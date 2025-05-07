# backend/features/advertising/routes.py 

# This file defines FastAPI API endpoints specific to the advertising feature.
# Includes endpoints to fetch active ads.

import datetime
# Import asyncio because the find_many function uses it internally
import asyncio
from fastapi import APIRouter, HTTPException, status, Request, Query
from pymongo.collection import Collection # Import Collection for type hinting
from typing import List, Dict, Any, Optional # Import type hints
from bson import ObjectId # Import ObjectId for working with document IDs
import traceback # Import traceback for detailed error logging

# Import database module
from ...db import mongo_client as database # Adjusted import path

# --- Define API Router for this feature ---
router = APIRouter(
    prefix="/api/ads",               # Use the /api/ads prefix as discussed
    tags=["advertising"]             # Optional: Add tags for OpenAPI documentation
)

# --- Endpoint to Fetch Active Advertisements (New) ---
# Fetches ads that are active, within date range, and optionally by placement.
@router.get("/active", response_model=List[Dict[str, Any]]) # Specify response model hint
async def get_active_advertisements(
    request: Request, # To access app.state
    placement: Optional[str] = Query(None, description="Filter ads by placement (e.g., 'today_view_top')"),
    active: Optional[bool] = Query(None, description="Filter ads by active status (true or false). Defaults to true if not provided.")
):
    """
    Retrieves active advertisements based on current date/time,
    optional placement filter, and optional explicit active status filter.
    """
    print(f"Request received for /api/ads/active with placement={placement}, active={active}")

    # --- Access the advertising collection from app.state ---
    # Use the getter function from the database module
    advertising_collection: Collection | None = database.get_advertising_collection()

    if advertising_collection is None:
        print("Error: Advertising collection not accessible.")
        # Use 503 Service Unavailable if the database connection isn't live/collection isn't available
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is not available."
        )

    # --- Build the MongoDB Query ---
    query: Dict[str, Any] = {}

    # Filter by current date/time being within start_datetime and end_datetime
    now = datetime.datetime.utcnow() # Use UTC time for consistency with potential storage
    query["start_datetime"] = {"$lte": now}
    query["end_datetime"] = {"$gte": now}

    # Filter by placement if provided
    if placement is not None:
        query["placement"] = placement

    # Filter by active status based on the query parameter (flexible)
    # If parameter is provided, use its boolean value
    if active is not None:
        query["active"] = active
    else:
        # If parameter is NOT provided, default to filtering for active=True
        query["active"] = True

    print(f"MongoDB query for advertising: {query}")

    # --- Fetch documents from the collection using the database helper function ---
    try:
        # Use the database.find_many helper function as intended
        # This function handles the asyncio.to_thread wrapping and returns a list
        ads_list = await database.find_many(advertising_collection, query)

        # The database.find_many function returns List[Dict] or [].
        # We still need to convert ObjectId to string for JSON serialization
        # before returning, as our Pydantic response_model hint is List[Dict[str, Any]].
        for ad in ads_list:
            if '_id' in ad and isinstance(ad['_id'], ObjectId):
                ad['_id'] = str(ad['_id'])
            # Optional: Handle datetime serialization if needed later, but FastAPI usually handles standard datetime objects.


        print(f"Found {len(ads_list)} matching advertisements using database.find_many.")

        # Return the list of advertisement documents
        return ads_list

    except Exception as e:
        # Catch any other unexpected errors during processing after fetch
        print(f"An unexpected error occurred after fetching advertisements: {e}")
        # Include traceback for unexpected errors
        traceback.print_exc() # Use traceback.print_exc() for detailed error printing

        # Raise an HTTP exception to return an error response to the client
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred while processing advertisements: {e}"
        )

