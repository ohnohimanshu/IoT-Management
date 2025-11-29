from django.urls import path
from . import views

urlpatterns = [
    path('sensor-data/<str:device_id>/', views.fetch_device_data, name='get_sensor_data'),
    path('device/<str:device_id>/data/', views.device_data_view, name='device_data'),
    path('api/device-data/<str:device_id>/', views.device_data_api, name='device_data_api'),
]
