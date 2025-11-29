from rest_framework import serializers
from api.models import  DeviceData
from devices.models import Device



# api/serializers.py
class DeviceDataSerializer(serializers.ModelSerializer):
    id = serializers.CharField(source='pk', read_only=True)

    class Meta:
        model = DeviceData
        fields = ['id', 'device', 'data']  # removed 'created_at'
        read_only_fields = ['id']


class DeviceSerializer(serializers.ModelSerializer):
    data_points = DeviceDataSerializer(many=True, read_only=True)
    
    class Meta:
        model = Device
        fields = [
            'id', 'device_name', 'device_id', 'device_status',
            'last_seen', 'email', 'email_interval', 'device_type',
            'status_change_count', 'data_points', 'settings'
        ]
        read_only_fields = ['last_seen', 'status_change_count']
