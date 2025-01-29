import requests
import open_ai


def fetch(url):
    api_url = "https://app.whoz.com/api/shared/task/"
    # Extract the job ID from the URL
    job_id = url.split("/")[-1]
    response = requests.get(api_url + job_id)
    json_res = response.json()
    name, description, skills = (
        json_res["name"],
        json_res["description"],
        json_res["skills"],
    )
    jobData = {"name": name, "description": description, "required_skills": skills}
    processed_job_listing = open_ai.summarize_skills_in_job_listing(jobData)
    return processed_job_listing
