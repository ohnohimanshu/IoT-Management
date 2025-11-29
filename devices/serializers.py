from rest_framework import serializers
from .models import Device

class DeviceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Device
        fields = [
            'id', 'device_name', 'device_id', 'device_status',
            'last_seen', 'email', 'email_interval', 'device_type',
            'status_change_count', 'settings'
        ]
        read_only_fields = ['last_seen', 'status_change_count']

