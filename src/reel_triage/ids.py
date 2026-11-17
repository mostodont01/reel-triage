"""Instagram post IDs (shortcodes) and links.

Share links carry tracking parameters (?igsh=…, ?srtk=…) tied to the sharer's
account, so only the shortcode is ever stored.
"""

import re

_URL = re.compile(
    r"instagram\.com/(?:[A-Za-z0-9_.]+/)?(?:p|reel|reels|tv)/([A-Za-z0-9_-]{5,40})"
)
_CODE = re.compile(r"^[A-Za-z0-9_-]{5,40}$")


def parse(text: str) -> str | None:
    """Shortcode from a link or a bare shortcode, else None."""
    text = text.strip()
    match = _URL.search(text)
    if match:
        return match.group(1)
    if _CODE.match(text) and not text.startswith("-"):
        return text
    return None


def find_all(text: str) -> list[str]:
    """All shortcodes in links inside a piece of text, in order, no duplicates."""
    return list(dict.fromkeys(_URL.findall(text)))


def url(code: str) -> str:
    return f"https://www.instagram.com/p/{code}/"
