import re
import httpx
from bs4 import BeautifulSoup
from urllib.parse import urlparse

headers={
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
}

def normalise_url(url):
    url=url.strip()
    if "://" not in url:
        url="https://"+url
    host=urlparse(url).netloc.removeprefix("www.")
    if "." not in host:
        return None
    return url

def get_description(url):
    if "://" not in url:
        url=normalise_url(url)

    name=urlparse(url).netloc.removeprefix("www.").split(".")[0].capitalize()

    try:
        response=httpx.get(url, headers=headers, follow_redirects=True, timeout=10)
    except httpx.HTTPError:
        return {"name": name, "title": None, "description": None, "error": "Could not reach site"}

    soup=BeautifulSoup(response.text, "html.parser")

    title_tag=soup.find("title")
    if title_tag is None:
        title=name
    else:
        title=title_tag.text.strip()

    tag=soup.find("meta", attrs={"name": re.compile("^description$", re.IGNORECASE)}) or soup.find("meta", attrs={"property": "og:description"})
    if tag is None:
        return {"name": name, "title": title, "description": None, "error": None}
    return {"name": name, "title": title, "description": tag.get("content"), "error": None}


if __name__ == "__main__":
    print(get_description("nexturn.com"))
    print(get_description("https://www.apple.com"))