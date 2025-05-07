

# Starting the app server:

uvicorn backend.api.main:app --reload > logging.log 2>&1


# Run Pre_match Analysis:

curl -X POST "http://127.0.0.1:8000/analytic/run-predictions"



# Run Post_match Analysis for a Particular Date:

curl -X POST "http://127.0.0.1:8000/analytic/run-post-match-analysis/04-05-2025"

# Prediction Route Fetch '/analytic/predictions'


## Fetch all predictions (with default limit=100, skip=0):

curl "http://127.0.0.1:8000/analytic/predictions"

## Fetch predictions for a specific date: 
*(Replace 04-05-2025 with your desired date)*

curl "http://127.0.0.1:8000/analytic/predictions?target_date=04-05-2025"

## Fetch predictions where pre-match analysis is complete:

curl "http://127.0.0.1:8000/analytic/predictions?predict_status=true"

## Fetch predictions where pre-match analysis is NOT complete:

curl "http://127.0.0.1:8000/analytic/predictions?predict_status=false"

## Fetch predictions where post-match analysis is complete:

curl "http://127.0.0.1:8000/analytic/predictions?post_match_analysis_status=true"


## Fetch predictions where post-match analysis is NOT complete:

curl "http://127.0.0.1:8000/analytic/predictions?post_match_analysis_status=false"

## Fetch predictions for a specific home team:
*(Replace Brentford with a team name from your data)*

curl "http://127.0.0.1:8000/analytic/predictions?home_team=Brentford"

## Fetch predictions for a specific away team:
*(Replace Manchester Utd with a team name from your data)*

curl "http://127.0.0.1:8000/analytic/predictions?away_team=Manchester Utd"

## Fetch predictions for a specific competition:
*(Replace england with a competition name from your data)*

curl "http://127.0.0.1:8000/analytic/predictions?competition='England - Premier League'"

## Fetch predictions with a specific overall status:
*(Replace post_analysis_complete with a status like analysis_failed, post_analysis_fetch_failed, etc.)*

curl "http://127.0.0.1:8000/analytic/predictions?status=post_analysis_complete"


## **Combine filters**: Fetch predictions for a date where post-match analysis failed:
*(Replace date as needed)*

curl "http://127.0.0.1:8000/analytic/predictions?target_date=04-05-2025&post_match_analysis_status=false"


## **Combine filters**: Fetch predictions for a date between two specific teams:
(Replace date and teams as needed)

curl "http://127.0.0.1:8000/analytic/predictions?target_date=05-05-2025&home_team=Brighton&away_team=Newcastle Utd"

## **Combine filters**: Fetch predictions for a date, with pre-match complete and post-match failed:
*(Replace date as needed)*

curl "http://127.0.0.1:8000/analytic/predictions?target_date=05-05-2025&predict_status=true&post_match_analysis_status=false"


## Using limit and skip for pagination (e.g., fetch the next 10 results after the first 20):

curl "http://127.0.0.1:8000/analytic/predictions?limit=10&skip=20"
Combining filters with limit and skip:

## Combining filters with limit and skip:

curl "http://127.0.0.1:8000/analytic/predictions?target_date=05-05-2025&status=post_analysis_complete&limit=5&skip=0"


# Post match Route Fetch '/analytic/fetch-post-match-results'

## Fetch all documents for a date where post-match analysis completed 
*(Replace date as needed)*

curl "http://127.0.0.1:8000/analytic/fetch-results?target_date=04-05-2025&post_match_analysis_status=true"


## Fetch a specific match document by ID (will return 404 if not found or if post_match_analysis_status is NOT True, unless you remove that filter):
*(Replace YOUR_MATCH_ID_HERE with a real ID from your DB)*

curl "http://127.0.0.1:8000/analytic/fetch-results?match_id=YOUR_MATCH_ID_HERE"


## Fetch documents for a date where post-match analysis failed (e.g., due to MAX_TOKENS):
*(Replace date as needed. This should return the match(es) that failed analysis on that date, like the one that hit MAX_TOKENS in your logs).*

curl "http://127.0.0.1:8000/analytic/fetch-results?target_date=04-05-2025&post_match_analysis_status=false"

## Fetch documents for a date with a specific overall status (e.g., post_analysis_max_tokens):
*(Replace date as needed)*

curl "http://127.0.0.1:8000/analytic/fetch-results?target_date=04-05-2025&status=post_analysis_max_tokens"


## Combine filters: Fetch documents for a date, between specific teams, where post-match analysis completed:


curl "http://127.0.0.1:8000/analytic/fetch-results?target_date=05-05-2025&home_team=Brighton&away_team=Newcastle Utd&post_match_analysis_status=true"
(Replace date and teams as needed)

## Using limit and skip with date filter:

curl "http://127.0.0.1:8000/analytic/fetch-results?target_date=05-05-2025&post_match_analysis_status=true&limit=5&skip=0"
