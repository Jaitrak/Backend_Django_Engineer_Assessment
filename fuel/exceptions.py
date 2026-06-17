"""
Custom exceptions for the fuel app to facilitate clean and consistent error responses.
"""


class RouteNotFoundError(Exception):
    """Raised when the routing service cannot find or calculate a route."""

    pass


class GeocodingError(Exception):
    """Raised when the geocoding service cannot resolve a location string to coordinates."""

    pass


class FuelOptimizationError(Exception):
    """Raised when the fuel optimization service fails to find a feasible path or stop configuration."""

    pass
