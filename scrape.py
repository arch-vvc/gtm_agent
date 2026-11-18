import html
import ipaddress
import json
import re
import socket
from urllib.parse import quote, unquote, urljoin, urlparse

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


REFUSED_MESSAGE="Refused: not a public web address"
ALLOWED_PORTS={80, 443}
MAX_REDIRECTS=5
MAX_BODY_BYTES=2*1024*1024
REDIRECT_STATUSES={301, 302, 303, 307, 308}
BLOCKED_HOST_SUFFIXES=(".local", ".internal", ".localhost")
# Tests set this to an httpx.MockTransport so nothing touches the network.
DEFAULT_TRANSPORT=None


class RefusedURL(Exception):
    def __init__(self):
        super().__init__(REFUSED_MESSAGE)


class FetchedPage:
    """The parts of a response the scraper uses, with the body already capped."""

    def __init__(self, status_code, url, text):
        self.status_code=status_code
        self.url=url
        self.text=text

    @property
    def is_error(self):
        return self.status_code >= 400


def resolve_host(host):
    """Every address a host resolves to, as strings. Raises OSError when it does not resolve."""
    return [info[4][0] for info in socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)]


def is_public_address(address):
    ip=ipaddress.ip_address(address.split("%")[0])
    if ip.version == 6 and ip.ipv4_mapped is not None:
        ip=ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def check_public_url(url, resolver=None):
    """Raise RefusedURL unless the URL is http(s) on port 80 or 443 and every address of its host is public.

    Returns the addresses that passed, so the caller can connect to one of them."""
    resolver=resolver or resolve_host
    try:
        parsed=urlparse(url)
        port=parsed.port
    except ValueError:
        raise RefusedURL() from None
    host=(parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme not in ("http", "https") or not host:
        raise RefusedURL()
    if port is not None and port not in ALLOWED_PORTS:
        raise RefusedURL()
    if host == "localhost" or host.endswith(BLOCKED_HOST_SUFFIXES):
        raise RefusedURL()
    try:
        addresses=[str(ipaddress.ip_address(host))]
    except ValueError:
        try:
            addresses=resolver(host)
        except OSError as error:
            raise httpx.ConnectError(f"Could not resolve {host}") from error
    if not addresses or not all(is_public_address(address) for address in addresses):
        raise RefusedURL()
    return addresses


def read_capped(response):
    body=bytearray()
    for chunk in response.iter_bytes():
        body.extend(chunk)
        if len(body) >= MAX_BODY_BYTES:
            del body[MAX_BODY_BYTES:]
            break
    return bytes(body).decode(response.encoding or "utf-8", errors="replace")


def fetch(url, resolver=None, transport=None):
    """GET a page. Checks the first URL and every redirect hop, follows at most 5, reads at most 2 MB.

    Raises RefusedURL for a non public address and an httpx error for anything unreachable.
    """
    transport=transport or DEFAULT_TRANSPORT
    with httpx.Client(headers=headers, timeout=10, follow_redirects=False, transport=transport) as client:
        for _ in range(MAX_REDIRECTS+1):
            address=check_public_url(url, resolver)[0]
            # Connect to the address that passed the check, not to a second lookup of the name.
            # The Host header and the https certificate name stay those of the original host.
            target=httpx.URL(url)
            pinned=target.copy_with(host=address)
            request=client.build_request("GET", pinned, headers={"Host": target.netloc.decode()}, extensions={"sni_hostname": target.host})
            response=client.send(request, stream=True)
            try:
                location=response.headers.get("location")
                if response.status_code in REDIRECT_STATUSES and location:
                    url=str(target.join(location))
                    continue
                return FetchedPage(response.status_code, target, read_capped(response))
            finally:
                response.close()
    raise httpx.TooManyRedirects(f"More than {MAX_REDIRECTS} redirects")


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
        response=fetch(about_url)
    except (httpx.HTTPError, RefusedURL):
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
        response=fetch(careers_url)
    except (httpx.HTTPError, RefusedURL):
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
        response=fetch(customers_url)
    except (httpx.HTTPError, RefusedURL):
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


MAX_JOB_TEXT=3000
GREENHOUSE_HOSTS={"job-boards.greenhouse.io", "boards.greenhouse.io"}
# The public posting APIs of each job board. {board} and {id} are percent encoded before use.
JOB_APIS={
    "greenhouse": "https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{id}",
    "lever": "https://api.lever.co/v0/postings/{board}/{id}",
    "ashby": "https://api.ashbyhq.com/posting-api/job-board/{board}",
}


def parse_job_url(url):
    """Return (job board, board name, job id) for a Greenhouse, Lever or Ashby posting link, else None."""
    if not isinstance(url, str) or not url.strip():
        return None
    parsed=urlparse(url.strip())
    host=(parsed.hostname or "").lower()
    parts=[unquote(part) for part in parsed.path.split("/") if part]
    if host in GREENHOUSE_HOSTS and len(parts) >= 3 and parts[1] == "jobs":
        return ("greenhouse", parts[0], parts[2])
    if host == "jobs.lever.co" and len(parts) >= 2:
        return ("lever", parts[0], parts[1])
    if host == "jobs.ashbyhq.com" and len(parts) >= 2:
        return ("ashby", parts[0], parts[1])
    return None


def tidy(text):
    return " ".join(text.split()) if isinstance(text, str) else ""


def get_job_post(job_url):
    """Read a job posting from its board's public API. Returns {"title", "text"} or None.

    Only Greenhouse, Lever and Ashby links are read. Anything else, a posting that is no
    longer listed, a failed request or an unreadable answer gives None, so the caller
    carries on with the company site alone. The request goes through fetch(), so private
    addresses are refused and the body is capped.
    """
    parsed=parse_job_url(job_url)
    if parsed is None:
        return None
    board, board_name, job_id=parsed
    api=JOB_APIS[board].format(board=quote(board_name, safe=""), id=quote(job_id, safe=""))
    try:
        response=fetch(api)
    except (httpx.HTTPError, RefusedURL):
        return None
    if response.is_error:
        return None
    try:
        data=json.loads(response.text)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None

    if board == "greenhouse":
        # Greenhouse sends the description as HTML that has been entity escaped once.
        content=data.get("content")
        text=BeautifulSoup(html.unescape(content), "html.parser").get_text(" ", strip=True) if isinstance(content, str) else ""
        title=data.get("title")
    elif board == "lever":
        text=data.get("descriptionPlain")
        title=data.get("text")
    else:
        jobs=data.get("jobs")
        if not isinstance(jobs, list):
            return None
        posting=next((job for job in jobs if isinstance(job, dict) and job.get("id") == job_id), None)
        if posting is None:
            return None
        text=posting.get("descriptionPlain")
        title=posting.get("title")

    text=tidy(text)[:MAX_JOB_TEXT]
    if not text:
        return None
    return {"title": tidy(title) or None, "text": text}


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
        "job_title": None,
        "job_post": None,
        "domain": domain,
        "error": error,
    }


def get_description(url, job_url=None):
    raw_url=url
    url=normalise_url(url)
    if url is None:
        return failed_description(raw_url, name_from_host(urlparse(raw_url if "://" in raw_url else "//"+raw_url).hostname or ""), "", REFUSED_MESSAGE)

    name=name_from_host(urlparse(url).hostname or "")
    input_domain=host_of(url)

    try:
        response=fetch(url)
    except RefusedURL:
        return failed_description(url, name, input_domain, REFUSED_MESSAGE)
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
    job=get_job_post(job_url) if job_url else None

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
        "job_title": job["title"] if job else None,
        "job_post": job["text"] if job else None,
        "domain": host_of(str(response.url)) or input_domain,
        "error": None,
    }


if __name__ == "__main__":
    print(get_description("nexturn.com"))
    print(get_description("stripe.com"))
    print(get_description("apple.com"))