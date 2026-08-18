"""Best-effort suggestion of a series' total volume count.

There is no reliable, exhaustive database for this information, especially
for French-language comics. Two complementary approaches are used:

- AniList (free, no key): fairly reliable for manga, which are well
  referenced there with their official volume count.
- Google Books: failing that, a heuristic that looks for the highest volume
  number mentioned among the editions catalogued under this series name.
  It's an estimate, not official data — it must always be presented as
  such and never applied automatically without user confirmation.
"""

import re

import requests

TIMEOUT = 6

VOLUME_NUMBER_PATTERNS = [
    re.compile(r"tome\s*#?\s*(\d{1,3})", re.IGNORECASE),
    re.compile(r"\bvol(?:ume)?\.?\s*#?\s*(\d{1,3})", re.IGNORECASE),
    re.compile(r"\bt\.?\s*(\d{1,3})\b", re.IGNORECASE),
    re.compile(r"#(\d{1,3})"),
]


def _extract_volume_number(text):
    if not text:
        return None
    for pattern in VOLUME_NUMBER_PATTERNS:
        match = pattern.search(text)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                continue
    return None


def _from_anilist(series_name):
    """AniList explicitly references the volume count (`volumes` field) for
    most known manga: a fairly reliable source when it finds a match."""
    graphql_query = """
    query ($search: String) {
      Media(search: $search, type: MANGA) {
        title { romaji english }
        volumes
        status
      }
    }
    """
    try:
        response = requests.post(
            "https://graphql.anilist.co",
            json={"query": graphql_query, "variables": {"search": series_name}},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        media = response.json().get("data", {}).get("Media")
    except requests.RequestException:
        return None

    if not media or not media.get("volumes"):
        return None

    found_title = media["title"].get("romaji") or media["title"].get("english") or series_name
    return {
        "value": media["volumes"],
        "source": f"AniList — {found_title}",
        "reliable": media.get("status") == "FINISHED",
    }


def _from_google_books(series_name):
    """Heuristic: looks for the highest volume number mentioned among the
    editions referenced under this series name. Works mostly for
    well-catalogued series; treat as a low estimate, never as an official
    figure."""
    try:
        response = requests.get(
            "https://www.googleapis.com/books/v1/volumes",
            params={"q": f'intitle:"{series_name}"', "maxResults": 40},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        items = response.json().get("items", [])
    except requests.RequestException:
        return None

    numbers = []
    for item in items:
        info = item.get("volumeInfo", {})
        for field in (info.get("title"), info.get("subtitle")):
            number = _extract_volume_number(field)
            if number:
                numbers.append(number)

    if not numbers:
        return None

    return {
        "value": max(numbers),
        "source": "Google Books (estimation d'après les éditions référencées)",
        "reliable": False,
    }


def suggest_volume_count(series_name, item_type=None):
    """Returns {"value": int, "source": str, "reliable": bool}, or None if
    no suggestion could be found. `reliable=False` signals an estimate to
    verify rather than a confirmed official figure."""
    if item_type == "Manga":
        suggestion = _from_anilist(series_name)
        if suggestion:
            return suggestion

    return _from_google_books(series_name)
