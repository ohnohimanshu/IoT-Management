from django.urls import path
from . import views
from showdata.views import get_sensor_data


urlpatterns = [
    path('device/data/', views.device_data_upload, name='device-data-upload'),
    path('sensor-data/<int:device_id>/', get_sensor_data, name='get-sensor-data'),
]