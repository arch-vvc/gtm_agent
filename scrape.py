import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

headers={
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
}


def normalise_url(url):
    url=url.strip().lower()
    if "://" not in url:
        url="https://"+url
    parsed=urlparse(url)
    host=parsed.netloc.removeprefix("www.")
    if "." not in host:
        return None
    path=parsed.path.rstrip("/")
    return "https://"+host+path


def find_about_url(soup, base_url):
    for link in soup.find_all("a", href=True):
        href=link["href"].lower()
        if href.startswith("#"):
            continue
        text=link.get_text().lower()
        if "about" in href or "about" in text:
            return urljoin(base_url, link["href"])
    return None


def get_about_text(about_url):
    if about_url is None:
        return None
    try:
        response=httpx.get(about_url, headers=headers, follow_redirects=True, timeout=10)
    except httpx.HTTPError:
        return None
    
    if response.is_error:
        return None

    soup=BeautifulSoup(response.text, "html.parser")
    paragraphs=[p.get_text(" ", strip=True) for p in soup.find_all("p")]
    text=" ".join(p for p in paragraphs if len(p)>40)
    return text[:2000] or None


CUSTOMERS_HREF_PARTS=["/customers", "/customer-stories", "/case-studies", "/case-study", "/use-cases", "/use-case"]
CUSTOMERS_TEXT_PATTERN=re.compile(r"\b(customers|customer stories|case studies|use cases)\b")
# "For customers" is usually a login or help menu, not a page that names buyers.
NOT_CUSTOMERS_TEXT="for customers"
SKIPPED_HREF_PREFIXES=("#", "mailto:", "tel:", "javascript:")


def find_customers_url(soup, base_url):
    links=[]
    for link in soup.find_all("a", href=True):
        href=link["href"].strip()
        if href.lower().startswith(SKIPPED_HREF_PREFIXES):
            continue
        links.append(link)

    for link in links:
        path=urlparse(link["href"].strip()).path.lower()
        if any(part in path for part in CUSTOMERS_HREF_PARTS):
            return urljoin(base_url, link["href"].strip())

    for link in links:
        text=" ".join(link.get_text().split()).lower()
        if NOT_CUSTOMERS_TEXT in text:
            continue
        if CUSTOMERS_TEXT_PATTERN.search(text):
            return urljoin(base_url, link["href"].strip())
    return None


def get_customers_text(customers_url):
    if customers_url is None:
        return None
    try:
        response=httpx.get(customers_url, headers=headers, follow_redirects=True, timeout=10)
    except httpx.HTTPError:
        return None

    if response.is_error:
        return None

    soup=BeautifulSoup(response.text, "html.parser")
    pieces=[]
    for tag in soup.find_all(["h1", "h2", "h3", "p", "img"]):
        if tag.name == "img":
            # Customer logos are usually images, so the alt text holds the company name.
            piece=re.sub(r"\s+logo$", "", " ".join((tag.get("alt") or "").split()), flags=re.IGNORECASE)
        else:
            piece=tag.get_text(" ", strip=True)
            if tag.name == "p" and len(piece) <= 40:
                continue
        if piece and piece not in pieces:
            pieces.append(piece)
    text="\n".join(pieces)
    return text[:2000] or None


def get_description(url):
    url=normalise_url(url)

    name=urlparse(url).netloc.removeprefix("www.").split(".")[0].capitalize()

    try:
        response=httpx.get(url, headers=headers, follow_redirects=True, timeout=10)
    except httpx.HTTPError:
        return {"name": name, "title": None, "description": None, "about_url": None, "about": None, "customers_url": None, "customers": None, "error": "Could not reach site"}

    if response.is_error:
        return {"name": name, "title": None, "description": None, "about_url": None, "about": None, "customers_url": None, "customers": None, "error": f"Site returned {response.status_code}"}
   
    soup=BeautifulSoup(response.text, "html.parser")

    title_tag=soup.find("title")
    if title_tag is None:
        title=name
    else:
        title=title_tag.text.strip()

    tag=soup.find("meta", attrs={"name": re.compile("^description$", re.IGNORECASE)}) or soup.find("meta", attrs={"property": "og:description"})
    description=tag.get("content") if tag else None

    about_url=find_about_url(soup, str(response.url))
    about=get_about_text(about_url)

    customers_url=find_customers_url(soup, str(response.url))
    customers=get_customers_text(customers_url)

    return {
        "name": name,
        "title": title,
        "description": description,
        "about_url": about_url,
        "about": about,
        "customers_url": customers_url,
        "customers": customers,
        "error": None,
    }


if __name__ == "__main__":
    print(get_description("nexturn.com"))
    print(get_description("stripe.com"))
    print(get_description("apple.com"))