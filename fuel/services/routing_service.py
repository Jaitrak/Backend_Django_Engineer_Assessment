import logging
import requests
from typing import List, Dict, Any
from django.conf import settings
from fuel.exceptions import RouteNotFoundError
from fuel.services.cache_service import CacheService

logger = logging.getLogger("fuel")


class RoutingService:
    """
    Service to fetch driving routes from OpenRouteService Directions API.
    Utilizes POST request with GeoJSON coordinates and caches responses locally.
    """

    @classmethod
    def get_route(
        cls,
        start_query: str,
        finish_query: str,
        start_coords: List[float],
        finish_coords: List[float],
    ) -> Dict[str, Any]:
        """
        Fetches the driving route between start and finish coordinates.
        Checks CacheService first. Returns a dictionary containing:
        - coordinates: List[List[float]] (sampled route points [lon, lat])
        - distance_miles: float
        - duration_seconds: float
        - geometry: Dict[str, Any] (the GeoJSON geometry for client rendering)
        """
        # 1. Check Cache first
        cached_route = CacheService.get_route(start_query, finish_query)
        if cached_route:
            return cached_route

        # 2. Verify API Key
        api_key = getattr(settings, "ORS_API_KEY", "")
        if not api_key or api_key == "your_api_key_here":
            logger.error("OpenRouteService API Key (ORS_API_KEY) is not configured.")
            raise RouteNotFoundError(
                "OpenRouteService API Key (ORS_API_KEY) is missing or configured as a placeholder. Please set it in your environment or .env file."
            )

        # 3. Call OpenRouteService Directions POST API
        url = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"
        headers = {
            "Authorization": api_key,
            "Content-Type": "application/json; charset=utf-8",
        }
        payload = {
            "coordinates": [
                [start_coords[0], start_coords[1]],  # [longitude, latitude]
                [finish_coords[0], finish_coords[1]],
            ]
        }

        try:
            logger.info(
                f"Making external Routing Directions API call from '{start_query}' to '{finish_query}'"
            )
            response = requests.post(url, json=payload, headers=headers, timeout=15)

            if response.status_code != 200:
                logger.error(
                    f"Routing API returned status code {response.status_code}: {response.text}"
                )
                raise RouteNotFoundError(
                    f"Routing service returned error status {response.status_code}."
                )

            data = response.json()
            features = data.get("features", [])
            if not features:
                logger.error("No routing features found in response.")
                raise RouteNotFoundError(
                    "No route found between the specified coordinates."
                )

            feature = features[0]
            geometry = feature.get("geometry", {})
            properties = feature.get("properties", {})
            summary = properties.get("summary", {})

            # Extract distance in meters and convert to miles (1 meter = 0.000621371 miles)
            distance_meters = summary.get("distance", 0.0)
            distance_miles = round(distance_meters * 0.000621371, 2)

            duration_seconds = summary.get("duration", 0.0)
            coordinates = geometry.get("coordinates", [])

            if not coordinates:
                logger.error("Route geometry contains no coordinates.")
                raise RouteNotFoundError("Calculated route has empty coordinates.")

            route_data = {
                "coordinates": coordinates,
                "distance_miles": distance_miles,
                "duration_seconds": duration_seconds,
                "geometry": geometry,
            }

            # 4. Cache and return
            CacheService.set_route(start_query, finish_query, route_data)
            return route_data

        except requests.RequestException as e:
            logger.exception("HTTP error during routing.")
            raise RouteNotFoundError(f"Network error during routing: {str(e)}")
        except (KeyError, TypeError, ValueError) as e:
            logger.exception("Parsing error during routing.")
            raise RouteNotFoundError(f"Parsing error during routing: {str(e)}")
