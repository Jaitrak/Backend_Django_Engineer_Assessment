import math
import time
import logging
from typing import List, Dict, Any, Tuple
from django.db.models import Avg, Q
from fuel.models import TruckStop
from fuel.constants import MAX_RANGE_MILES, MPG, SEARCH_RADIUS_MILES
from fuel.exceptions import FuelOptimizationError

logger = logging.getLogger("fuel")


class FuelOptimizerService:
    """
    Service to execute greedy fuel stop selection and calculate total cost.
    Optimized to perform bounding box DB query filtering and project stops onto route coordinates.
    """

    @staticmethod
    def _haversine(coord1: Tuple[float, float], coord2: Tuple[float, float]) -> float:
        """
        Calculates the great-circle distance between two points in miles using the Haversine formula.
        coord = (longitude, latitude)
        """
        lon1, lat1 = coord1
        lon2, lat2 = coord2

        # Earth radius in miles
        r = 3958.8

        d_lat = math.radians(lat2 - lat1)
        d_lon = math.radians(lon2 - lon1)

        a = (
            math.sin(d_lat / 2) ** 2
            + math.cos(math.radians(lat1))
            * math.cos(math.radians(lat2))
            * math.sin(d_lon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        return r * c

    @classmethod
    def optimize(
        cls, route_coordinates: List[List[float]], total_distance_miles: float
    ) -> Dict[str, Any]:
        """
        Main entry point for optimizing fuel stops along the route.
        Returns:
            Dict containing:
            - fuel_stops: List of Dicts representing selected truck stops
            - total_fuel_cost: float
        """
        t_start = time.perf_counter()
        if not route_coordinates:
            raise FuelOptimizationError("No route coordinates provided.")

        # 1. Handle short routes (<= 500 miles)
        if total_distance_miles <= MAX_RANGE_MILES:
            logger.info(
                f"Route distance ({total_distance_miles} miles) is within range limit ({MAX_RANGE_MILES}). No stops required."
            )
            avg_price = TruckStop.objects.aggregate(Avg("retail_price"))[
                "retail_price__avg"
            ]
            if avg_price is None:
                # Default average if DB is empty
                avg_price = 3.50
                logger.warning(
                    "Database contains no fuel stations. Using default average price: $3.50"
                )
            else:
                avg_price = float(avg_price)

            fuel_consumed = total_distance_miles / MPG
            total_cost = round(fuel_consumed * avg_price, 2)

            return {
                "fuel_stops": [],
                "total_fuel_cost": total_cost,
            }

        # 2. Extract bounding box of the route with 0.5 degrees margin (approx 35 miles)
        # Using 15 segmented bounding boxes to avoid fetching candidate stops far from the actual route
        segment_count = 15
        segment_size = max(1, len(route_coordinates) // segment_count)
        margin_lat = 0.73
        margin_lon = 1.0

        q_objects = Q()
        for i in range(0, len(route_coordinates), segment_size):
            segment = route_coordinates[i : i + segment_size + 1]
            lons_seg = [pt[0] for pt in segment]
            lats_seg = [pt[1] for pt in segment]
            min_lon_seg, max_lon_seg = min(lons_seg) - margin_lon, max(lons_seg) + margin_lon
            min_lat_seg, max_lat_seg = min(lats_seg) - margin_lat, max(lats_seg) + margin_lat
            
            q_objects |= Q(
                latitude__gte=min_lat_seg,
                latitude__lte=max_lat_seg,
                longitude__gte=min_lon_seg,
                longitude__lte=max_lon_seg,
            )

        # 3. Query candidates within the segmented bounding box
        db_candidates = list(TruckStop.objects.filter(q_objects))
        db_candidates_count = len(db_candidates)

        # 4. Calculate cumulative distance along route coordinates to map indices to distances
        cumulative_distances = [0.0]
        for i in range(1, len(route_coordinates)):
            segment_dist = cls._haversine(
                (route_coordinates[i - 1][0], route_coordinates[i - 1][1]),
                (route_coordinates[i][0], route_coordinates[i][1]),
            )
            cumulative_distances.append(cumulative_distances[-1] + segment_dist)

        # 5. Project candidates onto the route (Coarse-to-fine spatial search)
        t_proj_start = time.perf_counter()
        projected_candidates = []
        R = len(route_coordinates)
        K = int(math.sqrt(R)) if R > 50 else 1

        for stop in db_candidates:
            stop_coord = (stop.longitude, stop.latitude)

            # Stage 1: Coarse search
            min_dist_coarse = float("inf")
            best_coarse_idx = 0
            for idx in range(0, R, K):
                pt = route_coordinates[idx]
                dist = cls._haversine(stop_coord, (pt[0], pt[1]))
                if dist < min_dist_coarse:
                    min_dist_coarse = dist
                    best_coarse_idx = idx

            # Stage 2: Fine search around the neighborhood of best_coarse_idx
            start_idx = max(0, best_coarse_idx - K)
            end_idx = min(R, best_coarse_idx + K + 1)

            min_dist = float("inf")
            best_idx = 0
            for idx in range(start_idx, end_idx):
                pt = route_coordinates[idx]
                dist = cls._haversine(stop_coord, (pt[0], pt[1]))
                if dist < min_dist:
                    min_dist = dist
                    best_idx = idx

            # If within the 50 miles threshold, keep it
            if min_dist <= SEARCH_RADIUS_MILES:
                projected_candidates.append(
                    {
                        "model": stop,
                        "projected_dist": cumulative_distances[best_idx],
                        "route_index": best_idx,
                        "proximity_miles": round(min_dist, 2),
                    }
                )

        projection_time = time.perf_counter() - t_proj_start

        # Sort candidate stops by their projected distance along the route
        projected_candidates.sort(key=lambda x: x["projected_dist"])

        # 6. Execute Greedy Viability Optimizer
        selected_stops = []
        current_dist = 0.0

        while total_distance_miles - current_dist > MAX_RANGE_MILES:
            # Range window: (current_dist, current_dist + 500.0]
            max_reachable_dist = current_dist + MAX_RANGE_MILES

            # Find stops reachable within range
            reachable = [
                (idx, item)
                for idx, item in enumerate(projected_candidates)
                if current_dist < item["projected_dist"] <= max_reachable_dist
            ]

            if not reachable:
                # No stops reachable at all in the next 500 miles. Raise optimization error.
                logger.error(
                    f"Route GAP detected: No truck stops found between {current_dist:.1f} and {max_reachable_dist:.1f} miles."
                )
                raise FuelOptimizationError(
                    "No truck stops found within driving range of the vehicle."
                )

            # Filter reachable stops to only those that are VIABLE
            # A stop is viable if we can either reach the destination from it, OR we can reach another stop from it.
            viable_reachable = []
            for idx, item in reachable:
                d_i = item["projected_dist"]

                # Can we reach destination?
                if total_distance_miles - d_i <= MAX_RANGE_MILES:
                    viable_reachable.append(item)
                    continue

                # Can we reach another stop further along the route?
                has_next_stop = False
                for next_item in projected_candidates[idx + 1 :]:
                    if next_item["projected_dist"] - d_i <= MAX_RANGE_MILES:
                        has_next_stop = True
                        break

                if has_next_stop:
                    viable_reachable.append(item)

            # Select the cheapest stop from the viable subset
            if viable_reachable:
                best_stop = min(viable_reachable, key=lambda x: x["model"].retail_price)
            else:
                # Fallback: if no stops are viable, pick the cheapest reachable stop to proceed and log warning
                logger.warning(
                    "No viable stops found that guarantee reaching the next stop/destination. "
                    "Falling back to cheapest reachable stop in range."
                )
                best_stop = min(
                    [item for _, item in reachable],
                    key=lambda x: x["model"].retail_price,
                )

            selected_stops.append(best_stop)
            current_dist = best_stop["projected_dist"]
            logger.info(
                f"Selected stop: {best_stop['model'].name} at route mile {current_dist:.2f} (Price: ${best_stop['model'].retail_price})"
            )

        # 7. Calculate fuel cost for each segment
        # Segment 1: from Start (0.0) to selected_stops[0] (fuel purchased at selected_stops[0])
        # Segment j: from selected_stops[j-1] to selected_stops[j] (fuel purchased at selected_stops[j])
        # Final Segment: from selected_stops[-1] to Finish (total_distance_miles) (fuel purchased at selected_stops[-1])
        total_cost = 0.0
        prev_dist = 0.0

        for stop in selected_stops:
            segment_dist = stop["projected_dist"] - prev_dist
            segment_fuel = segment_dist / MPG
            segment_cost = segment_fuel * float(stop["model"].retail_price)
            total_cost += segment_cost
            prev_dist = stop["projected_dist"]

        # Final segment cost (uses last stop's price)
        if selected_stops:
            final_dist = total_distance_miles - prev_dist
            final_fuel = final_dist / MPG
            final_cost = final_fuel * float(selected_stops[-1]["model"].retail_price)
            total_cost += final_cost

        # 8. Structure fuel stops response
        stops_response = []
        for item in selected_stops:
            model = item["model"]
            stops_response.append(
                {
                    "truckstop_id": model.truckstop_id,
                    "name": model.name,
                    "address": model.address,
                    "city": model.city,
                    "state": model.state,
                    "retail_price": float(model.retail_price),
                    "latitude": model.latitude,
                    "longitude": model.longitude,
                }
            )

        optimizer_total = time.perf_counter() - t_start
        logger.info(f"Route points: {R}")
        logger.info(f"DB candidates: {db_candidates_count}")
        logger.info(f"Filtered candidates: {len(projected_candidates)}")
        logger.info(f"Projection: {projection_time:.2f}s")
        logger.info(f"Optimizer total: {optimizer_total:.2f}s")

        return {
            "fuel_stops": stops_response,
            "total_fuel_cost": round(total_cost, 2),
        }
