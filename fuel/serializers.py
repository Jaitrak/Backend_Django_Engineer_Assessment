from rest_framework import serializers


class RouteRequestSerializer(serializers.Serializer):
    """
    Serializer validating incoming request payload for route optimization.
    """

    start = serializers.CharField(
        max_length=255,
        required=True,
        help_text="Start location name or address in the USA (e.g. 'New York, NY')",
    )
    finish = serializers.CharField(
        max_length=255,
        required=True,
        help_text="Destination location name or address in the USA (e.g. 'Los Angeles, CA')",
    )

    def validate(self, data):
        start = data.get("start")
        finish = data.get("finish")
        if start and finish:
            from fuel.services.cache_service import CacheService

            start_norm = CacheService._normalize_location(start)
            finish_norm = CacheService._normalize_location(finish)
            if start_norm == finish_norm:
                raise serializers.ValidationError(
                    "Start and finish locations cannot be the same."
                )
        return data


class TruckStopSerializer(serializers.Serializer):
    """
    Serializer detailing a selected truck stop refuel point.
    """

    truckstop_id = serializers.CharField(help_text="OPIS unique truck stop ID.")
    name = serializers.CharField(help_text="Name of the truck stop.")
    address = serializers.CharField(help_text="Street address.")
    city = serializers.CharField(help_text="City name.")
    state = serializers.CharField(help_text="State abbreviation.")
    retail_price = serializers.FloatField(help_text="Retail fuel price per gallon.")
    latitude = serializers.FloatField(help_text="Latitude coordinate.")
    longitude = serializers.FloatField(help_text="Longitude coordinate.")


class RouteResponseSerializer(serializers.Serializer):
    """
    Serializer representing the final response structure of the route optimizer API.
    """

    route_geometry = serializers.DictField(
        help_text="GeoJSON geometry of the computed route."
    )
    total_distance_miles = serializers.FloatField(
        help_text="Total calculated route distance in miles."
    )
    total_fuel_cost = serializers.FloatField(
        help_text="Estimated total fuel cost for the trip in USD."
    )
    fuel_stops = TruckStopSerializer(
        many=True, help_text="Cheapest viable fuel stops along the route."
    )
