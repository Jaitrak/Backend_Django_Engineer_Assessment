import pytest
from unittest.mock import patch, MagicMock
from django.core.cache import cache
from django.test import override_settings

from fuel.services.cache_service import CacheService
from fuel.services.geocoding_service import GeocodingService
from fuel.services.routing_service import RoutingService
from fuel.exceptions import GeocodingError, RouteNotFoundError


@pytest.fixture(autouse=True)
def clear_django_cache():
    """Clear the django cache before each test."""
    cache.clear()


def test_cache_normalization():
    """
    Verifies location strings are normalized correctly.
    """
    norm1 = CacheService._normalize_location("New York, NY")
    norm2 = CacheService._normalize_location("new york, ny")
    norm3 = CacheService._normalize_location("  New York   NY  ")
    assert norm1 == "new york ny"
    assert norm2 == "new york ny"
    assert norm3 == "new york ny"


def test_cache_route_get_set():
    """
    Test setting and getting routes from cache.
    """
    start = "New York, NY"
    finish = "Boston, MA"
    route_payload = {"distance_miles": 220.0, "coordinates": [[1, 2], [3, 4]]}

    assert CacheService.get_route(start, finish) is None
    CacheService.set_route(start, finish, route_payload)

    cached = CacheService.get_route(start, finish)
    assert cached == route_payload

    # Verify casing differences still hit the cache
    assert CacheService.get_route("new york, ny", "boston, ma") == route_payload


def test_cache_geocode_get_set():
    """
    Test setting and getting geocoding results from cache.
    """
    query = "Miami, FL"
    coords = [-80.1918, 25.7617]

    assert CacheService.get_geocode(query) is None
    CacheService.set_geocode(query, coords)

    assert CacheService.get_geocode(query) == coords
    assert CacheService.get_geocode("  miami fl  ") == coords


@patch("requests.get")
@override_settings(ORS_API_KEY="test_api_key")
def test_geocoding_service_success(mock_get):
    """
    Verifies GeocodingService returns coordinates on successful API response
    and caches the result.
    """
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "features": [{"geometry": {"coordinates": [-118.2437, 34.0522]}}]
    }
    mock_get.return_value = mock_response

    coords = GeocodingService.geocode("Los Angeles, CA")
    assert coords == [-118.2437, 34.0522]

    # Verify geocode is cached
    assert CacheService.get_geocode("Los Angeles, CA") == [-118.2437, 34.0522]

    # Verify subsequent call uses cache without calling API again
    mock_get.reset_mock()
    coords_cached = GeocodingService.geocode("Los Angeles, CA")
    assert coords_cached == [-118.2437, 34.0522]
    mock_get.assert_not_called()


@patch("requests.get")
@override_settings(ORS_API_KEY="test_api_key")
def test_geocoding_service_not_found(mock_get):
    """
    Verifies GeocodingService raises GeocodingError when no features are found.
    """
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"features": []}
    mock_get.return_value = mock_response

    with pytest.raises(GeocodingError) as exc_info:
        GeocodingService.geocode("Invalid City")
    assert "could not be resolved" in str(exc_info.value)


@patch("requests.post")
@override_settings(ORS_API_KEY="test_api_key")
def test_routing_service_success(mock_post):
    """
    Verifies RoutingService returns driving car route info and caches it.
    """
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "features": [
            {
                "geometry": {
                    "type": "LineString",
                    "coordinates": [[-74.006, 40.7128], [-71.0589, 42.3601]],
                },
                "properties": {
                    "summary": {
                        # 350,000 meters ~ 217.48 miles
                        "distance": 350000.0,
                        "duration": 14400.0,
                    }
                },
            }
        ]
    }
    mock_post.return_value = mock_response

    route_data = RoutingService.get_route(
        "New York, NY", "Boston, MA", [-74.006, 40.7128], [-71.0589, 42.3601]
    )

    assert route_data["distance_miles"] == 217.48
    assert route_data["duration_seconds"] == 14400.0
    assert route_data["coordinates"] == [[-74.006, 40.7128], [-71.0589, 42.3601]]

    # Verify cached
    cached = CacheService.get_route("New York, NY", "Boston, MA")
    assert cached == route_data


@patch("requests.post")
@override_settings(ORS_API_KEY="test_api_key")
def test_routing_service_network_failure(mock_post):
    """
    Verifies RoutingService raises RouteNotFoundError on HTTP error status.
    """
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    mock_post.return_value = mock_response

    with pytest.raises(RouteNotFoundError) as exc_info:
        RoutingService.get_route(
            "New York, NY", "Boston, MA", [-74.006, 40.7128], [-71.0589, 42.3601]
        )
    assert "returned error status 500" in str(exc_info.value)
