from rest_framework import serializers
from .models import Alert, EmailRecipient
from devices.serializers import DeviceSerializer

class EmailRecipientSerializer(serializers.ModelSerializer):
    class Meta:
        model = EmailRecipient
        fields = ['id', 'email', 'added_at', 'user']

class AlertSerializer(serializers.ModelSerializer):
    device_name = serializers.CharField(source='device.device_name', read_only=True)
    device_id = serializers.CharField(source='device.device_id', read_only=True)
    
    class Meta:
        model = Alert
        fields = ['id', 'title', 'message', 'severity', 'device', 'device_name', 'device_id', 'user', 'timestamp', 'is_read']
        read_only_fields = ['timestamp']