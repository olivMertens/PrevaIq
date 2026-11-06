"""Where the loss happened: the claim address, geocoded once and kept with the case.

Geocoding uses Nominatim (OpenStreetMap): free and without a key, with an identifying
User-Agent and at most one request per second (usage policy). Each case is geocoded once:
the result, found or not, is stored with the case and reused until the address (or the
geocoding below) changes. Only a match in the claim's town is kept, never a namesake nearby.
"""

from __future__ import annotations

import json
import re
import threading
import time
import unicodedata
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any, Final, Optional

import requests

from .jurisdiction import application_jurisdiction
from .storage import load_file, save_application_file
from .utils import setup_logging

logger = setup_logging()

LOCATION_FILE: Final = ".location.json"
# Stored positions from another version of the geocoding below are computed again.
LOCATION_VERSION: Final = 1
NOMINATIM_URL: Final = "https://nominatim.openstreetmap.org/search"
USER_AGENT: Final = "PrevaIQ-Claims-Demo/1.0 (+https://github.com/olivMertens/PrevaIq)"
# Address fields by priority: where the loss happened, else the insured's address.
ADDRESS_FIELDS: Final = (
    (
        "loss",
        (
            "LieuSinistre",
            "AdresseSinistre",
            "LieuAccident",
            "AdresseRisque",
            "AdresseBien",
            "PropertyAddress",
            "LossLocation",
        ),
    ),
    ("insured", ("AdresseAssure", "InsuredAddress")),
)

# "33000 Bordeaux", "8400 Winterthur", "CH-9000 St. Gallen" (postcode digits by country).
_PLACE_RE: Final = {
    "FR": re.compile(r"(?<![\d'’.,])(\d{5})\s+([^\d,;()—–]+?)(?=\s*(?:[,;()—–]|\s-\s|$))"),
    "CH": re.compile(
        r"(?:\bCH-\s?|(?<![\d'’.,]))(\d{4})\s+([^\d,;()—–]+?)(?=\s*(?:[,;()—–]|\s-\s|$))"
    ),
}
_DESCRIPTION_SEPARATOR: Final = re.compile(r"\s+[-–—]\s+")
# OSM address parts naming the town. Not "municipality": in France it is the arrondissement, so
# "rue des Vignobles, 33000 Bordeaux" matched a street of Mérignac (arrondissement of Bordeaux).
_LOCALITY_KEYS: Final = ("city", "town", "village")

# Nominatim's matches for a search (its parameters) in a country, best first.
Search = Callable[[Mapping[str, str], str], list[dict[str, Any]]]


def field_value(fields: Mapping[str, Any], names: tuple[str, ...]) -> str:
    """First non-empty field among names, whatever its key prefix ("llm_extracted:", "file:")."""
    for name in names:
        wanted = name.lower()
        for key, entry in fields.items():
            label = entry.get("field_name") if isinstance(entry, Mapping) else None
            if str(label or str(key).split(":")[-1]).lower() != wanted:
                continue
            value = entry.get("value") if isinstance(entry, Mapping) else entry
            if value is not None and str(value).strip():
                return str(value).strip()
    return ""


def claim_address(fields: Mapping[str, Any]) -> Optional[tuple[str, str]]:
    """("loss" | "insured", address) of a claim, None without any address field."""
    for kind, names in ADDRESS_FIELDS:
        value = field_value(fields, names)
        if value:
            return kind, value
    return None


def address_place(address: str, country: str = "FR") -> Optional[tuple[str, str]]:
    """Postcode and town of an address: ("33000", "Bordeaux"), ("8400", "Winterthur")."""
    found = _PLACE_RE.get(country, _PLACE_RE["FR"]).search(re.sub(r"\s+", " ", address))
    if not found:
        return None
    town = re.sub(r"\bcedex\b.*$", "", found.group(2), flags=re.I).strip(" .-'’")
    return (found.group(1), town) if town else None


def geocode_searches(address: str, country: str = "FR") -> list[dict[str, str]]:
    """Nominatim searches to try in order: the street address, then the town.

    "Cave de la maison, 42 rue des Vignobles, 33000 Bordeaux - cave et sous-sol" gives the
    free-text search "42 rue des Vignobles, 33000 Bordeaux", then a structured search for the
    town Bordeaux with its postcode: it finds the town itself, not the middle of its postcode area.
    """
    text = re.sub(r"\s+", " ", address).strip()
    pattern = _PLACE_RE.get(country, _PLACE_RE["FR"])
    parts = [
        part.strip(" ,") for part in _DESCRIPTION_SEPARATOR.split(re.sub(r"\([^)]*\)", " ", text))
    ]
    parts = [part for part in parts if part]
    part = next((item for item in parts if pattern.search(item)), parts[0] if parts else "")
    segments = [segment.strip() for segment in part.split(",") if segment.strip()]
    # A description before the street ("Cave de la maison, 42 rue …") is not part of the address.
    while len(segments) > 1 and not re.search(r"\d", segments[0]):
        segments.pop(0)
    street = ", ".join(segments)
    place = address_place(text, country)

    searches = []
    if re.search(r"\d", street) and len(street) >= 6 and street != " ".join(place or ()):
        searches.append({"q": street})
    if place:
        searches.append({"city": place[1], "postalcode": place[0]})
    return searches


def map_address(address: str, country: str = "FR") -> str:
    """The address for map links: without its description ("— Salon"), else its town."""
    street = next(
        (search["q"] for search in geocode_searches(address, country) if "q" in search), None
    )
    place = address_place(address, country)
    return street or (" ".join(place) if place else address)


_throttle = threading.Lock()
_last_request = 0.0


def nominatim_search(
    search: Mapping[str, str], country: str, timeout: float = 6.0
) -> list[dict[str, Any]]:
    """Nominatim's best matches (at most 5) for a search in a country.

    ``search`` holds Nominatim's search parameters: ``q`` (free text), or ``city`` and
    ``postalcode`` (structured search).
    """
    global _last_request
    with _throttle:  # one request per second at most (Nominatim usage policy)
        wait = 1.1 - (time.monotonic() - _last_request)
        if wait > 0:
            time.sleep(wait)
        try:
            response = requests.get(
                NOMINATIM_URL,
                params={
                    **search,
                    "format": "jsonv2",
                    "limit": 5,
                    "addressdetails": 1,
                    "countrycodes": country.lower(),
                },
                headers={"User-Agent": USER_AGENT},
                timeout=timeout,
            )
        finally:
            _last_request = time.monotonic()
    response.raise_for_status()
    results = response.json()
    if not isinstance(results, list):
        return []
    hits = []
    for result in results:
        details = result.get("address") or {}
        hits.append(
            {
                "lat": float(result["lat"]),
                "lon": float(result["lon"]),
                "display_name": str(result.get("display_name") or ""),
                "house_number": str(details.get("house_number") or ""),
                "road": str(details.get("road") or ""),
                "postcode": str(details.get("postcode") or ""),
                "locality": next(
                    (str(details[key]) for key in _LOCALITY_KEYS if details.get(key)), ""
                ),
                "country_code": details.get("country_code"),
            }
        )
    return hits


def _simplified(text: str) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", " ", plain.lower()).strip()


def _in_town(hit: Mapping[str, Any], place: Optional[tuple[str, str]]) -> bool:
    """The match lies in the claim's town (same name or postcode), not in a namesake nearby."""
    if not place:
        return True
    postcode, town = place
    return _simplified(str(hit.get("locality") or "")) == _simplified(town) or (
        hit.get("postcode") == postcode
    )


def geocode_address(
    address: str, country: str, search: Search = nominatim_search
) -> Optional[dict[str, Any]]:
    """Position of an address in its town: the building, else the street, else the town.

    ``level`` says which one was found; ``precise`` (building) is the only level where the
    position is the address itself. ``label`` names what the map shows ("Winterthur").
    """
    place = address_place(address, country)
    for params in geocode_searches(address, country):
        hit = next((item for item in search(params, country) if _in_town(item, place)), None)
        if not hit:
            continue
        if "q" in params and hit.get("house_number"):
            level = "building"
        elif "q" in params and hit.get("road"):
            level = "street"
        else:
            level = "town"
        if level == "town":
            label = hit.get("locality") or (place[1] if place else "")
        else:
            label = ", ".join(part for part in (hit.get("road"), hit.get("locality")) if part)
        return {
            "lat": hit["lat"],
            "lon": hit["lon"],
            "display_name": hit["display_name"],
            "label": label or hit["display_name"],
            "level": level,
            "precise": level == "building",
            "country_code": hit.get("country_code"),
            "source": "OpenStreetMap",
        }
    return None


def claim_location(root: str, app_md: Any, search: Search = nominatim_search) -> dict[str, Any]:
    """Address and position of a claim, geocoded on first request and kept with the case.

    ``status``: ``resolved`` (``place`` set), ``not_found``, ``no_address`` or ``unavailable``
    (geocoder unreachable: not stored, the next request tries again). ``search_address`` is
    the address without its description, for map links.
    """
    found = claim_address(getattr(app_md, "extracted_fields", None) or {})
    if not found:
        return {
            "status": "no_address",
            "address": None,
            "search_address": None,
            "kind": None,
            "place": None,
        }
    kind, address = found
    country = application_jurisdiction(app_md).country
    search_address = map_address(address, country)

    def answer(status: str, place: Optional[dict[str, Any]]) -> dict[str, Any]:
        return {
            "status": status,
            "address": address,
            "search_address": search_address,
            "kind": kind,
            "place": place,
        }

    stored = load_file(root, app_md.id, LOCATION_FILE)
    if stored:
        try:
            cached = json.loads(stored.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            cached = None
        if (
            isinstance(cached, dict)
            and cached.get("version") == LOCATION_VERSION
            and cached.get("address") == address
        ):
            place = cached.get("place")
            return answer("resolved" if place else "not_found", place)

    try:
        place = geocode_address(address, country, search)
    except Exception as exc:  # network, rate limit or malformed answer
        logger.warning("Geocoding failed for %s: %s", app_md.id, exc)
        return answer("unavailable", None)

    record = {
        "version": LOCATION_VERSION,
        "address": address,
        "place": place,
        "geocoded_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        save_application_file(root, app_md.id, LOCATION_FILE, json.dumps(record).encode("utf-8"))
    except Exception as exc:  # the position is still returned
        logger.warning("Could not store the location of %s: %s", app_md.id, exc)
    return answer("resolved" if place else "not_found", place)
