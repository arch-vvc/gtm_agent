import re
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin

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
        text=link.get_text().lower()
        if "about" in href or "about" in text:
            return urljoin(base_url, link["href"])
    return None


def get_description(url):
    url=normalise_url(url)

    name=urlparse(url).netloc.removeprefix("www.").split(".")[0].capitalize()

    try:
        response=httpx.get(url, headers=headers, follow_redirects=True, timeout=10)
    except httpx.HTTPError:
        return {"name": name, "title": None, "description": None, "about_url": None, "error": "Could not reach site"}

    soup=BeautifulSoup(response.text, "html.parser")

    title_tag=soup.find("title")
    if title_tag is None:
        title=name
    else:
        title=title_tag.text.strip()

    about_url=find_about_url(soup, str(response.url))

    tag=soup.find("meta", attrs={"name": re.compile("^description$", re.IGNORECASE)}) or soup.find("meta", attrs={"property": "og:description"})
    description=tag.get("content") if tag else None

    return {"name": name, "title": title, "description": description, "about_url": about_url, "error": None}


if __name__ == "__main__":
    print(get_description("nexturn.com"))
    print(get_description("stripe.com"))
    print(get_description("apple.com"))