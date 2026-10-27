from google import genai
from google.genai import errors
from groq import Groq
import groq
from pydantic import BaseModel
from scape import get_description

gemini_client=genai.Client()
groq_client=Groq()

GEMINI_MODELS=["gemini-3.8-flash", "gemini-3.5-flash", "gemini-3.1-flash-lite"]
GROQ_MODEL="openai/gpt-oss-20b"


class Company(BaseModel):
    industry: str
    what_they_sell: str
    target_customer: str


def ask_gemini(prompt):
    for model in GEMINI_MODELS:
        try:
            response=gemini_client.models.generate_content(
                model=model,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": Company,
                },
            )
            return response.parsed, model
        except errors.ServerError:
            print(f"{model} is busy, trying the next one")
    return None, None


def ask_groq(prompt):
    try:
        response=groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "company",
                    "strict": True,
                    "schema": {**Company.model_json_schema(), "additionalProperties": False},                },
            },
        )
        return Company.model_validate_json(response.choices[0].message.content), GROQ_MODEL
    except (groq.InternalServerError, groq.RateLimitError):
        print("Groq is busy too")
        return None, None


PROVIDERS=[ask_gemini, ask_groq]


def ask(prompt):
    for provider in PROVIDERS:
        company, model=provider(prompt)
        if company:
            return company, model
    return None, None


def result(name, company=None, model=None, error=None):
    return {"name": name, "company": company, "model": model, "error": error}


def enrich(url):
    site=get_description(url)
    name=site["name"]

    if site["error"]:
        return result(name, error=site["error"])

    if site["description"] is None and site["about"] is None:
        return result(name, error="No description could be found")

    prompt=f"""Here is information from a company's website.
Title: {site["title"]}
Description: {site["description"] or "Not available"}
About page: {site["about"] or "Not available"}

Fill in the fields using only this information.
Be specific: name the actual product or service and the actual type of customer."""

    company, model=ask(prompt)
    if company is None:
        return result(name, error="All models are currently busy, please retry in a minute.")
    return result(name, company=company, model=model)


if __name__ == "__main__":
    output=enrich("stripe.com")

    if output["error"]:
        print(output["error"])
    else:
        print(output["model"], output["company"])