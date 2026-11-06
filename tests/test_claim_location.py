"""The loss address is shown on a map: geocoded once with OpenStreetMap, kept with the case."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app import claim_location as location
from app.storage_providers.base import StorageBackend, StorageSettings
from app.storage_providers.local import LocalStorageProvider


def _street(text):
    return {"q": text}


def _town(postcode, town):
    return {"city": town, "postalcode": postcode}


@pytest.mark.parametrize(
    ("address", "country", "expected"),
    [
        (
            "Kakaogasse 7, 8400 Winterthur, Schweiz",
            "CH",
            [_street("Kakaogasse 7, 8400 Winterthur, Schweiz"), _town("8400", "Winterthur")],
        ),
        (
            "42 rue des Vignobles, 33000 Bordeaux - cave et sous-sol",
            "FR",
            [_street("42 rue des Vignobles, 33000 Bordeaux"), _town("33000", "Bordeaux")],
        ),
        (
            "Cave et sous-sol de la maison individuelle, 42 rue des Vignobles, 33000 Bordeaux",
            "FR",
            [_street("42 rue des Vignobles, 33000 Bordeaux"), _town("33000", "Bordeaux")],
        ),
        (
            "5 Place Bellecour, 69002 Lyon — Salon",
            "FR",
            [_street("5 Place Bellecour, 69002 Lyon"), _town("69002", "Lyon")],
        ),
        (
            "10 Chemin de Falgarde, 81000 Albi — Cave + RDC",
            "FR",
            [_street("10 Chemin de Falgarde, 81000 Albi"), _town("81000", "Albi")],
        ),
        (
            "23 Allée des Violettes, 31400 Toulouse",
            "FR",
            [_street("23 Allée des Violettes, 31400 Toulouse"), _town("31400", "Toulouse")],
        ),
        (
            "12 rue Paradis, 33000 BORDEAUX CEDEX",
            "FR",
            [_street("12 rue Paradis, 33000 BORDEAUX CEDEX"), _town("33000", "BORDEAUX")],
        ),
        ("Laden und Atelier (8400 Winterthur)", "CH", [_town("8400", "Winterthur")]),
        ("8400 Winterthur", "CH", [_town("8400", "Winterthur")]),
        (
            "Unruhweg 9, CH-8207 Schaffhausen",
            "CH",
            [_street("Unruhweg 9, CH-8207 Schaffhausen"), _town("8207", "Schaffhausen")],
        ),
        ("Cave de la maison", "FR", []),
    ],
)
def test_searches_drop_the_description_then_fall_back_to_the_town(address, country, expected):
    assert location.geocode_searches(address, country) == expected


def test_map_links_use_the_address_without_its_description_else_its_town():
    assert location.map_address("5 Place Bellecour, 69002 Lyon — Salon") == (
        "5 Place Bellecour, 69002 Lyon"
    )
    assert location.map_address("Laden und Atelier (8400 Winterthur)", "CH") == "8400 Winterthur"
    assert location.map_address("Cave de la maison") == "Cave de la maison"


def test_the_loss_address_comes_before_the_insured_address_whatever_the_key_prefix():
    fields = {
        "llm_extracted:AdresseAssure": {"value": "Kakaogasse 7, 8400 Winterthur"},
        "schadenmeldung.pdf:LieuSinistre": {
            "field_name": "LieuSinistre",
            "value": "Unruhweg 9, 8207 Schaffhausen",
        },
    }
    assert location.claim_address(fields) == ("loss", "Unruhweg 9, 8207 Schaffhausen")
    assert location.claim_address({"AdresseAssure": "42 rue des Vignobles, 33000 Bordeaux"}) == (
        "insured",
        "42 rue des Vignobles, 33000 Bordeaux",
    )
    assert location.claim_address({"LieuSinistre": {"value": "  "}}) is None


def _key(search):
    """ "5 Place Bellecour, 69002 Lyon" (free text) or "8400 Winterthur" (structured search)."""
    return search.get("q") or f"{search['postalcode']} {search['city']}"


def _search(results):
    calls = []

    def search(params, country):
        calls.append((_key(params), country))
        return results.get(_key(params), [])

    return search, calls


def _hit(lat, lon, locality, postcode, road="", house_number="", country="fr"):
    return {
        "lat": lat,
        "lon": lon,
        "display_name": ", ".join(
            part for part in (house_number, road, locality, postcode) if part
        ),
        "house_number": house_number,
        "road": road,
        "postcode": postcode,
        "locality": locality,
        "country_code": country,
    }


def test_the_map_shows_the_building_else_the_street_else_the_town():
    town = _hit(47.4992, 8.7291, "Winterthur", "", country="ch")
    search, calls = _search({"8400 Winterthur": [town]})

    place = location.geocode_address("Kakaogasse 7, 8400 Winterthur, Schweiz", "CH", search)

    assert calls == [("Kakaogasse 7, 8400 Winterthur, Schweiz", "CH"), ("8400 Winterthur", "CH")]
    assert place == {
        "lat": 47.4992,
        "lon": 8.7291,
        "display_name": "Winterthur",
        "label": "Winterthur",
        "level": "town",
        "precise": False,
        "country_code": "ch",
        "source": "OpenStreetMap",
    }

    street = _hit(44.84, -0.58, "Bordeaux", "33000", road="Rue des Vignobles")
    search, _ = _search({"42 rue des Vignobles, 33000 Bordeaux": [street]})
    place = location.geocode_address("42 rue des Vignobles, 33000 Bordeaux - cave", "FR", search)
    assert (place["level"], place["label"], place["precise"]) == (
        "street",
        "Rue des Vignobles, Bordeaux",
        False,
    )

    building = _hit(45.7587, 4.8318, "Lyon", "69002", road="Place Bellecour", house_number="5")
    search, _ = _search({"5 Place Bellecour, 69002 Lyon": [building]})
    place = location.geocode_address("5 Place Bellecour, 69002 Lyon — Salon", "FR", search)
    assert (place["level"], place["precise"]) == ("building", True)

    search, _ = _search({})
    assert location.geocode_address("5 Place Bellecour, 69002 Lyon", "FR", search) is None


# Nominatim's answers to seeded claim addresses (trimmed). The streets also exist in other towns
# of the arrondissement, which OSM names in "municipality". Dijon's two answers are swapped so
# that the namesake comes first.
_RECORDED = {
    "22 Rue Jean Moulin, 35000 Rennes": [
        {
            "lat": "48.0769",
            "lon": "-1.8547",
            "display_name": "22, Rue Jean Moulin, Mordelles, Rennes, Ille-et-Vilaine",
            "address": {
                "house_number": "22",
                "road": "Rue Jean Moulin",
                "village": "Mordelles",
                "municipality": "Rennes",
                "postcode": "35310",
                "country_code": "fr",
            },
        },
        {
            "lat": "48.0597",
            "lon": "-1.4489",
            "display_name": "22, Rue Jean Moulin, Châteaugiron, Rennes, Ille-et-Vilaine",
            "address": {
                "house_number": "22",
                "road": "Rue Jean Moulin",
                "town": "Châteaugiron",
                "municipality": "Rennes",
                "postcode": "35410",
                "country_code": "fr",
            },
        },
    ],
    "35000 Rennes": [
        {
            "lat": "48.1113",
            "lon": "-1.6800",
            "display_name": "Rennes, Ille-et-Vilaine, Bretagne",
            "address": {"city": "Rennes", "municipality": "Rennes", "country_code": "fr"},
        }
    ],
    "17 Rue de la Liberté, 21000 Dijon": [
        {
            "lat": "47.2553",
            "lon": "5.1457",
            "display_name": "17, Rue de la Liberté, Fauverney, Dijon, Côte-d'Or",
            "address": {
                "house_number": "17",
                "road": "Rue de la Liberté",
                "village": "Fauverney",
                "municipality": "Dijon",
                "postcode": "21110",
                "country_code": "fr",
            },
        },
        {
            "lat": "47.3229",
            "lon": "5.0360",
            "display_name": "17, Rue de la Liberté, Dijon, Côte-d'Or",
            "address": {
                "house_number": "17",
                "road": "Rue de la Liberté",
                "city": "Dijon",
                "municipality": "Dijon",
                "postcode": "21000",
                "country_code": "fr",
            },
        },
    ],
}


class _Response:
    def __init__(self, results):
        self.results = results

    def raise_for_status(self):
        return None

    def json(self):
        return self.results


def test_a_namesake_street_in_a_neighbouring_town_is_not_taken_for_the_claim(monkeypatch):
    monkeypatch.setattr(
        location.requests,
        "get",
        lambda url, params, headers, timeout: _Response(_RECORDED.get(_key(params), [])),
    )
    monkeypatch.setattr(location.time, "sleep", lambda seconds: None)

    rennes = location.geocode_address("22 Rue Jean Moulin, 35000 Rennes — Chambre", "FR")
    assert (rennes["level"], rennes["label"], rennes["lat"]) == ("town", "Rennes", 48.1113)

    dijon = location.geocode_address("17 Rue de la Liberté, 21000 Dijon — Cuisine", "FR")
    assert (dijon["level"], dijon["lat"], dijon["label"]) == (
        "building",
        47.3229,
        "Rue de la Liberté, Dijon",
    )


@pytest.fixture()
def storage_root(tmp_path, monkeypatch):
    provider = LocalStorageProvider(
        StorageSettings(backend=StorageBackend.LOCAL, local_root=str(tmp_path))
    )
    monkeypatch.setattr("app.storage._get_provider", lambda: provider)
    return str(tmp_path)


def _case(address):
    return SimpleNamespace(id="app-1", extracted_fields={"LieuSinistre": {"value": address}})


def test_a_case_is_geocoded_once_and_again_only_when_its_address_changes(storage_root, monkeypatch):
    hit = _hit(45.757, 4.832, "Lyon", "69002", road="Place Bellecour", house_number="5")
    search, calls = _search(
        {"5 Place Bellecour, 69002 Lyon": [hit], "17 Rue de la Liberté, 21000 Dijon": []}
    )

    first = location.claim_location(
        storage_root, _case("5 Place Bellecour, 69002 Lyon — Salon"), search
    )
    again = location.claim_location(
        storage_root, _case("5 Place Bellecour, 69002 Lyon — Salon"), search
    )

    assert first == again
    assert (
        first["status"] == "resolved"
        and first["kind"] == "loss"
        and first["place"]["precise"] is True
    )
    assert first["address"] == "5 Place Bellecour, 69002 Lyon — Salon"
    assert first["search_address"] == "5 Place Bellecour, 69002 Lyon"
    assert len(calls) == 1

    moved = location.claim_location(
        storage_root, _case("17 Rue de la Liberté, 21000 Dijon — Cuisine"), search
    )
    assert moved["status"] == "not_found" and moved["place"] is None
    assert len(calls) == 3  # street, then town: neither found
    location.claim_location(
        storage_root, _case("17 Rue de la Liberté, 21000 Dijon — Cuisine"), search
    )
    assert len(calls) == 3  # "not found" is kept too

    # A position stored by another version of the geocoding is computed again.
    monkeypatch.setattr(location, "LOCATION_VERSION", location.LOCATION_VERSION + 1)
    location.claim_location(
        storage_root, _case("17 Rue de la Liberté, 21000 Dijon — Cuisine"), search
    )
    assert len(calls) == 5


def test_an_unreachable_geocoder_is_tried_again_next_time(storage_root):
    def down(query, country):
        raise ConnectionError("nominatim unreachable")

    assert (
        location.claim_location(storage_root, _case("5 Place Bellecour, 69002 Lyon"), down)[
            "status"
        ]
        == "unavailable"
    )
    hit = _hit(45.757, 4.832, "Lyon", "69002", road="Place Bellecour", house_number="5")
    search, calls = _search({"5 Place Bellecour, 69002 Lyon": [hit]})
    assert (
        location.claim_location(storage_root, _case("5 Place Bellecour, 69002 Lyon"), search)[
            "status"
        ]
        == "resolved"
    )
    assert len(calls) == 1
    no_address = SimpleNamespace(id="app-2", extracted_fields={})
    assert location.claim_location(storage_root, no_address, search) == {
        "status": "no_address",
        "address": None,
        "search_address": None,
        "kind": None,
        "place": None,
    }


def test_nominatim_is_asked_politely_and_its_answer_read(monkeypatch):
    sent = {}
    answer = [
        {
            "lat": "45.7578",
            "lon": "4.8320",
            "display_name": "5, Place Bellecour, Lyon, France",
            "address": {
                "house_number": "5",
                "road": "Place Bellecour",
                "postcode": "69002",
                "city": "Lyon",
                "municipality": "Lyon",
                "country_code": "fr",
            },
        }
    ]

    def get(url, params, headers, timeout):
        sent.update(url=url, params=params, headers=headers, timeout=timeout)
        return _Response(answer)

    monkeypatch.setattr(location.requests, "get", get)
    monkeypatch.setattr(location.time, "sleep", lambda seconds: None)

    hits = location.nominatim_search({"q": "5 Place Bellecour, 69002 Lyon"}, "FR")

    assert hits == [
        {
            "lat": 45.7578,
            "lon": 4.832,
            "display_name": "5, Place Bellecour, Lyon, France",
            "house_number": "5",
            "road": "Place Bellecour",
            "postcode": "69002",
            "locality": "Lyon",
            "country_code": "fr",
        }
    ]
    assert sent["url"] == "https://nominatim.openstreetmap.org/search"
    assert sent["params"]["q"] == "5 Place Bellecour, 69002 Lyon"
    assert sent["params"]["countrycodes"] == "fr" and sent["params"]["limit"] == 5
    assert sent["headers"]["User-Agent"].startswith("PrevaIQ-")

    location.nominatim_search({"city": "Winterthur", "postalcode": "8400"}, "CH")
    assert "q" not in sent["params"] and sent["params"]["countrycodes"] == "ch"
    assert (sent["params"]["city"], sent["params"]["postalcode"]) == ("Winterthur", "8400")
