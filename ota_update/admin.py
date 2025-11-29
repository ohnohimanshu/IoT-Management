from django.contrib import admin
from .models import FirmwareVersion, OTAUpdate, DeviceFirmwareInfo


@admin.register(FirmwareVersion)
class FirmwareVersionAdmin(admin.ModelAdmin):
    list_display = ['name', 'version_number', 'device_type', 'file_size_mb', 'is_active', 'created_at']
    list_filter = ['device_type', 'is_active', 'created_at']
    search_fields = ['name', 'version_number', 'description']
    readonly_fields = ['file_size', 'checksum', 'created_at']
    ordering = ['-created_at']


@admin.register(OTAUpdate)
class OTAUpdateAdmin(admin.ModelAdmin):
    list_display = ['device', 'firmware_version', 'status', 'progress_percentage', 'initiated_by', 'initiated_at']
    list_filter = ['status', 'initiated_at', 'firmware_version__device_type']
    search_fields = ['device__device_name', 'device__device_id', 'firmware_version__version_number']
    readonly_fields = ['initiated_at', 'started_at', 'completed_at', 'duration']
    ordering = ['-initiated_at']

    def duration(self, obj):
        return obj.duration
    duration.short_description = 'Duration'


@admin.register(DeviceFirmwareInfo)
class DeviceFirmwareInfoAdmin(admin.ModelAdmin):
    list_display = ['device', 'current_version', 'update_available', 'auto_update_enabled', 'last_updated']
    list_filter = ['update_available', 'auto_update_enabled', 'last_updated']
    search_fields = ['device__device_name', 'device__device_id', 'current_version']
    readonly_fields = ['last_check']