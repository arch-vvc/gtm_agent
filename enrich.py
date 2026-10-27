from google import genai
from google.genai import types
import httpx
from google.genai import errors
from groq import Groq
import groq
from pydantic import BaseModel
from scape import get_description
import redis

r=redis.Redis(host="redis", decode_responses=True, socket_timeout=30)
COOLDOWN_SECONDS=120

gemini_client=genai.Client(http_options=types.HttpOptions(timeout=30000))
groq_client=Groq(timeout=30)
GEMINI_MODELS=["gemini-3.8-flash", "gemini-3.5-flash", "gemini-3.1-flash-lite"]
GROQ_MODEL="openai/gpt-oss-20b"


class Company(BaseModel):
    industry: str
    what_they_sell: str
    target_customer: str


def ask_gemini(prompt):
    for model in GEMINI_MODELS:
        if r.exists(f"cooldown:{model}"):
            print(f"{model} is cooling down, skipping")
            continue
        print(f"Trying {model}")
        try:
            response=gemini_client.models.generate_content(
                model=model,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_schema": Company,
                },
            )
            print(f"{model} answered")
            return response.parsed, model
        except (errors.ServerError, httpx.TimeoutException):
            print(f"{model} is busy, cooling down for {COOLDOWN_SECONDS}s")
            r.set(f"cooldown:{model}", 1, ex=COOLDOWN_SECONDS)
    return None, None


def ask_groq(prompt):
    print("Trying Groq")
    try:
        response=groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "company",
                    "strict": True,
                    "schema": {**Company.model_json_schema(), "additionalProperties": False},
                },
            },
        )
        print("Groq answered")
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
    print(f"Scraping {url}")
    site=get_description(url)
    print("Scrape done, asking LLM")
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