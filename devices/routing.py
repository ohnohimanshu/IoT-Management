from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/device_data/(?P<device_id>[^/]+)/$', consumers.DeviceDataConsumer.as_asgi()),
] 