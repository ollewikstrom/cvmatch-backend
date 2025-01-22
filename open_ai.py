import json
import asyncio
import os
from openai import AzureOpenAI
from dotenv import load_dotenv


load_dotenv()

# gets the API Key from environment variable AZURE_OPENAI_API_KEY
client = AzureOpenAI(
    api_version="2024-08-01-preview",
    azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
)

def get_response(cv_text, job_listing):

    prompt_string = (
    f"Given the job listing: '{job_listing}', and this cv \n\n{cv_text}.\n"
    "Check how well the cv matches the demands of the job listing. If a skill is a perfect match in area and experience, "
    'provide it with a label of "MATCH". If a skill is not perfectly matched, but is similar to another skill, provide it '
    'with a label of "PARTIAL". If a skill is not matched, provide it with a label of "MISSING". If it is unclear if a '
    'skill is present or not, provide it with a label of "UNSURE". \n\n'
    "You should return a JSON object. The structure of the object should be this: \n"
    "```{ \n"
    '    "summary": <a flowing text of no more than 150 words that describes how well the cv matches the job listing>,\n'
    '    "percentage_match": <your own rating of how compatible the cv is to the prospect>,\n'
    '    "skills": [\n'
    '        { "skill": <name of the skill>, "reason": <a short reason of why it matches, or a reason for why another, \n'
    '        similar skill might be relevant>, "levelOfImportance": <the level of importance the skill has in the job listing, '
    'for example "MUST HAVE", "SHOULD HAVE" etc>, "matchLabel": <the provided match label>},\n'
    "    ], \n"
    "}```"
)
    # Prompt the model to just generate what is missing and not missing, and then prompt it again to see if any of the missing skills have similar skills that are present
    # Prompt the model again with the response it generated, the cv and job listing, and allow it to make edits to the original response in order for it to be more accurate
    completion = client.chat.completions.create(
        model="gpt-4o-mini",  # Ensure the model matches your deployment
        messages=[
            {
                "role": "user",
                "content": prompt_string,
            },
        ],
        temperature=0.7,
    )

    # Extract the response
    json_response = completion.choices[0].message.content.strip()

    # Remove ```json from the response
    json_response = json_response.replace("```json", "").replace("```json", "").replace("```", "")
 

    # convert to json
    try:
        json_object = json.loads(r"""{}""".format(json_response))
    except json.JSONDecodeError:
        # If the JSON is invalid, return nothing
        return 

    print(json_object["percentage_match"])

    return json_object