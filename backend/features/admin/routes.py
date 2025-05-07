# backend/features/admin/routes.py

# This file defines FastAPI API endpoints specific to the admin feature.
# Includes endpoints for administrative tasks, starting with fetching parameters.

from fastapi import APIRouter, HTTPException, status, Request # Import Request
from pymongo.collection import Collection # Import Collection for type hinting
from typing import Dict, Any, List, Optional # Import type hints
from bson import ObjectId # Import ObjectId for working with document IDs
import traceback # Import traceback for detailed error logging

# Import database module
from ...db import mongo_client as database # Adjusted import path to go up 3 levels

# --- Define API Router for this feature ---
router = APIRouter(
    prefix="/api/admin",             # Use the /api/admin prefix as per design
    tags=["admin"]                   # Optional: Add tags for OpenAPI documentation
)

# --- IMPORTANT NOTE FOR THIS STEP ---
# Authentication and Authorization are NOT implemented on this endpoint yet.
# This is a temporary state to build the structure safely.
# Adding proper Admin Auth/RBAC is a critical future step.

# --- Endpoint to Fetch System Parameters (New) ---
# Fetches the main parameters document from the database.
@router.get("/parameters", response_model=Dict[str, Any]) # Specify response model hint
async def get_system_parameters(request: Request):
    """
    Retrieves the main system parameters document from the 'parameters' collection.
    NOTE: This endpoint is currently UNPROTECTED (no authentication/authorization).
    Proper Admin Auth/RBAC needs to be implemented in a future step.
    """
    print("Request received for /api/admin/parameters")

    # --- Access the parameters collection from app.state using the getter ---
    parameters_collection: Collection | None = database.get_parameters_collection() # Use the getter function

    if parameters_collection is None:
        print("Error: Parameters collection not accessible.")
        # Use 503 Service Unavailable if the database connection isn't live/collection isn't available
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database service is not available."
        )

    # --- Fetch the parameters document ---
    try:
        # We expect only one parameters document, so use find_one with an empty query
        parameters_doc = await database.find_one(parameters_collection, {})

        if parameters_doc:
            # Convert ObjectId to string for JSON serialization (important!)
            if '_id' in parameters_doc and isinstance(parameters_doc['_id'], ObjectId):
                parameters_doc['_id'] = str(parameters_doc['_id'])

            print("Successfully fetched system parameters.")
            # Return the parameters document
            return parameters_doc
        else:
            # This case should ideally not happen if startup loads parameters,
            # but good to handle defensively.
            print("Warning: No system parameters document found in the database.")
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="System parameters document not found."
            )

    except Exception as e:
        # Catch any unexpected errors during the fetch operation
        print(f"An unexpected error occurred while fetching system parameters: {e}")
        # Include traceback for unexpected errors
        traceback.print_exc() # Use traceback.print_exc() for detailed error printing

        # Raise an HTTP exception to return an error response to the client
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An unexpected error occurred while fetching system parameters: {e}"
        )

