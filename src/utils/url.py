"""
URL normalization utility for consistent URL handling across the system.
"""
import re
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

def normalize_url(url: str) -> str:
    """
    Normalize a URL to a consistent format for deduplication and ID generation.

    Steps:
    1. Remove URL anchor (#)
    2. Remove tracking parameters (utm_*, ref, etc.)
    3. Unify HTTP/HTTPS protocol (convert to HTTPS)
    4. Remove trailing slashes
    5. Handle www subdomain consistency (remove www.)
    6. Convert host to lowercase

    Args:
        url: Raw URL to normalize

    Returns:
        Normalized URL string
    """
    if not url:
        return ""

    # Parse URL
    parsed = urlparse(url)

    # Unify protocol to HTTPS
    scheme = "https"

    # Process host: remove www. and lowercase
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]

    # Remove anchor
    path = parsed.path
    query = parsed.query

    # Remove tracking parameters
    if query:
        query_params = parse_qs(query)
        # Filter out tracking parameters
        filtered_params = {k: v for k, v in query_params.items()
                          if not k.startswith("utm_")
                          and k not in ["ref", "source", "campaign", "medium", "term"]}
        query = urlencode(filtered_params, doseq=True) if filtered_params else ""

    # Remove trailing slash from path and make lowercase
    if path.endswith("/") and len(path) > 1:
        path = path[:-1]
    path = path.lower()

    # Reconstruct URL
    normalized = urlunparse((scheme, netloc, path, "", query, ""))

    return normalized
