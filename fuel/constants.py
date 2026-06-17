"""
Constants configuration for the fuel route optimizer application.
Avoids magic numbers and keeps domain configurations in one place.
"""

MAX_RANGE_MILES = 500.0
MPG = 10.0
SEARCH_RADIUS_MILES = 50.0
ROUTE_CACHE_TTL = 86400  # 24 hours in seconds
GEOCODE_CACHE_TTL = 2592000  # 30 days in seconds
