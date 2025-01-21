import io
import asyncio
import os
import logging
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends, UploadFile, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from time import perf_counter  # Import for timing
from database import ResponseSummary, db_session, init_db, save_openai_response, with_retry
from open_ai import get_response
import scrape_job_two
import cv_to_json

# Load the environment variables
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI
app = FastAPI()

# Initialize the database
init_db()

# Pydantic models for request and response validation
class JobListingRequest(BaseModel):
    job_listing: str

class MatchIDResponse(BaseModel):
    match_id: str

class MatchResponse(BaseModel):
    match_id: str
    summary: dict
    skills: list


@app.post("/process", response_model=MatchIDResponse)
async def process_cv_and_job(
    job_listing: str = Form(...),
    cv_file: UploadFile = Form(...),
    db: Session = Depends(db_session)
):
    """
    Process the CV file and job listing, then get an OpenAI response.
    """

    logger.info(f"Processing request with job listing: {job_listing[:50]} and file: {cv_file.filename}")
    try:
        total_start_time = perf_counter()  # Start total timing

        response_data = {}

        # Step 1: Process job listing
        step_start_time = perf_counter()
        if job_listing:
            response_data["job_listing"] = process_job_listing(job_listing)
        step_end_time = perf_counter()
        print(f"Step 1 (Process Job Listing): {step_end_time - step_start_time:.4f} seconds")

        # Step 2: Process CV file
        step_start_time = perf_counter()
        if cv_file:
            response_data["cv_data"] = await process_cv_file(cv_file)
        step_end_time = perf_counter()
        print(f"Step 2 (Process CV File): {step_end_time - step_start_time:.4f} seconds")

        # Step 3: Get OpenAI response
        step_start_time = perf_counter()
        if "cv_data" in response_data and "job_listing" in response_data:
            try:
                open_ai_response = await asyncio.to_thread(
                    get_response, response_data["cv_data"], response_data["job_listing"]
                )
            except Exception as e:
                logger.error(f"OpenAI request failed: {e}")
                raise HTTPException(status_code=500, detail="OpenAI request failed")

            if open_ai_response:
                response_data["open_ai_response"] = open_ai_response
                step_end_time = perf_counter()
                print(f"Step 3 (Get OpenAI Response): {step_end_time - step_start_time:.4f} seconds")

                # Step 4: Save OpenAI response
                step_start_time = perf_counter()
                response_id = save_with_retry(
                    response_data["open_ai_response"],
                    cv_file.filename,
                    response_data["job_listing"]["name"],
                    job_listing,
                )
                step_end_time = perf_counter()
                print(f"Step 4 (Save OpenAI Response): {step_end_time - step_start_time:.4f} seconds")

                response_data["match_id"] = response_id

                # Total time taken
                total_end_time = perf_counter()
                print(f"Total Time Taken: {total_end_time - total_start_time:.4f} seconds")

                logger.info(f"Successfully processed request. Match ID: {response_id}")

                return {"match_id": response_id}
            else:
                logger.error(f"Error processing request: {e}")
                raise HTTPException(status_code=500, detail="Error processing the CV and job listing")
        else:
            logger.error(f"Error processing request: {e}")
            raise HTTPException(status_code=400, detail="Missing CV or Job Listing data")

    except Exception as e:
        # Log the error
        print(f"Error: {str(e)}")
        raise HTTPException(status_code=500, detail="An error occurred while processing your request.")


@app.get("/match/{match_id}", response_model=MatchResponse)
async def get_match(match_id: str, db: Session = Depends(db_session)):
    """
    Fetch and return the match details by match ID.
    """
    step_start_time = perf_counter()
    response_summary = db.query(ResponseSummary).options(joinedload(ResponseSummary.skills)).filter_by(id=match_id).first()
    if not response_summary:
        step_end_time = perf_counter()
        print(f"Step (Fetch Match Details - Not Found): {step_end_time - step_start_time:.4f} seconds")
        raise HTTPException(status_code=404, detail=f"No match found with ID {match_id}")

    step_end_time = perf_counter()
    print(f"Step (Fetch Match Details): {step_end_time - step_start_time:.4f} seconds")

    return {
        "match_id": match_id,
        "summary": {
            "id": response_summary.id,
            "summary": response_summary.summary,
            "cv_name": response_summary.cv_name,
            "job_listing_name": response_summary.job_listing_name,
            "job_listing_url": response_summary.job_listing_url,
            "created_at": response_summary.created_at,
        },
        "skills": [
            {
                "id": skill.id,
                "skill_name": skill.skill_name,
                "reason": skill.reason,
                "level_of_importance": skill.level_of_importance,
                "match_label": skill.match_label,
            }
            for skill in response_summary.skills
        ],
    }


# Helper function to process job listing
def process_job_listing(job_listing: str):
    try:
        return scrape_job_two.fetch(job_listing)
    except Exception as e:
        print(f"Error fetching job listing: {str(e)}")
        raise HTTPException(status_code=500, detail="Error fetching job listing")


# Helper function to process CV file
async def process_cv_file(cv_file: UploadFile):
    try:
        content_bytes = io.BytesIO(await cv_file.read())
        return cv_to_json.parse_docx_to_json(content_bytes, cv_file.filename)
    except Exception as e:
        print(f"Error processing CV file: {str(e)}")
        raise HTTPException(status_code=500, detail="Error processing CV file")


# Save OpenAI response with retry logic
@with_retry(retries=3, delay=5)
def save_with_retry(response_data, cv_name, job_listing_name, job_listing_url):
    return save_openai_response(response_data, cv_name, job_listing_name, job_listing_url)


if __name__ == "__main__":
    import uvicorn

    # Run the app with Uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
