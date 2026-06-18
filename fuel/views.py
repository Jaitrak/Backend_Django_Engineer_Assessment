import time
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from drf_spectacular.utils import extend_schema

from fuel.serializers import RouteRequestSerializer, RouteResponseSerializer
from fuel.services.geocoding_service import GeocodingService
from fuel.services.routing_service import RoutingService
from fuel.services.fuel_optimizer import FuelOptimizerService
from fuel.exceptions import GeocodingError, RouteNotFoundError, FuelOptimizationError

logger = logging.getLogger("fuel")


class RouteOptimizerView(APIView):
    """
    API view that accepts a start and finish location in the USA,
    calculates the driving route, selects optimal fuel stops,
    and returns the total fuel cost and route geometry.
    """

    @extend_schema(
        request=RouteRequestSerializer,
        responses={
            200: RouteResponseSerializer,
            400: RouteResponseSerializer,  # Custom error format is returned
            500: RouteResponseSerializer,
        },
        summary="Calculate optimal route and fuel stops",
        description=(
            "Calculates the driving route coordinates, identifies cheapest viable "
            "fuel stops within the 500-mile vehicle range, and calculates the total "
            "fuel cost for the journey."
        ),
    )
    def post(self, request, *args, **kwargs):
        serializer = RouteRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {
                    "error": {
                        "code": "invalid_request",
                        "message": "Input validation failed.",
                        "details": serializer.errors,
                    }
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        start = serializer.validated_data["start"]
        finish = serializer.validated_data["finish"]

        t_total_start = time.perf_counter()
        try:
            # 1. Geocode Start and Finish Locations
            logger.info(f"Geocoding locations: start='{start}', finish='{finish}'")
            t_geocode_start = time.perf_counter()
            try:
                start_coords = GeocodingService.geocode(start)
            except GeocodingError as e:
                return Response(
                    {
                        "error": {
                            "code": "geocoding_error",
                            "message": f"Start location: {str(e)}",
                        }
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )

            try:
                finish_coords = GeocodingService.geocode(finish)
            except GeocodingError as e:
                return Response(
                    {
                        "error": {
                            "code": "geocoding_error",
                            "message": f"Finish location: {str(e)}",
                        }
                    },
                    status=status.HTTP_400_BAD_REQUEST,
                )
            t_geocode_end = time.perf_counter()
            duration_geocoding = t_geocode_end - t_geocode_start

            # 2. Fetch driving route coordinates and metrics
            logger.info("Requesting route from RoutingService...")
            t_routing_start = time.perf_counter()
            route_data = RoutingService.get_route(
                start, finish, start_coords, finish_coords
            )
            t_routing_end = time.perf_counter()
            duration_routing = t_routing_end - t_routing_start

            # 3. Calculate optimal fuel stops and total cost
            logger.info("Executing FuelOptimizerService...")
            t_opt_start = time.perf_counter()
            optimization_data = FuelOptimizerService.optimize(
                route_coordinates=route_data["coordinates"],
                total_distance_miles=route_data["distance_miles"],
            )
            t_opt_end = time.perf_counter()
            duration_opt = t_opt_end - t_opt_start

            t_total_end = time.perf_counter()
            duration_total = t_total_end - t_total_start

            logger.info(f"[PERF] Geocoding: {duration_geocoding:.2f}s")
            logger.info(f"[PERF] Routing: {duration_routing:.2f}s")
            logger.info(f"[PERF] Fuel Optimization: {duration_opt:.2f}s")
            logger.info(f"[PERF] Total: {duration_total:.2f}s")

            # 4. Return success response
            response_payload = {
                "route_geometry": route_data["geometry"],
                "total_distance_miles": route_data["distance_miles"],
                "total_fuel_cost": optimization_data["total_fuel_cost"],
                "fuel_stops": optimization_data["fuel_stops"],
            }
            return Response(response_payload, status=status.HTTP_200_OK)

        except RouteNotFoundError as e:
            logger.warning(f"Route not found: {str(e)}")
            return Response(
                {"error": {"code": "route_not_found", "message": str(e)}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except FuelOptimizationError as e:
            logger.warning(f"Fuel optimization failed: {str(e)}")
            return Response(
                {"error": {"code": "optimization_error", "message": str(e)}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            logger.exception(
                "Unexpected exception occurred during route optimization processing."
            )
            return Response(
                {
                    "error": {
                        "code": "internal_error",
                        "message": "An unexpected error occurred while processing the request.",
                    }
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
