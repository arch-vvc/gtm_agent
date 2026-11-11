import os
from typing import Literal

import groq
import httpx
import redis
from google import genai
from google.genai import errors, types
from groq import Groq
from pydantic import BaseModel, Field, ValidationError

import pitch
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
    cluster: Literal["A", "B", "C", "D", "E", "F"]
    cluster_reason: str
    customer_pain: str
    tailoring: list[str] = Field(min_length=3, max_length=3)
    pitch_note: str


def strict_schema(model):
    """Return the model's JSON schema in the shape Groq strict mode expects.

    Every object gets additionalProperties false and all its properties listed
    as required. minItems and maxItems are removed because Groq support for
    them is unconfirmed. Pydantic still enforces exactly 3 tailoring items when
    the answer is parsed.
    """
    return make_strict(model.model_json_schema())


def make_strict(schema):
    if isinstance(schema, list):
        return [make_strict(item) for item in schema]
    if not isinstance(schema, dict):
        return schema

    strict={}
    for key, value in schema.items():
        if key in ("minItems", "maxItems"):
            continue
        if key == "properties":
            strict[key]={name: make_strict(sub_schema) for name, sub_schema in value.items()}
        else:
            strict[key]=make_strict(value)

    if "properties" in strict:
        strict["required"]=list(strict["properties"])
        strict["additionalProperties"]=False
    return strict


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
                    "schema": strict_schema(Company),
                },
            },
        )
        print("Groq answered")
        return Company.model_validate_json(response.choices[0].message.content), GROQ_MODEL
    except (groq.InternalServerError, groq.RateLimitError, groq.APIConnectionError):
        print("Groq is busy too")
        return None, None
    except (ValidationError, ValueError):
        # Groq answered, but not with JSON that fits the schema (ValueError covers bad JSON).
        print("Groq returned an answer that does not fit the schema")
        return None, None


PROVIDERS=[ask_gemini, ask_groq]


def ask(prompt):
    for provider in PROVIDERS:
        company, model=provider(prompt)
        if company:
            return company, model
    return None, None


BUILT_DEMOS="""A: voice agent call QA. Simulated callers and a judge check that a voice agent follows a client script before go live.
B: invoice exception triage. Messy purchase order, invoice and payment exports go in, and every three way match mismatch is flagged and explained."""


def result(name, company=None, model=None, error=None, demo=None, pitch_note=None, pitch_error=None, site=None):
    site=site or {}
    return {
        "name": name,
        "company": company,
        "model": model,
        "error": error,
        "demo": demo,
        "pitch_note": pitch_note,
        "pitch_error": pitch_error,
        "careers_url": site.get("careers_url"),
        "hiring_fde": site.get("hiring_fde"),
    }


def hiring_signal(site):
    """One line about the careers page: roles found, none found, or not readable."""
    hiring_fde=site.get("hiring_fde")
    if hiring_fde is True:
        return "Hiring signal: careers page lists " + ", ".join(site.get("fde_roles") or [])
    if hiring_fde is False:
        return "Hiring signal: careers page lists no FDE role"
    return "Hiring signal: careers page not readable"


def build_prompt(site):
    labels="\n".join(f"{letter}: {label}" for letter, label in pitch.CLUSTER_LABELS.items())
    return f"""Here is information from a company's website.
Title: {site["title"]}
Description: {site["description"] or "Not available"}
About page: {site["about"] or "Not available"}
{hiring_signal(site)}

Fill in the fields using only this information.
Be specific: name the actual product or service and the actual type of customer.

cluster: pick the one letter that best fits the company.
{labels}

cluster_reason: one sentence that quotes the site's own words.
customer_pain: one sentence, grounded in the text, about the deployment pain the company's customers have.
tailoring: exactly 3 changes to make to a demo for this company, covering sample data, persona names and terminology.

pitch_note: a short note to the company's founder or FDE lead. These are the demos that exist:
{BUILT_DEMOS}
Rules for pitch_note:
1. At most 150 words, in British English.
2. No hyphens or dashes of any kind.
3. Conclusion first, then 2 or 3 reasons.
4. Name only products and customers that appear in the text above.
5. Never name the demo repos. Describe the demo in plain words instead.
6. The final line must be exactly: Loom: {pitch.LOOM} Repo: {pitch.REPO}"""


def enrich(url):
    print(f"Scraping {url}")
    site=get_description(url)
    print("Scrape done")
    name=site["name"]

    if site["error"]:
        return result(name, error=site["error"])

    if site["description"] is None and site["about"] is None:
        return result(name, error="No description could be found")

    prompt=build_prompt(site)

    print("Asking LLM")
    company, model=ask(prompt)
    if company is None:
        return result(name, error="All models are currently busy, please retry in a minute.")

    violations=pitch.pitch_violations(company.pitch_note, site)
    retry_failed=False
    if violations:
        print(f"Pitch note rejected, asking once more: {violations}")
        retry_prompt=(
            f"{prompt}\n\nYour previous pitch_note was rejected for: {'; '.join(violations)}. "
            "Write every field again and fix this."
        )
        retry_company, retry_model=ask(retry_prompt)
        if retry_company is None:
            retry_failed=True
        else:
            company, model=retry_company, retry_model
            violations=pitch.pitch_violations(company.pitch_note, site)

    pitch_note=company.pitch_note
    pitch_error=None
    if violations:
        pitch_note=None
        reason="the retry returned nothing" if retry_failed else "the retry was rejected too"
        pitch_error=f"Pitch note rejected and {reason}: " + "; ".join(violations)

    return result(
        name,
        company=company,
        model=model,
        demo=pitch.CLUSTER_DEMOS[company.cluster],
        pitch_note=pitch_note,
        pitch_error=pitch_error,
        site=site,
    )


if __name__ == "__main__":
    output=enrich("stripe.com")

    if output["error"]:
        print(output["error"])
    else:
        print(output["model"], output["company"])