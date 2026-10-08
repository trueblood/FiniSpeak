import json
import math
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen


EARTH_RADIUS_MILES = 3958.7613
GEOHASH_ALPHABET = "0123456789bcdefghjkmnpqrstuvwxyz"


def haversine_miles(latitude_a, longitude_a, latitude_b, longitude_b):
    """Return the great-circle distance between two WGS84 points."""
    lat_a, lon_a, lat_b, lon_b = map(math.radians, (
        float(latitude_a), float(longitude_a), float(latitude_b), float(longitude_b)
    ))
    d_lat = lat_b - lat_a
    d_lon = lon_b - lon_a
    value = math.sin(d_lat / 2) ** 2 + math.cos(lat_a) * math.cos(lat_b) * math.sin(d_lon / 2) ** 2
    return EARTH_RADIUS_MILES * 2 * math.asin(math.sqrt(value))


def encode_geohash(latitude, longitude, precision=9):
    """Encode coordinates without adding a runtime geospatial dependency."""
    latitude, longitude = validate_coordinates(latitude, longitude)
    latitude_range = [-90.0, 90.0]
    longitude_range = [-180.0, 180.0]
    result, bits, value, even = [], 0, 0, True
    bit_values = (16, 8, 4, 2, 1)
    while len(result) < precision:
        bounds = longitude_range if even else latitude_range
        coordinate = longitude if even else latitude
        midpoint = sum(bounds) / 2
        if coordinate >= midpoint:
            value |= bit_values[bits]
            bounds[0] = midpoint
        else:
            bounds[1] = midpoint
        even = not even
        if bits < 4:
            bits += 1
        else:
            result.append(GEOHASH_ALPHABET[value])
            bits, value = 0, 0
    return "".join(result)


def validate_coordinates(latitude, longitude):
    latitude, longitude = float(latitude), float(longitude)
    if not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
        raise ValueError("Invalid latitude or longitude.")
    return latitude, longitude


def geohash_prefixes(latitude, longitude, radius_miles):
    """Return prefixes covering the center and eight points on the search circle.

    Firestore can range-query each prefix and the final Haversine pass removes
    the rectangular/geohash false positives.
    """
    latitude, longitude = validate_coordinates(latitude, longitude)
    radius = max(1.0, min(float(radius_miles), 100.0))
    precision = 4 if radius <= 10 else 3
    lat_delta = radius / 69.0
    lon_delta = radius / max(1.0, 69.0 * math.cos(math.radians(latitude)))
    # Sample more tightly than the approximate cell dimensions so every cell
    # touching the bounding box contributes a prefix.
    cell_miles = 12.0 if precision == 4 else 97.0
    steps = max(2, int(math.ceil((radius * 2) / (cell_miles / 2))))
    points = []
    for lat_index in range(steps + 1):
        for lon_index in range(steps + 1):
            points.append((
                latitude - lat_delta + (2 * lat_delta * lat_index / steps),
                longitude - lon_delta + (2 * lon_delta * lon_index / steps),
            ))
    return sorted({encode_geohash(max(-90, min(90, lat)), ((lon + 180) % 360) - 180, precision) for lat, lon in points})


def geocode_public_area(query):
    """Resolve a city/state/ZIP to an approximate public area via Nominatim."""
    query = str(query or "").strip()
    if len(query) < 2 or len(query) > 160:
        raise ValueError("Enter a city, state, or ZIP code.")
    base_url = os.getenv("GEOCODING_BASE_URL", "https://nominatim.openstreetmap.org/search").strip()
    params = urlencode({"q": query, "format": "jsonv2", "limit": 1, "addressdetails": 1})
    request = Request(
        f"{base_url}?{params}",
        headers={"User-Agent": os.getenv("GEOCODING_USER_AGENT", "FiniSpeak/1.0 (support@finispeak.com)")},
    )
    with urlopen(request, timeout=5) as response:
        matches = json.loads(response.read().decode("utf-8"))
    if not matches:
        return None
    match = matches[0]
    latitude, longitude = validate_coordinates(match["lat"], match["lon"])
    address = match.get("address") or {}
    if address.get("house_number") or (address.get("road") and not (address.get("city") or address.get("town") or address.get("village") or address.get("postcode"))):
        raise ValueError("Enter only a city, state/province, or ZIP—not a street address.")
    return {
        "latitude": round(latitude, 3),
        "longitude": round(longitude, 3),
        "geohash": encode_geohash(latitude, longitude),
        "label": match.get("display_name", query),
        "city": address.get("city") or address.get("town") or address.get("village") or "",
        "state": address.get("state") or "",
        "country": address.get("country") or "",
    }
