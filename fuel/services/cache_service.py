import re
import logging
import hashlib
from typing import Optional, List
from django.core.cache import cache
from fuel.constants import ROUTE_CACHE_TTL, GEOCODE_CACHE_TTL

logger = logging.getLogger("fuel")


class CacheService:
    """
    Service to manage Django cache (LocMemCache) operations for routing and geocoding.
    Uses normalization and SHA-256 hashing to avoid CacheKeyWarning and backend key incompatibilities.
    """

    @staticmethod
    def _normalize_location(location: str) -> str:
        """
        Normalizes a location query string by converting to lowercase, removing punctuation,
        and collapsing whitespace.
        """
        if not location:
            return ""
        val = location.strip().lower()
        val = re.sub(r"[^\w\s]", "", val)  # Remove punctuation
        val = re.sub(r"\s+", " ", val)  # Collapse multiple spaces
        return val.strip()

    @classmethod
    def _make_safe_key(cls, prefix: str, *parts: str) -> str:
        """
        Generates a backend-safe, normalized, and hashed cache key.
        Uses SHA-256 to hash the normalized inputs to avoid spaces/unsafe characters.
        """
        normalized_parts = [cls._normalize_location(p) for p in parts]
        raw_key = ":".join(normalized_parts)
        hashed = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
        return f"{prefix}:{hashed}"

    @classmethod
    def get_route(cls, start: str, finish: str) -> Optional[dict]:
        """
        Retrieves a cached route response if it exists.
        Key structure: route:{sha256_hash_of_normalized_start_and_finish}
        """
        key = cls._make_safe_key("route", start, finish)
        data = cache.get(key)
        if data:
            logger.info(f"Cache HIT for route: {key}")
        else:
            logger.info(f"Cache MISS for route: {key}")
        return data

    @classmethod
    def set_route(cls, start: str, finish: str, route_data: dict) -> None:
        """
        Caches a route response for ROUTE_CACHE_TTL (24 hours).
        """
        key = cls._make_safe_key("route", start, finish)
        cache.set(key, route_data, ROUTE_CACHE_TTL)

    @classmethod
    def get_geocode(cls, query: str) -> Optional[List[float]]:
        """
        Retrieves cached geocoding coordinates [lon, lat] if they exist.
        Key structure: geocode:{sha256_hash_of_normalized_query}
        """
        key = cls._make_safe_key("geocode", query)
        data = cache.get(key)
        if data:
            logger.info(f"Cache HIT for geocode: {key}")
        else:
            logger.info(f"Cache MISS for geocode: {key}")
        return data

    @classmethod
    def set_geocode(cls, query: str, coordinates: List[float]) -> None:
        """
        Caches geocoding coordinates for GEOCODE_CACHE_TTL (30 days).
        """
        key = cls._make_safe_key("geocode", query)
        cache.set(key, coordinates, GEOCODE_CACHE_TTL)
        logger.info(f"Cached geocode successfully for key: {key}")
