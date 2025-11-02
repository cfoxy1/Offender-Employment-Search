import requests, time, json, re
from geopy.geocoders import Nominatim, ArcGIS, GoogleV3
from geopy.distance import geodesic
from shapely import wkt
from shapely.geometry import Point, shape, Polygon
from xml.etree import ElementTree


#### REQUIREMENT FOR USE ####
# Obtain a Google Cloud "Google Places" API Key
# Free for up to 10000 requests
# Each use of this program will perform 10-1000 Google Places requests

API_KEY = "<add Google API key here>"


# ---------------------------
# USER CONFIGURABLE VARIABLES
# ---------------------------
RADIUS_FEET = 1100
SEARCH_RADIUS_MILES = 5

SEARCH_TYPES = ["park", "playground", "school", "library", "preschool", "sports_complex",
                "sports_activity_location", "fitness_center", "child_care_agency",
                "video_arcade", "swimming_pool"]
EXCLUDE_SEARCH_TYPES = ["university"]
#SEARCH_KEYWORDS = ["School", "Academy", "Child", "Kid"]
SEARCH_KEYWORDS = ["Child", "Kid"]

# ---------------------------
# AUTO DOWNLOAD COUNTY BOUNDARY
# ---------------------------
"""
def fetch_shelby_county_boundary():
    #Download the Shelby County, TN boundary as a GeoJSON polygon.
    #Tries US Census TIGER/Line first, then falls back to a static URL.

    try:
        # U.S. Census TIGER/Line GeoJSON
        url = "https://raw.githubusercontent.com/plotly/datasets/master/geojson-counties-fips.json"
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()

        # Shelby County FIPS code = 47157
        for feature in data["features"]:
            if feature["id"] == "47157":
                return shape(feature["geometry"])

        raise ValueError("Shelby County boundary not found in dataset")

    except Exception as e:
        print(f"[ERROR] Could not fetch Shelby County boundary: {e}")
        raise
"""

#shelby_polygon = fetch_shelby_county_boundary()

#below polygon has been manually adjusted due to an issue with the boundary of the one fetched above
polygon_wkt = """
POLYGON ((-89.642786 35.04486, -89.643782 35.012092, -89.643739 35.011693,
-89.644282 34.995293, -89.724324 34.994763, -89.795187 34.994293,
-89.848488 34.994193, -89.883365 34.994261, -89.893402 34.994356,
-90.309297 34.995694, -90.309877 35.00975, -90.295596 35.040093,
-90.193859 35.061646, -90.174594 35.116682, -90.160058 35.12883,
-90.142794 35.135091, -90.109393 35.118891, -90.100593 35.116691,
-90.09061 35.118287, -90.08342 35.12167, -90.065392 35.137691,
-90.064612 35.140621, -90.073354 35.211004, -90.074262 35.218316,
-90.07741 35.225479, -90.097947 35.249983, -90.105093 35.254288,
-90.116493 35.255788, -90.140394 35.252289, -90.152094 35.255989,
-90.158865 35.262577, -90.166594 35.274588, -90.168871 35.281997,
-90.163812 35.296115, -90.158913 35.300637, -90.153394 35.302588,
-90.114893 35.303887, -90.086691 35.369935, -90.089612 35.379842,
-90.074992 35.384152, -90.061788 35.386184, -90.054322 35.389277,
-89.889317 35.390906, -89.70248 35.408584, -89.632776 35.375824,
-89.642786 35.04486))
"""

# Parse WKT to Polygon object
shelby_polygon = wkt.loads(polygon_wkt)
#print("shelby_polygon: ")
#print(shelby_polygon)



# ---------------------------
# CONVERSION UTILS
# ---------------------------
def feet_to_meters(feet):
    return feet * 0.3048

def miles_to_feet(miles):
    return miles * 5280


# ---------------------------
# ADDRESS UTILS
# ---------------------------

def census_geocode(address):
    """Try to geocode using U.S. Census API (best for U.S. addresses)."""
    url = "https://geocoding.geo.census.gov/geocoder/locations/onelineaddress"

    params = {
        "address": address,
        "benchmark": "Public_AR_Current",
        "format": "json"
    }


    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        result = resp.json()
        coords = result['result']['addressMatches'][0]['coordinates']
        return (coords['y'], coords['x'])  # latitude, longitude

    except (IndexError, KeyError, requests.RequestException):
        raise ValueError("Address not found via Census API")



def arcgis_geocode(address):
    """Fallback geocoding using ArcGIS via geopy."""
    geolocator = ArcGIS(timeout=10)
    location = geolocator.geocode(address)

    if location:
        return (location.latitude, location.longitude)
    else:
        raise ValueError("Address not found via ArcGIS")


def nominatim_geocode(address):
    """Fallback geocoding using Nominatim."""
    geolocator = Nominatim(user_agent="shelby_locator", timeout=10)
    location = geolocator.geocode(address)

    if location:
        return (location.latitude, location.longitude)
    else:
        raise ValueError("Address not found via Nominatim")


def geocode_address(address):
    """Attempt geocoding using multiple services in order."""
    for method in [census_geocode, arcgis_geocode, nominatim_geocode]:
        try:
            return method(address)
        except Exception:
            continue
    raise ValueError("Failed to geocode address with all methods.")


def extract_osm_address(tags):
    """Return cleaned address if explicitly tagged in OSM."""
    #print("inside extract_osm_address")
    house_number = tags.get("addr:housenumber")
    #if not house_number:
    #    print("WARNING: no housenumber was provided in the tags for extract_osm_address")
    #else:
    #print("House number (extract_osm_address): " + str(house_number))
    street = tags.get("addr:street")
    city = tags.get("addr:city") or tags.get("addr:town") or tags.get("addr:village")
    state = tags.get("addr:state")
    postcode = tags.get("addr:postcode")
    if house_number and street and city and state and postcode:
        address = f"{house_number} {street}, {city}, {state} {postcode}"
        return re.sub(r"\s+", " ", address).strip()
    return None


def reverse_geocode_clean(lat, lon, name):
    #Get the address using the coordinates if unavailable in OSM
    #Reverse geocode with ArcGIS primary and Census fallback.
    try:
        # --- Try ArcGIS first ---
        arcgis = ArcGIS(timeout=10)
        location = arcgis.reverse((lat, lon), exactly_one=True)
        if not location:
            print("WARNING: ArcGIS returned no resulting address for a set of coordinates.")
            return "Address unavailable"

        #print("ArcGIS location:")
        #print(location)

        house_number = ""
        # ArcGIS sometimes stores full address under 'Address' key
        if hasattr(location, "raw"):
            raw_addr = location.raw.get("Address", "")
            match = re.search(r"\b\d{1,5}(?:[A-Z]?)\b", raw_addr)
            if match:
                house_number = match.group(0)
                #print("just set house_number to: " + str(house_number))

        #if not house_number:
        #    print("STILL NO housenumber found after ArcGIS + Census.")
        #else:
        #    print("House number (reverse_geocode_clean): " + str(house_number))
        # Extract other address fields from ArcGIS
        address_parts = re.split(r",\s*", location.address or "")
        address = f"{location.address}"
        address = address.strip(", ")
        #print("address after reverse_geocode_clean: " + address)
        return address

    except Exception as e:
        print("Error in reverse_geocode_clean:", e)
        return "Address unavailable"



# ---------------------------
# GOOGLE PLACES APIS
# ---------------------------

def text_search(query, lat, lng, radius_meters):
    #NOTE: this api will only ever give a max of 20 entries
    url = "https://places.googleapis.com/v1/places:searchText"

    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": API_KEY,
        "X-Goog-FieldMask": (
            "places.displayName,"
            "places.formattedAddress,"
            "places.types,"
            "places.location,"
            "places.websiteUri"
        )
    }
    payload = {
        "textQuery": query,
        "locationBias": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": radius_meters
            }
        }
    }

    response = requests.post(url, headers=headers, json=payload, timeout=10)

    response.raise_for_status()

    data = response.json()

    return data.get("places", [])


def search_nearby_new(lat, lng, included_types, radius_meters):
    #print("inside search nearby. Lat: " + str(lat) + ", lng: " + str(lng) + ", radius_meters: " + str(radius_meters))
    #print("included types: ")
    #print(included_types)

    #NOTE: this api will only ever give a max of 20 entries
    url = f"https://places.googleapis.com/v1/places:searchNearby?key={API_KEY}"


    headers = {
        "Content-Type": "application/json",
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.types,places.location"
    }


    payload = {
        "locationRestriction": {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": radius_meters
            }
        },
        "includedTypes": included_types
    }


    response = requests.post(url, headers=headers, json=payload, timeout=10)

    response.raise_for_status()

    data = response.json()

    return data.get("places", [])


# ---------------------------
# OVERPASS APIS
# ---------------------------

def query_overpass_restaurants(lat, lon, radius_feet, max_retries=3, delay=5):
    radius_meters = radius_feet * 0.3048

    query = f"""
    [out:json];
    (
      node["amenity"="restaurant"](around:{radius_meters},{lat},{lon});
      way["amenity"="restaurant"](around:{radius_meters},{lat},{lon});
    );
    out center tags;
    """
    url = "https://overpass-api.de/api/interpreter"

    for attempt in range(max_retries):
        try:
            response = requests.get(url, params={"data": query}, timeout=30)
            response.raise_for_status()
            return response.json()
        except requests.RequestException:
            if attempt < max_retries - 1:
                time.sleep(delay)
                continue
            else:
                raise


def query_overpass_keywords(lat, lon, radius_feet, keywords, tags=("name",), max_retries=3, delay=5):

    #print(f"inside query_overpass_keywords. lat={lat}, lon={lon}, radius={radius_feet}ft")
    radius_meters = radius_feet * 0.3048
    #radius_meters = 10000

    # Make regex pattern for keywords
    keyword_pattern = "|".join(re.escape(k) for k in keywords)
    #print("keyword_pattern: " + str(keyword_pattern))
    # Build a query that matches BOTH name-based and tag-based features
    query = f"""
    [out:json];
    (
      node["name"~"({keyword_pattern})"](around:{radius_meters},{lat},{lon});
      way["name"~"({keyword_pattern})"](around:{radius_meters},{lat},{lon});
      relation["name"~"({keyword_pattern})"](around:{radius_meters},{lat},{lon});
    );
    out center tags;
    """

    url = "https://overpass-api.de/api/interpreter"

    for attempt in range(max_retries):
        try:
            response = requests.get(url, params={"data": query}, timeout=60)
            response.raise_for_status()
            data = response.json()
            print(f"[DEBUG] Overpass returned {len(data.get('elements', []))} results")
            return data
        except requests.RequestException as e:
            print(f"[WARN] Overpass attempt {attempt + 1} failed: {e}")
            if attempt < max_retries - 1:
                time.sleep(delay)
            else:
                raise



# ---------------------------
# MISC UTILITY FUNCTIONS
# ---------------------------

def inside_shelby_county(lat, lng):
    return shelby_polygon.contains(Point(lng, lat))

def get_youth_congregation_areas(address):
    #print(f"[DEBUG] Geocoding address: {address}")
    lat, lng = geocode_address(address)
    radius_meters = feet_to_meters(RADIUS_FEET)
    google_places = []
    overpass_places = []
    seen_names = set()
    final_list = []


    # Nearby Search
    try:
        places = search_nearby_new(lat, lng, SEARCH_TYPES, radius_meters)
    except Exception:
        places = []

    #print("places from nearby search: ")
    #print(places)

    for place in places:
        name = place.get("displayName", {}).get("text")
        if not name or name in seen_names:
            continue
        placeTypes = place.get("types", [])
        if any(item in EXCLUDE_SEARCH_TYPES for item in placeTypes):
            continue
        seen_names.add(name.lower())
        google_places.append(place)


    # Text Search
    for term in SEARCH_KEYWORDS:
        try:
            places = text_search(term, lat, lng, radius_meters)
        except Exception:
            continue
        for place in places:
            name = place.get("displayName", {}).get("text", "")
            #print("place found with " + term + " search text: " + name)
            #print("(1)seen_names: ")
            #print(seen_names)
            if not name or name.lower() in seen_names:
                #print("skipping " + name + " because it is already in seen_names")
                continue
            seen_names.add(name.lower())
            combined_text = name.lower()
            if SEARCH_KEYWORDS and not any(k.lower() in combined_text for k in SEARCH_KEYWORDS):
                #print("skipping " + name + "because it does not have one of the SEARCH_KEYWORDS")
                continue
            google_places.append(place)


    """
    #Overpass text search
    try:
        overpass_places = query_overpass_keywords(lat, lng, RADIUS_FEET, SEARCH_KEYWORDS).get("elements", [])
    except Exception as e:
        print("Error occurred during query_overpass_keywords")
        print(e)


    for element in overpass_places:
        #print("current element in overpass_places: ")
        #print(element)
        tags = element.get("tags", {})
        name = tags.get("name")
        #print("name: " + name)

        # Coordinates
        if "lat" in element:
            lat0, lon0 = element["lat"], element["lon"]
        else:
            center = element.get("center")
            if not center:
                continue
            lat0, lon0 = center["lat"], center["lon"]

            #print("lat: " + str(lat0) + ", lon: " + str(lon0))

        distance_miles = geodesic([lat, lng], (lat0, lon0)).miles
        distance_feet = distance_miles * 5280

        if not name or name.lower() in seen_names:
            continue
        seen_names.add(name.lower())
        combined_text = name.lower()
        if SEARCH_KEYWORDS and not any(k.lower() in combined_text for k in SEARCH_KEYWORDS):
            continue
        address = extract_osm_address(tags) or reverse_geocode_clean(lat0, lon0)

        if distance_feet is not None and distance_feet <= RADIUS_FEET:
           final_list.append({
                "name": name,
                "address": address,
                "distance": distance_feet
            })
    """

    for place in google_places:
        name = place.get("displayName", {}).get("text", "N/A")
        addr = place.get("formattedAddress", "N/A")
        types = place.get("types", [])
        loc = place.get("location", {})
        place_lat = loc.get("latitude")
        place_lng = loc.get("longitude")
        if place_lat is not None and place_lng is not None:
            dist_m = geodesic((lat, lng), (place_lat, place_lng)).meters
            dist_ft = round(dist_m / 0.3048)
        else:
            dist_ft = None
        if dist_ft is not None and dist_ft <= RADIUS_FEET:
            final_list.append({
                "name": name,
                "address": addr,
                "types": types,
                "distance": dist_ft
            })

    # Sort by distance
    final_list.sort(key=lambda x: x['distance'] if x.get('distance') is not None else float('inf'))
    return final_list



def calculate_polygon_center(polygon):
    """Calculate approximate geometric center of a polygon by averaging coordinates."""
    try:
        coords = list(polygon.exterior.coords)
        avg_x = sum(x for x, _ in coords) / len(coords)
        avg_y = sum(y for _, y in coords) / len(coords)
        return avg_y, avg_x  # return as (lat, lng)
    except Exception as e:
        print(f"[ERROR] Could not calculate polygon center: {e}")
        # fallback to downtown Memphis
        return (35.1495, -90.0490)


def get_restaurants_in_shelby_county(address=None):
    if address:
        #print(f"[DEBUG] Using user-provided address: {address}")
        lat0, lng0 = geocode_address(address)
        search_radius_ft = miles_to_feet(SEARCH_RADIUS_MILES)
    else:
        #print("[DEBUG] No address provided, calculating polygon center for Shelby County.")
        lat0, lng0 = calculate_polygon_center(shelby_polygon)
        search_radius_ft = miles_to_feet(20)

    # Fetch nearby restaurants using overpass API since it lets you fetch more than 20 at a time and is free
    restaurants_raw = query_overpass_restaurants(lat0, lng0, search_radius_ft).get("elements", [])
    #print("num restaurants returned by overpass search:", len(restaurants_raw))
    #print("restaurants_raw: ")
    #print(restaurants_raw)

    restaurants = []

    print("Fetching full addresses for " + str(len(restaurants_raw)) + " restaurants found ...")

    processed = -1
    for element in restaurants_raw:
        try:
            processed = processed + 1
            if processed % 10 == 0 and processed > 0:
                print("Identified " + str(processed) + " addresses out of " + str(len(restaurants_raw)))
            #print("current element: ")
            #print(element)
            #print("")
            tags = element.get("tags", {})
            name = tags.get("name")
            if not name:
                continue
            #print("name: " + name)

            # Coordinates
            if "lat" in element:
                lat, lon = element["lat"], element["lon"]
            else:
                center = element.get("center")
                if not center:
                    continue
                lat, lon = center["lat"], center["lon"]

            #print("lat: " + str(lat) + ", lon: " + str(lon))
            # Distance in feet
            distance_miles = geodesic([lat0, lng0], (lat, lon)).miles
            distance_feet = distance_miles * 5280
            #print("distance_feet: " + str(distance_feet))

            #print("tags for " + name + ": ")
            #print(tags)
            address = extract_osm_address(tags) or reverse_geocode_clean(lat, lon, name)

            #print("address: " + address)

            # skip bars
            if re.search(r'\bbar\b', name, flags=re.IGNORECASE) and not re.search(r'\bbar-b-q\b', name, flags=re.IGNORECASE) and not re.search(r'\bbar b q\b', name, flags=re.IGNORECASE):
                print(f"skipping location that has bar in the name: {name}")
                continue

            #print("checking if location is inside Shelby county")

            # strict Shelby County filter
            if lat is not None and lon is not None and not inside_shelby_county(lat, lon):
                print(f"skipping location that is not in Shelby County: {name}")
                continue


            #print("adding restaurant to list: " + name)
            restaurants.append({
                "name": name,
                "address": address,
                "distance_feet": round(distance_feet, 1)
            })


            #time.sleep(.1)
            #print("")
        except Exception as e:
            print(e)
            continue

    restaurants = sorted(restaurants, key=lambda x: x["distance_feet"])

    print(f"[DEBUG] Total restaurants after filtering: {len(restaurants)}")
    return restaurants



# ---------------------------
# MAIN
# ---------------------------
if __name__ == "__main__":
    print("Select an option:")
    print("1: Check if an address is near facilities where minors congregate")
    print("2: Find restaurants not near locations where minors congregate")
    choice = input("Enter 1 or 2: ").strip()

    if choice == "1":
        address = input(f"Enter an address in Shelby County to search within {RADIUS_FEET} feet: ").strip()
        kid_friendly = get_youth_congregation_areas(address)
        print("")
        if not kid_friendly:
            print(f"\nNo kid‑friendly locations found near {address}.")
        else:
            for place in kid_friendly:
                print(f"Place: {place['name']}")
                print(f"Address: {place['address']}")
                print(f"Types: {place['types']}")
                print(f"Distance: {place['distance']} feet\n")

    elif choice == "2":
        address = input("Enter an address in Shelby County to limit search by distance (or leave blank for full county): ").strip()

        restaurants = get_restaurants_in_shelby_county(address)
        total_restaurants = len(restaurants)
        if address:
            print(f"\n[WARNING] Found {total_restaurants} restaurants within " + str(SEARCH_RADIUS_MILES) + " miles of the provided address.")
        else:
            print(f"\n[WARNING] Found {total_restaurants} restaurants inside Shelby County.")

        confirm = input("Continue checking each for kid‑friendly nearby locations? (y/n): ").strip().lower()
        if confirm != "y" and confirm != "Y":
            print("Process cancelled.")
        else:
            non_kid_friendly = []
            for i, rest in enumerate(restaurants, 1):
                #print("checking restaurant: " + rest['name'] + ", address: " + rest['address'])
                kid_places = get_youth_congregation_areas(rest["address"])

                if not kid_places:
                    non_kid_friendly.append(rest)

                if i % 10 == 0 or i == total_restaurants:
                    print(f"[PROGRESS] Checked {i} of {total_restaurants} restaurants…")

            # If address was provided, sort non_kid_friendly by distance from that address
            if address:
                user_lat, user_lng = geocode_address(address)
                non_kid_friendly.sort(
                    key=lambda x: geodesic((user_lat, user_lng), geocode_address(x["address"])).feet
                )

            if not non_kid_friendly:
                print("\nAll restaurants have kid‑friendly locations nearby.")
            else:
                print(f"\nFound {len(non_kid_friendly)} restaurants with no kid‑friendly locations nearby:\n")
                for rest in non_kid_friendly:
                    print(f"Restaurant: {rest['name']}")
                    print(f"Address: {rest['address']}")
                    #if rest['website']:
                    #    print(f"Website: {rest['website']}\n")
                    if address:
                        try:
                            rest_lat, rest_lng = geocode_address(rest["address"])
                            dist_miles = geodesic((user_lat, user_lng), (rest_lat, rest_lng)).miles
                            print(f"Distance from provided address: {dist_miles:.2f} miles\n")
                        except Exception as e:
                            print(f"[WARN] Could not calculate distance for {rest['name']}: {e}\n")

    else:
        print("Invalid choice. Exiting.")