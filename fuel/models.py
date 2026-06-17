from django.db import models


class TruckStop(models.Model):
    """
    Model representing a US Truck Stop and its current fuel price.
    Includes database indexes to support fast spatial bounding-box lookups.
    """

    truckstop_id = models.CharField(max_length=50, unique=True, db_index=True)
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=255)
    city = models.CharField(max_length=100, db_index=True)
    state = models.CharField(max_length=50, db_index=True)
    retail_price = models.DecimalField(max_digits=10, decimal_places=4)
    latitude = models.FloatField(db_index=True)
    longitude = models.FloatField(db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["city", "state"]),
            models.Index(fields=["latitude", "longitude"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.city}, {self.state}) - ${self.retail_price}"
