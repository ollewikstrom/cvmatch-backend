import json
import os
import time
from openai import AzureOpenAI
from dotenv import load_dotenv


load_dotenv()

# gets the API Key from environment variable AZURE_OPENAI_API_KEY
client = AzureOpenAI(
    api_version="2024-08-01-preview",
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
    api_key=os.getenv("AZURE_OPENAI_API_KEY"),
)


def get_response(cv_text, job_listing):
    # Prompt the model to just generate what is missing and not missing, and then prompt it again to see if any of the missing skills have similar skills that are present
    # Prompt the model again with the response it generated, the cv and job listing, and allow it to make edits to the original response in order for it to be more accurate
    print("getting response")

    thread = client.beta.threads.create()

    # Add a user question to the thread
    message = client.beta.threads.messages.create(
        thread_id=thread.id, role="user", content=f"""{cv_text} {job_listing}"""
    )
    # Run the thread
    run = client.beta.threads.runs.create(
        thread_id=thread.id, assistant_id="asst_EklLhaFeVK6uaiJlJxVU0koa"
    )

    response = ""

    # Looping until the run completes or fails
    while run.status in ["queued", "in_progress", "cancelling"]:
        time.sleep(1)
        run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)

        if run.status == "completed":
            messages = client.beta.threads.messages.list(thread_id=thread.id)
            print("finished processing")
            for message in messages.data:
                if message.role == "assistant":  # Only process assistant messages
                    for content_block in message.content:
                        if hasattr(content_block, "text") and hasattr(
                            content_block.text, "value"
                        ):
                            response = content_block.text.value
        elif run.status == "requires_action":
            # the assistant requires calling some functions
            # and submit the tool outputs back to the run
            pass
        else:
            print(run.status)
    # Extract the response
    json_response = response

    # Remove ```json from the response
    json_response = (
        json_response.replace("```json", "").replace("```json", "").replace("```", "")
    )

    # convert to json
    try:
        json_object = json.loads(r"""{}""".format(json_response))
    except json.JSONDecodeError:
        # If the JSON is invalid, return nothing
        return
    return json_object


def summarize_skills_in_job_listing(job_listing):
    print("summarizing skills")
    print(job_listing)
    # Extract the skills from the job listing
    thread = client.beta.threads.create()

    # Add a user question to the thread
    message = client.beta.threads.messages.create(
        thread_id=thread.id, role="user", content=f"""{job_listing}"""
    )
    # Run the thread
    run = client.beta.threads.runs.create(
        thread_id=thread.id, assistant_id="asst_5nlvxmos0dnL9r21FkrNn3QN"
    )

    response = ""

    # Looping until the run completes or fails
    while run.status in ["queued", "in_progress", "cancelling"]:
        time.sleep(1)
        run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)

        if run.status == "completed":
            messages = client.beta.threads.messages.list(thread_id=thread.id)
            print("finished processing")
            for message in messages.data:
                if message.role == "assistant":  # Only process assistant messages
                    for content_block in message.content:
                        if hasattr(content_block, "text") and hasattr(
                            content_block.text, "value"
                        ):
                            response = content_block.text.value
        elif run.status == "requires_action":
            # the assistant requires calling some functions
            # and submit the tool outputs back to the run
            pass
        else:
            print(run.status)
    # Extract the response
    json_response = response

    # Remove ```json from the response
    json_response = (
        json_response.replace("```json", "").replace("```json", "").replace("```", "")
    )

    # convert to json
    try:
        json_object = json.loads(r"""{}""".format(json_response))
    except json.JSONDecodeError:
        # If the JSON is invalid, return nothing
        return

    print("Skills required: ", json_object)

    # Outout the json object to a file
    with open("jobskills.json", "w") as f:
        json.dump(json_object, f)

    return json_object
