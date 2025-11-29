from rest_framework import serializers
from .models import FirmwareVersion, OTAUpdate, DeviceFirmwareInfo


class FirmwareVersionSerializer(serializers.ModelSerializer):
    file_size_mb = serializers.ReadOnlyField()
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)

    class Meta:
        model = FirmwareVersion
        fields = [
            'id', 'name', 'description', 'version_number', 'device_type',
            'file_size', 'file_size_mb', 'checksum', 'is_active',
            'created_at', 'created_by_name'
        ]


class OTAUpdateSerializer(serializers.ModelSerializer):
    device_name = serializers.CharField(source='device.device_name', read_only=True)
    device_id = serializers.CharField(source='device.device_id', read_only=True)
    firmware_name = serializers.CharField(source='firmware_version.name', read_only=True)
    firmware_version_number = serializers.CharField(source='firmware_version.version_number', read_only=True)
    initiated_by_name = serializers.CharField(source='initiated_by.username', read_only=True)
    duration_seconds = serializers.SerializerMethodField()

    class Meta:
        model = OTAUpdate
        fields = [
            'id', 'device_name', 'device_id', 'firmware_name', 'firmware_version_number',
            'status', 'progress_percentage', 'initiated_by_name', 'initiated_at',
            'started_at', 'completed_at', 'duration_seconds', 'error_message',
            'previous_version', 'update_log'
        ]

    def get_duration_seconds(self, obj):
        duration = obj.duration
        if duration:
            return int(duration.total_seconds())
        return None


class DeviceFirmwareInfoSerializer(serializers.ModelSerializer):
    device_name = serializers.CharField(source='device.device_name', read_only=True)
    device_id = serializers.CharField(source='device.device_id', read_only=True)
    available_version_name = serializers.CharField(source='available_version.name', read_only=True)
    available_version_number = serializers.CharField(source='available_version.version_number', read_only=True)

    class Meta:
        model = DeviceFirmwareInfo
        fields = [
            'device_name', 'device_id', 'current_version', 'last_updated',
            'update_available', 'available_version_name', 'available_version_number',
            'auto_update_enabled', 'last_check'
        ]