import pytest
from fuel.models import TruckStop
from fuel.services.fuel_optimizer import FuelOptimizerService
from fuel.exceptions import FuelOptimizationError


@pytest.mark.django_db
def test_optimize_short_route_empty_db():
    """
    Test a short route (<= 500 miles) when the database is empty.
    Should return an empty list of stops and calculate fuel cost using default average price ($3.50).
    """
    # Route is 300 miles
    # Route coordinates: two points representing 300 miles
    # Let's say coordinates are not checked for distance calculation on short routes
    result = FuelOptimizerService.optimize(
        route_coordinates=[[-95.0, 30.0], [-95.0, 34.35]],  # approx 300 miles
        total_distance_miles=300.0,
    )
    assert result["fuel_stops"] == []
    # 300 miles / 10 MPG = 30 gallons. 30 gallons * $3.50 = 105.00
    assert result["total_fuel_cost"] == 105.00


@pytest.mark.django_db
def test_optimize_short_route_with_db_average():
    """
    Test a short route (<= 500 miles) with stations in the database.
    Should calculate cost using database average price.
    """
    # Insert some stops
    TruckStop.objects.create(
        truckstop_id="1",
        name="Stop A",
        address="1 Main",
        city="City A",
        state="TX",
        retail_price=3.0000,
        latitude=30.0,
        longitude=-95.0,
    )
    # Average price is 3.00
    result = FuelOptimizerService.optimize(
        route_coordinates=[[-95.0, 30.0], [-95.0, 34.35]],
        total_distance_miles=300.0,
    )
    assert result["fuel_stops"] == []
    # 300 miles / 10 MPG = 30 gallons * $3.00 = 90.00
    assert result["total_fuel_cost"] == 90.00


@pytest.mark.django_db
def test_optimize_long_route_success():
    """
    Test a long route (> 500 miles) requiring refuels.
    Verifies bounding box filtering, route projection, greedy viability, and segment costs.
    """
    # 1. Create truck stops along the route
    # Route coordinates goes from (-95.0, 30.0) directly north to (-95.0, 42.0)
    # 12 degrees latitude difference * 69 miles/deg = ~828 miles total
    # Let's place stops at different mile markers:
    # 1 degree of latitude is roughly 69.05 miles.

    # Stop 1: Mile ~207 (lat 33.0). Close to route (distance 0). Price: $3.00
    # Stop 2: Mile ~207 (lat 33.0). Close to route but more expensive. Price: $3.50 (should not be chosen)
    # Stop 3: Mile ~414 (lat 36.0). Close to route. Price: $3.20
    # Stop 4: Mile ~414 (lat 36.0). Too far from route (60 miles away). Price: $2.50 (should be excluded)
    # Stop 5: Mile ~621 (lat 39.0). Close to route. Price: $3.10

    # Dallas Stop (lat 33.0)
    TruckStop.objects.create(
        truckstop_id="101",
        name="Dallas Cheap",
        address="I-35",
        city="Dallas",
        state="TX",
        retail_price=3.0000,
        latitude=33.0,
        longitude=-95.0,
    )
    TruckStop.objects.create(
        truckstop_id="102",
        name="Dallas Pricey",
        address="I-35",
        city="Dallas",
        state="TX",
        retail_price=3.5000,
        latitude=33.0,
        longitude=-94.99,  # slightly east
    )
    # Oklahoma Stop (lat 36.0)
    TruckStop.objects.create(
        truckstop_id="103",
        name="Oklahoma Love",
        address="I-35",
        city="Oklahoma City",
        state="OK",
        retail_price=3.2000,
        latitude=36.0,
        longitude=-95.0,
    )
    # Oklahoma Stop (lat 36.0) but too far east (approx 60 miles east, lon -94.0)
    # 1 deg lon at 36 lat is ~56 miles. So -93.8 lon is ~67 miles away.
    TruckStop.objects.create(
        truckstop_id="104",
        name="Oklahoma Far Away",
        address="I-40",
        city="Far City",
        state="OK",
        retail_price=2.5000,
        latitude=36.0,
        longitude=-93.8,
    )
    # Kansas Stop (lat 39.0)
    # We must refuel at lat 36 or 39 because from 33 (mile 207) to the end (mile 828) is 621 miles (>500)
    # From start 0.0, we must stop at Oklahoma (mile 414) or Dallas (mile 207).
    # Oklahoma at mile 414 is reachable, and we can reach the end (828) from Oklahoma because 828 - 414 = 414 miles (<500).
    # Since Okla (3.20) is viable and Dallas (3.00) is viable, Oklahoma is further. Wait, Oklahoma price is $3.20, Dallas is $3.00.
    # From Okla (414) we can reach finish (828) directly. So we only need 1 stop.
    # Is Oklahoma (Oklahoma City) reachable from start? Yes, 414 miles <= 500 range.
    # Is Dallas (207) reachable? Yes.
    # Which viable stop is cheapest? Dallas is 3.00, Oklahoma is 3.20.
    # Wait, if we stop at Dallas (207), we have 500 miles of range from 207, which gets us to 707 miles.
    # The finish is 828 miles. We CANNOT reach the finish (828) if we only stop at Dallas! We would need a second stop!
    # Let's verify:
    # If we stop at Oklahoma (414): 1 stop total, cost = (414/10 * 3.20) + (414/10 * 3.20) = 41.4*3.20 + 41.4*3.20 = 82.8*3.20 = 264.96.
    # If we stop at Dallas (207) and then Kansas (621): 2 stops, cost = (207/10 * 3.00) + (414/10 * 3.10) + (207/10 * 3.10) = 62.1 + 128.34 + 64.17 = 254.61.
    # Since our greedy algorithm checks reachable stops and finds which are viable:
    # At start (0.0): reachable stops are Dallas (207) and Oklahoma (414).
    # Are they both viable?
    # Dallas (207): Can it reach finish? No, 828 - 207 = 621 (> 500). Can it reach another stop? Yes, Oklahoma (414 - 207 = 207 <= 500) and Kansas (621 - 207 = 414 <= 500). So Dallas is viable!
    # Oklahoma (414): Can it reach finish? Yes, 828 - 414 = 414 <= 500. Can it reach Kansas? Yes. So Oklahoma is viable!
    # From viable reachable stops {Dallas (3.00), Oklahoma (3.20)}, our greedy viability optimizer picks the CHEAPEST.
    # The cheapest is Dallas (3.00)!
    # So we stop at Dallas (207).
    # Next, current_dist = 207. Max reachable is 207 + 500 = 707.
    # Reachable from 207: Oklahoma (414) and Kansas (621).
    # Are they viable?
    # Oklahoma (414): Can reach finish? Yes (828 - 414 = 414 <= 500). Yes, viable.
    # Kansas (621): Can reach finish? Yes (828 - 621 = 207 <= 500). Yes, viable.
    # From viable reachable stops {Oklahoma (3.20), Kansas (3.10)}, our greedy viability optimizer picks the CHEAPEST.
    # The cheapest is Kansas (3.10)!
    # So we stop at Kansas (621).
    # Next, current_dist = 621. Remaining to finish is 828 - 621 = 207 <= 500. Destination is reachable! We stop.
    # Selected stops: Dallas (101) at 207 miles, Kansas (105) at 621 miles.
    # This is exactly correct! It shows the optimizer works perfectly.

    TruckStop.objects.create(
        truckstop_id="105",
        name="Kansas Love",
        address="I-35",
        city="Wichita",
        state="KS",
        retail_price=3.1000,
        latitude=39.0,
        longitude=-95.0,
    )

    # Define route coordinates (latitude from 30.0 to 42.0 in 13 points)
    route_coords = [[-95.0, float(lat)] for lat in range(30, 43)]
    total_dist = 12.0 * 69.05  # 828.6 miles

    result = FuelOptimizerService.optimize(
        route_coordinates=route_coords,
        total_distance_miles=total_dist,
    )

    # Selected stops should be 101 (Dallas) and 105 (Kansas)
    assert len(result["fuel_stops"]) == 2
    assert result["fuel_stops"][0]["truckstop_id"] == "101"
    assert result["fuel_stops"][1]["truckstop_id"] == "105"

    # Total cost details:
    # Segment 1 (start to Dallas): 207.15 miles -> 20.715 gallons * $3.00 = $62.145
    # Segment 2 (Dallas to Kansas): 414.3 miles -> 41.43 gallons * $3.10 = $128.433
    # Segment 3 (Kansas to end): 207.15 miles -> 20.715 gallons * $3.10 = $64.2165
    # Sum ~ $254.80. Let's make sure the calculated cost is close.
    assert result["total_fuel_cost"] > 250.0
    assert result["total_fuel_cost"] < 260.0


@pytest.mark.django_db
def test_optimize_long_route_no_stops_reachable():
    """
    Test a route where there is a gap > 500 miles with no stations.
    Should raise FuelOptimizationError.
    """
    # 800 miles trip
    route_coords = [[-95.0, float(lat)] for lat in range(30, 43)]

    with pytest.raises(FuelOptimizationError) as exc_info:
        FuelOptimizerService.optimize(
            route_coordinates=route_coords,
            total_distance_miles=800.0,
        )
    assert "No truck stops found within driving range" in str(exc_info.value)
