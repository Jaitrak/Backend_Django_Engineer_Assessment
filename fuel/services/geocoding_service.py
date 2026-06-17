import logging
import requests
from typing import List
from django.conf import settings
from fuel.exceptions import GeocodingError
from fuel.services.cache_service import CacheService

logger = logging.getLogger("fuel")


class GeocodingService:
    """
    Service to convert location strings into [longitude, latitude] coordinates.
    Integrates with OpenRouteService Geocoding API and caches results to avoid repeat calls.
    """

    @classmethod
    def geocode(cls, location_query: str) -> List[float]:
        """
        Geocodes a location query. Returns [longitude, latitude].
        Raises GeocodingError if geocoding fails.
        """
        if not location_query:
            raise GeocodingError("Location query cannot be empty.")

        # 1. Check cache first
        cached_coords = CacheService.get_geocode(location_query)
        if cached_coords:
            return cached_coords

        # 2. Verify API Key configuration
        api_key = getattr(settings, "ORS_API_KEY", "")
        if not api_key or api_key == "your_api_key_here":
            logger.error("OpenRouteService API Key (ORS_API_KEY) is not configured.")
            raise GeocodingError(
                "OpenRouteService API Key (ORS_API_KEY) is missing or configured as a placeholder. Please set it in your environment or .env file."
            )

        # 3. Call OpenRouteService Geocoding API
        url = "https://api.openrouteservice.org/geocode/search"
        params = {
            "api_key": api_key,
            "text": location_query,
            "boundary.country": "USA",
            "size": 1,
        }

        try:
            logger.info(f"Making external Geocoding API call for: '{location_query}'")
            response = requests.get(url, params=params, timeout=10)

            if response.status_code != 200:
                logger.error(
                    f"Geocoding API returned status code {response.status_code}: {response.text}"
                )
                raise GeocodingError(
                    f"Geocoding service returned error status {response.status_code}."
                )

            data = response.json()
            features = data.get("features", [])
            if not features:
                logger.warning(f"No coordinates found for location: '{location_query}'")
                raise GeocodingError(
                    f"Location '{location_query}' could not be resolved to coordinates."
                )

            # GeoJSON coordinates format is [longitude, latitude]
            coords = features[0]["geometry"]["coordinates"]
            if not coords or len(coords) < 2:
                logger.error(f"Invalid geometry structure returned: {features[0]}")
                raise GeocodingError("Invalid geocoding response structure.")

            # 4. Cache and return coordinates
            CacheService.set_geocode(location_query, coords)
            return coords

        except requests.RequestException as e:
            logger.exception("HTTP error encountered during geocoding.")
            raise GeocodingError(f"Network error during geocoding: {str(e)}")
        except (KeyError, TypeError, ValueError) as e:
            logger.exception("Data parsing error encountered during geocoding.")
            raise GeocodingError(f"Parsing error during geocoding: {str(e)}")
