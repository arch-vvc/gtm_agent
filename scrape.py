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


def host_of(url):
    """Lowercased host of a URL with a leading www. removed."""
    return (urlparse(url).hostname or "").lower().removeprefix("www.")


SECOND_LEVEL_LABELS={"co", "com", "org", "net", "gov", "edu", "ac"}
IPV4_PATTERN=re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def name_from_host(host):
    """Company name from the main domain label, so blog.stripe.com and stripe.com both give Stripe.

    Handles two part suffixes like co.uk (shop.example.co.uk gives Example).
    A single label host or an IP address keeps the whole host.
    """
    host=host.lower().removeprefix("www.")
    labels=host.split(".")
    if len(labels) < 2 or IPV4_PATTERN.match(host):
        return host.capitalize()
    index=-2
    if len(labels) >= 3 and len(labels[-1]) == 2 and labels[-2] in SECOND_LEVEL_LABELS:
        index=-3
    return labels[index].capitalize()


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


CAREERS_WORDS=("career", "jobs", "join us", "join-us", "work with us", "work-with-us")

FDE_ROLE_PHRASES=(
    "forward deployed",
    "solutions engineer",
    "solution engineer",
    "solutions architect",
    "solution architect",
    "deployment engineer",
    "customer engineer",
    "implementation engineer",
)


def find_careers_url(soup, base_url):
    for link in soup.find_all("a", href=True):
        href=link["href"].lower()
        if href.startswith("#"):
            continue
        text=link.get_text().lower()
        if any(word in href or word in text for word in CAREERS_WORDS):
            return urljoin(base_url, link["href"])
    return None


def get_careers_text(careers_url):
    if careers_url is None:
        return None
    try:
        response=httpx.get(careers_url, headers=headers, follow_redirects=True, timeout=10)
    except httpx.HTTPError:
        return None

    if response.is_error:
        return None

    soup=BeautifulSoup(response.text, "html.parser")
    text=soup.get_text(" ", strip=True)
    return text[:20000] or None


def find_fde_roles(text):
    if not text:
        return []
    text=text.lower().replace("-", " ")
    return [phrase for phrase in FDE_ROLE_PHRASES if phrase in text]


CUSTOMERS_PATH_SEGMENTS={"customers", "customer-stories", "case-studies", "case-study", "use-cases", "use-case"}
# A path with one of these segments is a login, help or jobs page, not a page that names buyers.
BLOCKED_PATH_SEGMENTS={"login", "signin", "sign-in", "signup", "sign-up", "support", "help", "careers", "jobs"}
CUSTOMERS_TEXT_PATTERN=re.compile(r"\b(customers|customer stories|case studies|use cases)\b")
# "For customers" is usually a login or help menu, not a page that names buyers.
BLOCKED_TEXT_PARTS=("for customers", "login", "log in", "sign in", "signin", "support", "help")
SKIPPED_HREF_PREFIXES=("#", "mailto:", "tel:", "javascript:")


def same_site(url, base_url):
    host=urlparse(url).hostname or urlparse(base_url).hostname
    base_host=urlparse(base_url).hostname
    if not host or not base_host:
        return False
    return host.lower().removeprefix("www.")==base_host.lower().removeprefix("www.")


def is_customers_path(path):
    segments={segment for segment in path.lower().split("/") if segment}
    return bool(segments & CUSTOMERS_PATH_SEGMENTS) and not segments & BLOCKED_PATH_SEGMENTS


def find_customers_url(soup, base_url):
    links=[]
    for link in soup.find_all("a", href=True):
        href=link["href"].strip()
        if href.lower().startswith(SKIPPED_HREF_PREFIXES):
            continue
        if not same_site(urljoin(base_url, href), base_url):
            continue
        links.append(link)

    for link in links:
        if is_customers_path(urlparse(link["href"].strip()).path):
            return urljoin(base_url, link["href"].strip())

    for link in links:
        text=" ".join(link.get_text().split()).lower()
        if any(part in text for part in BLOCKED_TEXT_PARTS):
            continue
        if CUSTOMERS_TEXT_PATTERN.search(text):
            return urljoin(base_url, link["href"].strip())
    return None


MAX_ALT_LENGTH=60
# Strips " logo" or " logo image", and drops an alt that is only "logo".
LOGO_SUFFIX_PATTERN=re.compile(r"(?:^|\s+)logo(?:\s+image)?$", re.IGNORECASE)


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
            alt=" ".join((tag.get("alt") or "").split())
            if len(alt) > MAX_ALT_LENGTH:
                continue
            piece=LOGO_SUFFIX_PATTERN.sub("", alt)
        else:
            piece=tag.get_text(" ", strip=True)
            if tag.name == "p" and len(piece) <= 40:
                continue
        if piece and piece not in pieces:
            pieces.append(piece)
    text="\n".join(pieces)
    return text[:2000] or None


def failed_description(url, name, domain, error):
    return {
        "url": url,
        "name": name,
        "title": None,
        "description": None,
        "about_url": None,
        "about": None,
        "careers_url": None,
        "hiring_fde": None,
        "fde_roles": [],
        "customers_url": None,
        "customers": None,
        "domain": domain,
        "error": error,
    }


def get_description(url):
    url=normalise_url(url)

    name=name_from_host(urlparse(url).hostname or "")
    input_domain=host_of(url)

    try:
        response=httpx.get(url, headers=headers, follow_redirects=True, timeout=10)
    except httpx.HTTPError:
        return failed_description(url, name, input_domain, "Could not reach site")

    if response.is_error:
        return failed_description(url, name, input_domain, f"Site returned {response.status_code}")

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

    careers_url=find_careers_url(soup, str(response.url))
    careers_text=get_careers_text(careers_url)
    fde_roles=find_fde_roles(careers_text)
    if careers_text is None:
        hiring_fde=None
    else:
        hiring_fde=bool(fde_roles)

    customers_url=find_customers_url(soup, str(response.url))
    customers=get_customers_text(customers_url)

    return {
        "url": url,
        "name": name,
        "title": title,
        "description": description,
        "about_url": about_url,
        "about": about,
        "careers_url": careers_url,
        "hiring_fde": hiring_fde,
        "fde_roles": fde_roles,
        "customers_url": customers_url,
        "customers": customers,
        "domain": host_of(str(response.url)) or input_domain,
        "error": None,
    }


if __name__ == "__main__":
    print(get_description("nexturn.com"))
    print(get_description("stripe.com"))
    print(get_description("apple.com"))