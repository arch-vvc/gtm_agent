import os
import re
import string

import groq
import httpx
import redis
from google import genai
from google.genai import errors, types
from groq import Groq
from pydantic import BaseModel

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


# Unambiguous placeholders are junk when they start the answer as whole words,
# so "Not available, see site" is junk but "Nathan's bakeries" is not.
JUNK_PREFIXES=[
    "not available",
    "not specified",
    "not provided",
    "no information",
    "unavailable",
    "unspecified",
    "n/a",
]
# Ambiguous words are junk only when they are the whole answer,
# so "None" is junk but "None of the above insurance" is a real answer.
JUNK_WHOLE_ANSWERS={"na", "n a", "none", "unknown"}
JUNK_PATTERN=re.compile("^(" + "|".join(re.escape(phrase) for phrase in JUNK_PREFIXES) + r")(\W|$)")
# Curly single and double quotes, written as escapes to keep this file ASCII.
EDGE_CHARS=string.punctuation + string.whitespace + "‘’‚‛“”„‟"
NOT_APPLICABLE_PATTERN=re.compile(r"\bn\s*[/.]\s*a\b")


def normalise(value):
    text=str(value or "").strip(EDGE_CHARS)
    text=" ".join(text.lower().split())
    # "n.a", "n / a" and "n/a" all become "n/a"
    return NOT_APPLICABLE_PATTERN.sub("n/a", text)


def is_junk(value):
    cleaned=normalise(value)
    return cleaned == "" or cleaned in JUNK_WHOLE_ANSWERS or bool(JUNK_PATTERN.match(cleaned))


def junk_fields(company):
    fields={
        "industry": company.industry,
        "what_they_sell": company.what_they_sell,
        "target_customer": company.target_customer,
    }
    return [field for field, value in fields.items() if is_junk(value)]


def describe_answer(value):
    return " ".join(str(value or "").split())[:40]


def result(name, company=None, model=None, error=None):
    return {"name": name, "company": company, "model": model, "error": error}


def enrich(url):
    print(f"Scraping {url}")
    site=get_description(url)
    print("Scrape done")
    name=site["name"]

    if site["error"]:
        return result(name, error=site["error"])

    if site["description"] is None and site["about"] is None:
        return result(name, error="No description could be found")

    lines=["Here is information from a company's website.", f"Title: {site['title']}"]
    if site["description"]:
        lines.append(f"Description: {site['description']}")
    if site["about"]:
        lines.append(f"About page: {site['about']}")
    lines.append("")
    lines.append("Fill in the fields using only this information.")
    lines.append("If a field cannot be determined from this information, answer exactly UNKNOWN for that field.")
    lines.append("Be specific: name the actual product or service and the actual type of customer.")
    prompt="\n".join(lines)

    print("Asking LLM")
    company, model=ask(prompt)
    if company is None:
        return result(name, error="All models are currently busy, please retry in a minute.")

    missing=junk_fields(company)
    if missing:
        answers=", ".join(f"{field} (answered '{describe_answer(getattr(company, field))}')" for field in missing)
        return result(
            name,
            error=(
                f"The model could not fill in {answers} from the site text. "
                "The site gave too little to go on, please check the site manually."
            ),
        )
    return result(name, company=company, model=model)


if __name__ == "__main__":
    output=enrich("stripe.com")

    if output["error"]:
        print(output["error"])
    else:
        print(output["model"], output["company"])