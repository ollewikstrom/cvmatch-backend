import io
import asyncio
import os
import logging
import sys
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends, UploadFile, Form
from pydantic import BaseModel
from sqlalchemy.orm import Session
from uvicorn.config import LOGGING_CONFIG
from time import perf_counter  # Import for timing
from database import (
    MatchGroup,
    Match,
    db_session,
    init_db,
    save_openai_response,
    with_retry,
)
from open_ai import get_response
import scrape_job_two
import cv_to_json

# Load the environment variables
load_dotenv()

# Apply Uvicorn's logging configuration to all logs
logging.config.dictConfig(LOGGING_CONFIG)

# Ensure logging goes to stdout explicitly
for handler in logging.getLogger().handlers:
    handler.stream = sys.stdout  # Redirect logs to stdout

logger = logging.getLogger("uvicorn")  # Use Uvicorn's logger instead of __name__

logger.info("Logging is set up correctly!")
logger.info("✅ This should appear in Azure Log Stream!")
logger.error("❌ This is an error message!")
# Initialize FastAPI
app = FastAPI()

# Initialize the database
init_db()


# Pydantic models for request and response validation
class JobListingRequest(BaseModel):
    job_listing: str


class MatchIDResponse(BaseModel):
    match_id: str


class MatchGroupResponse(BaseModel):
    match_group_id: str
    match_ids: list[str]  # A list of match IDs


class MatchResponse(BaseModel):
    match_id: str
    summary: dict
    skills: list


@app.post("/process", response_model=MatchGroupResponse)
async def process_cv_and_job(
    job_listing: str = Form(...),
    cv_files: list[UploadFile] = Form(...),
    db: Session = Depends(db_session),
):
    if len(cv_files) > 5:
        raise HTTPException(
            status_code=400, detail="You can upload a maximum of 5 files."
        )

    logger.info(
        f"Processing {len(cv_files)} CV files for job listing: {job_listing[:50]}"
    )

    # Track overall execution time
    overall_start_time = perf_counter()

    # Time tracking: Job listing processing
    job_start_time = perf_counter()
    processed_job_listing = await asyncio.to_thread(scrape_job_two.fetch, job_listing)
    logger.info(
        f"Job listing processed in {perf_counter() - job_start_time:.2f} seconds."
    )

    try:
        # Create a new MatchGroup
        match_group = MatchGroup(job_listing_url=job_listing)
        db.add(match_group)
        db.commit()
        db.refresh(match_group)

        async def process_single_cv(cv_file):
            cv_start_time = perf_counter()
            cv_data = await process_cv_file(cv_file)
            logger.info(
                f"CV {cv_file.filename} processed in {perf_counter() - cv_start_time:.2f} seconds."
            )

            ai_start_time = perf_counter()
            open_ai_response = await asyncio.to_thread(
                get_response, cv_data, processed_job_listing
            )
            logger.info(
                f"AI response for {cv_file.filename} generated in {perf_counter() - ai_start_time:.2f} seconds."
            )

            # Save response as a Match
            match_id = save_with_retry(
                open_ai_response,
                cv_file.filename,
                job_listing,
                job_listing,
            )

            # Link Match to MatchGroup
            match = db.query(Match).filter_by(id=match_id).first()
            match.match_group_id = match_group.id
            db.add(match)
            return match_id

        # Process all CV files in parallel
        match_ids = await asyncio.gather(
            *[process_single_cv(cv_file) for cv_file in cv_files]
        )

        db.commit()  # Commit all changes

        logger.info(
            f"Overall processing completed in {perf_counter() - overall_start_time:.2f} seconds."
        )

        return {"match_group_id": match_group.id, "match_ids": match_ids}

    except Exception as e:
        logger.error(f"Error processing files: {e}")
        db.rollback()
        raise HTTPException(status_code=500, detail="Error processing the files.")


@app.get("/match_group/{match_group_id}")
async def get_match_group(match_group_id: str, db: Session = Depends(db_session)):
    """
    Fetch match group details, including matches and their associated skills in prioritized order.
    """
    # Query the MatchGroup by ID
    match_group = db.query(MatchGroup).filter_by(id=match_group_id).first()
    if not match_group:
        raise HTTPException(
            status_code=404, detail=f"No match group found with ID {match_group_id}"
        )

    # Build the response
    return {
        "match_group_id": match_group.id,
        "job_listing_url": match_group.job_listing_url,
        "matches": [
            {
                "match_id": response.id,
                "cv_name": response.cv_name,
                "summary": response.summary,
                "skills": sorted(
                    [
                        {
                            "skill_name": skill.skill_name,
                            "reason": skill.reason,
                            "level_of_importance": skill.level_of_importance,
                            "match_label": skill.match_label,
                            "order_index": skill.order_index,  # Include order_index for clarity (optional)
                        }
                        for skill in response.skills
                    ],
                    key=lambda x: x["order_index"],  # Sort skills by their order_index
                ),
            }
            for response in match_group.responses
        ],
    }


# Helper function to process CV file
async def process_cv_file(cv_file: UploadFile):
    try:
        content_bytes = io.BytesIO(await cv_file.read())
        return cv_to_json.parse_docx_to_json(content_bytes, cv_file.filename)
    except Exception as e:
        logger.error(f"Error processing CV file {cv_file.filename}: {str(e)}")
        raise HTTPException(status_code=500, detail="Error processing CV file")


# Save OpenAI response with retry logic
@with_retry(retries=3, delay=5)
def save_with_retry(response_data, cv_name, job_listing_name, job_listing_url):
    return save_openai_response(
        response_data, cv_name, job_listing_name, job_listing_url
    )


if __name__ == "__main__":
    import uvicorn

    # Run the app with Uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
