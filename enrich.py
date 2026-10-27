from google import genai
from google.genai import errors
from pydantic import BaseModel
from scape import get_description

client=genai.Client()

MODELS=["gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-2.5-flash"]


class Company(BaseModel):
    industry: str
    what_they_sell: str
    target_customer: str


def enrich(url):
    site=get_description(url)
    name=site["name"]

    if site["error"]:
        return {"name": name, "company": None, "error": site["error"]}

    if site["description"] is None and site["about"] is None:
        return {"name": name, "company": None, "error": "No description could be found"}

    prompt=f"""Here is information from a company's website.
Title: {site["title"]}
Description: {site["description"] or "Not available"}
About page: {site["about"] or "Not available"}

Fill in the fields using only this information.
Be specific: name the actual product or service and the actual type of customer."""

    for model in MODELS:
        try:
            response=client.models.generate_content(
                model=model,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": Company,
                },
            )
            return {"name": name, "company": response.parsed, "error": None}
        except errors.ServerError:
            print(f"{model} is busy, trying the next one")

    return {"name": name, "company": None, "error": "All models are currently busy, please retry in a minute."}


if __name__ == "__main__":
    result=enrich("stripe.com")

    if result["error"]:
        print(result["error"])
    else:
        print(result["company"])