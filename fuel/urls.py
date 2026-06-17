from django.urls import path
from fuel.views import RouteOptimizerView

app_name = "fuel"

urlpatterns = [
    path("route/", RouteOptimizerView.as_view(), name="route-optimizer"),
]
