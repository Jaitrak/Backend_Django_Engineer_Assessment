import csv
import pytest
from unittest.mock import patch
from django.core.management import call_command
from django.core.management.base import CommandError
from fuel.models import TruckStop


@pytest.mark.django_db
def test_import_truckstops_csv_success(tmp_path):
    """
    Test importing from a CSV file.
    Verifies price deduplication (keeping cheapest) and offline geocoding database mapping.
    """
    # 1. Define mock geocoding mapping with uppercase state abbreviations to match the command
    mock_mapping = {
        "dallas,TX": {"latitude": 32.7767, "longitude": -96.7970},
        "houston,TX": {"latitude": 29.7604, "longitude": -95.3698},
    }

    # 2. Create mock CSV data
    csv_file = tmp_path / "fuel_prices.csv"
    headers = [
        "OPIS Truckstop ID",
        "Truckstop Name",
        "Address",
        "City",
        "State",
        "Rack ID",
        "Retail Price",
    ]
    rows = [
        # Normal stop in Dallas
        ["1001", "Dallas Pilot", "123 Main St", "Dallas", "TX", "99", "3.1500"],
        # Duplicate stop in Dallas, more expensive (should be skipped)
        [
            "1001",
            "Dallas Pilot Duplicate",
            "123 Main St",
            "Dallas",
            "TX",
            "99",
            "3.2500",
        ],
        # Duplicate stop in Dallas, cheaper (should replace)
        ["1001", "Dallas Pilot Cheaper", "123 Main St", "Dallas", "TX", "99", "3.1000"],
        # Stop in Houston
        ["1002", "Houston Loves", "456 Loop Rd", "Houston", "TX", "99", "3.2000"],
        # Stop in Austin (not in mapping, should be skipped/logged)
        ["1003", "Austin Flying J", "789 I-35", "Austin", "TX", "99", "3.0500"],
    ]

    with open(csv_file, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        writer.writerows(rows)

    # 3. Call management command, mocking the JSON database loading
    with patch("json.load", return_value=mock_mapping):
        call_command("import_truckstops", str(csv_file))

    # 4. Assertions
    # 1001 (cheapest Dallas stop) and 1002 (Houston stop) should be imported. 1003 is skipped.
    assert TruckStop.objects.count() == 2

    # Check Dallas stop properties (must be the cheapest one)
    dallas_stop = TruckStop.objects.get(truckstop_id="1001")
    assert dallas_stop.name == "Dallas Pilot Cheaper"
    assert float(dallas_stop.retail_price) == 3.10
    assert dallas_stop.latitude == 32.7767
    assert dallas_stop.longitude == -96.7970
    assert dallas_stop.city == "Dallas"
    assert dallas_stop.state == "TX"

    # Check Houston stop
    houston_stop = TruckStop.objects.get(truckstop_id="1002")
    assert houston_stop.name == "Houston Loves"
    assert float(houston_stop.retail_price) == 3.20


@pytest.mark.django_db
def test_import_truckstops_file_not_found():
    """
    Verifies that the command raises CommandError if the file does not exist.
    """
    with pytest.raises(CommandError) as exc_info:
        call_command("import_truckstops", "nonexistent_file.csv")
    assert "File not found at path" in str(exc_info.value)
