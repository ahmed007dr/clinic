"""Which clinic is nearest to the customer (docs/16, Phase A).

The public page asks for the clinics that offer a service and wants them nearest
first. Two ways to say where the customer is, best first:

* **a point** (`lat`, `lng`) — the browser's location, if the customer allowed it.
  Distance is the straight line (haversine), enough to order clinics of a country;
* **a governorate** — chosen from a list, for a customer who would not share a
  location, or clinics that have no coordinates.

Nothing about where the customer is leaves this module: it is used to order a
list and is neither stored nor sent back.
"""

from math import asin, cos, radians, sin, sqrt

EARTH_KM = 6371.0088


def distance_km(lat1, lng1, lat2, lng2):
    """Great-circle distance between two points, in kilometres."""
    lat1, lng1, lat2, lng2 = (radians(float(v)) for v in (lat1, lng1, lat2, lng2))
    a = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lng2 - lng1) / 2) ** 2
    return 2 * EARTH_KM * asin(sqrt(a))


def parse_point(params):
    """`(lat, lng)` from query parameters, or None when absent or not a real point."""
    try:
        lat, lng = float(params.get("lat")), float(params.get("lng"))
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180) or lat != lat or lng != lng:
        return None
    return lat, lng


def normalize(text):
    """A governorate as typed by people: case, spacing and Arabic alef/ya variants ignored."""
    text = str(text or "").strip().casefold()
    for old, new in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ى", "ي"), ("ة", "ه")):
        text = text.replace(old, new)
    return " ".join(text.split())


def order_by_nearness(rows, branches, params):
    """Sort `rows` (dicts with a `uuid`) nearest first, adding `distance_km`,
    `governorate` and `same_governorate` to each. `branches` maps a row's uuid to
    its Branch. Returns `(rows, mode)`, `mode` one of "distance", "governorate", "name"."""
    point = parse_point(params)
    wanted = normalize(params.get("governorate"))
    mode = "name"
    for row in rows:
        branch = branches[row["uuid"]]
        has_point = branch.latitude is not None and branch.longitude is not None
        km = None
        if point and has_point:
            km = round(distance_km(point[0], point[1], branch.latitude, branch.longitude), 1)
        row["governorate"] = branch.governorate or ""
        row["distance_km"] = km
        row["same_governorate"] = bool(wanted) and normalize(branch.governorate) == wanted
    if point and any(row["distance_km"] is not None for row in rows):
        mode = "distance"
        rows.sort(key=lambda r: (r["distance_km"] is None, r["distance_km"] or 0, not r["same_governorate"], r["name"]))
    elif wanted:
        mode = "governorate"
        rows.sort(key=lambda r: (not r["same_governorate"], r["name"]))
    else:
        rows.sort(key=lambda r: r["name"])
    # Only a clinic that really is near (a distance, or the customer's own governorate) is "nearest".
    for index, row in enumerate(rows):
        row["nearest"] = index == 0 and mode != "name" and (
            row["distance_km"] is not None or row["same_governorate"])
    return rows, mode
