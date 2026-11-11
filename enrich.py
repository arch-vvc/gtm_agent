import os

import groq
import httpx
import redis
from google import genai
from google.genai import errors, types
from groq import Groq
from pydantic import BaseModel

from junk import describe_answer, is_junk, junk_fields  # noqa: F401 (is_junk is re exported)
from scrape import get_description

REDIS_HOST=os.environ.get("REDIS_HOST", "redis")
r=redis.Redis(host=REDIS_HOST, decode_responses=True, socket_timeout=30)
COOLDOWN_SECONDS=120

gemini_client=genai.Client(http_options=types.HttpOptions(timeout=30000))
groq_client=Groq(timeout=30)
GEMINI_MODELS=["gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-3.8-flash"]
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
        except errors.ServerError:
            print(f"{model} returned a server error, cooling down for {COOLDOWN_SECONDS}s")
            r.set(f"cooldown:{model}", 1, ex=COOLDOWN_SECONDS)
        except httpx.TimeoutException:
            print(f"{model} timed out, cooling down for {COOLDOWN_SECONDS}s")
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
    except (groq.InternalServerError, groq.RateLimitError, groq.APIConnectionError):
        print("Groq is busy too")
        return None, None


PROVIDERS=[ask_gemini, ask_groq]


def ask(prompt):
    for provider in PROVIDERS:
        company, model=provider(prompt)
        if company:
            return company, model
    return None, None


def result(name, company=None, model=None, error=None, domain=None):
    return {"name": name, "company": company, "model": model, "error": error, "domain": domain}


def enrich(url):
    print(f"Scraping {url}")
    site=get_description(url)
    print("Scrape done")
    name=site["name"]
    domain=site.get("domain")

    if site["error"]:
        return result(name, error=site["error"], domain=domain)

    if site["description"] is None and site["about"] is None:
        return result(name, error="No description could be found", domain=domain)

    lines=["Here is information from a company's website.", f"Title: {site['title']}"]
    if site["description"]:
        lines.append(f"Description: {site['description']}")
    if site["about"]:
        lines.append(f"About page: {site['about']}")
    if site.get("customers"):
        lines.append(f"Customers page: {site['customers']}")
    lines.append("")
    lines.append("Fill in the fields using only this information.")
    lines.append("If a field cannot be determined from this information, answer exactly UNKNOWN for that field.")
    lines.append("Be specific: name the actual product or service.")
    lines.append("For target_customer, name the type of buyer, meaning who pays for it, as industry, company size or job title.")
    if site.get("customers"):
        lines.append("A customers page is given, so base target_customer on the companies and use cases named there.")
    lines.append('For target_customer, never answer with a device, operating system or a generic user group such as "Mac and PC users".')
    prompt="\n".join(lines)

    print("Asking LLM")
    company, model=ask(prompt)
    if company is None:
        return result(name, error="All models are currently busy, please retry in a minute.", domain=domain)

    missing=junk_fields(company)
    if missing:
        answers=", ".join(f"{field} (answered '{describe_answer(getattr(company, field))}')" for field in missing)
        return result(
            name,
            error=(
                f"The model could not fill in {answers} from the site text. "
                "The site gave too little to go on, please check the site manually."
            ),
            domain=domain,
        )
    return result(name, company=company, model=model, domain=domain)


if __name__ == "__main__":
    output=enrich("stripe.com")

    if output["error"]:
        print(output["error"])
    else:
        print(output["model"], output["company"])