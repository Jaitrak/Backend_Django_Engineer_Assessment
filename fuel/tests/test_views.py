import pytest
from unittest.mock import patch
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient
from fuel.exceptions import GeocodingError, RouteNotFoundError, FuelOptimizationError


@pytest.fixture
def api_client():
    return APIClient()


def test_route_optimizer_view_validation_error(api_client):
    """
    Test that invalid request payload returns 400 Bad Request.
    """
    url = reverse("fuel:route-optimizer")

    # Missing 'finish'
    response = api_client.post(url, {"start": "New York, NY"}, format="json")
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["error"]["code"] == "invalid_request"
    assert "finish" in response.data["error"]["details"]


@patch("fuel.services.geocoding_service.GeocodingService.geocode")
def test_route_optimizer_view_geocoding_error(mock_geocode, api_client):
    """
    Test that geocoding failure returns 400 Bad Request with custom error payload.
    """
    url = reverse("fuel:route-optimizer")
    mock_geocode.side_effect = GeocodingError("Location could not be resolved.")

    response = api_client.post(
        url, {"start": "InvalidCity", "finish": "Los Angeles, CA"}, format="json"
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["error"]["code"] == "geocoding_error"
    assert "Location could not be resolved" in response.data["error"]["message"]


@patch("fuel.services.geocoding_service.GeocodingService.geocode")
@patch("fuel.services.routing_service.RoutingService.get_route")
def test_route_optimizer_view_routing_error(mock_route, mock_geocode, api_client):
    """
    Test that route calculation failure returns 400 Bad Request.
    """
    url = reverse("fuel:route-optimizer")
    mock_geocode.return_value = [0.0, 0.0]
    mock_route.side_effect = RouteNotFoundError("No route found between coordinates.")

    response = api_client.post(
        url, {"start": "New York, NY", "finish": "Los Angeles, CA"}, format="json"
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["error"]["code"] == "route_not_found"
    assert "No route found" in response.data["error"]["message"]


@patch("fuel.services.geocoding_service.GeocodingService.geocode")
@patch("fuel.services.routing_service.RoutingService.get_route")
@patch("fuel.services.fuel_optimizer.FuelOptimizerService.optimize")
def test_route_optimizer_view_optimization_error(
    mock_opt, mock_route, mock_geocode, api_client
):
    """
    Test that fuel optimization failure returns 400 Bad Request.
    """
    url = reverse("fuel:route-optimizer")
    mock_geocode.return_value = [0.0, 0.0]
    mock_route.return_value = {
        "coordinates": [[0, 0]],
        "distance_miles": 600.0,
        "geometry": {},
    }
    mock_opt.side_effect = FuelOptimizationError("No truck stops found within range.")

    response = api_client.post(
        url, {"start": "New York, NY", "finish": "Los Angeles, CA"}, format="json"
    )

    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["error"]["code"] == "optimization_error"
    assert "No truck stops found" in response.data["error"]["message"]


@patch("fuel.services.geocoding_service.GeocodingService.geocode")
@patch("fuel.services.routing_service.RoutingService.get_route")
@patch("fuel.services.fuel_optimizer.FuelOptimizerService.optimize")
def test_route_optimizer_view_success(mock_opt, mock_route, mock_geocode, api_client):
    """
    Test that a successful request returns 200 OK with the correct route and cost schema.
    """
    url = reverse("fuel:route-optimizer")
    mock_geocode.side_effect = [[-74.0060, 40.7128], [-118.2437, 34.0522]]
    mock_route.return_value = {
        "coordinates": [[-74.0060, 40.7128], [-118.2437, 34.0522]],
        "distance_miles": 2790.0,
        "duration_seconds": 150000.0,
        "geometry": {"type": "LineString", "coordinates": []},
    }
    mock_opt.return_value = {
        "fuel_stops": [
            {
                "truckstop_id": "1",
                "name": "Pilot",
                "address": "123 Rd",
                "city": "Dallas",
                "state": "TX",
                "retail_price": 3.25,
                "latitude": 32.7767,
                "longitude": -96.7970,
            }
        ],
        "total_fuel_cost": 906.75,
    }

    response = api_client.post(
        url, {"start": "New York, NY", "finish": "Los Angeles, CA"}, format="json"
    )

    assert response.status_code == status.HTTP_200_OK
    assert "route_geometry" in response.data
    assert response.data["total_distance_miles"] == 2790.0
    assert response.data["total_fuel_cost"] == 906.75
    assert len(response.data["fuel_stops"]) == 1
    assert response.data["fuel_stops"][0]["name"] == "Pilot"


def test_route_optimizer_view_same_start_finish(api_client):
    """
    Test that submitting identical start and finish locations returns 400 Bad Request
    and fails validation before calling external services.
    """
    url = reverse("fuel:route-optimizer")

    # Try identical strings
    response = api_client.post(
        url, {"start": "New York, NY", "finish": "New York, NY"}, format="json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["error"]["code"] == "invalid_request"
    assert (
        "Start and finish locations cannot be the same."
        in response.data["error"]["details"]["non_field_errors"][0]
    )

    # Try equivalent strings with different casing/spacing
    response = api_client.post(
        url, {"start": "  new york, ny  ", "finish": "NEW YORK, NY"}, format="json"
    )
    assert response.status_code == status.HTTP_400_BAD_REQUEST
    assert response.data["error"]["code"] == "invalid_request"
    assert (
        "Start and finish locations cannot be the same."
        in response.data["error"]["details"]["non_field_errors"][0]
    )
