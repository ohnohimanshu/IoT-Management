from django.db import models
from django.utils import timezone
from devices.models import Device
from accounts.models import CustomUser
import os


class FirmwareVersion(models.Model):
    """Model to store firmware versions and files"""
    name = models.CharField(max_length=100, help_text="Firmware version name (e.g., v1.2.3)")
    description = models.TextField(blank=True, help_text="Description of changes in this version")
    firmware_file = models.FileField(upload_to='firmware/', help_text="Upload .bin firmware file")
    device_type = models.CharField(max_length=20, choices=[
        ('esp32', 'ESP32'),
        ('esp8266', 'ESP8266'),
        ('esp', 'ESP Generic')
    ], help_text="Compatible device type")
    version_number = models.CharField(max_length=20, help_text="Version number (e.g., 1.2.3)")
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    is_active = models.BooleanField(default=True, help_text="Whether this version is available for updates")
    file_size = models.IntegerField(null=True, blank=True, help_text="File size in bytes")
    checksum = models.CharField(max_length=64, blank=True, help_text="SHA256 checksum of firmware file")

    class Meta:
        ordering = ['-created_at']
        unique_together = ['version_number', 'device_type']

    def __str__(self):
        return f"{self.name} ({self.device_type}) - {self.version_number}"

    def save(self, *args, **kwargs):
        if self.firmware_file:
            self.file_size = self.firmware_file.size
        super().save(*args, **kwargs)

    @property
    def file_size_mb(self):
        """Return file size in MB"""
        if self.file_size:
            return round(self.file_size / (1024 * 1024), 2)
        return 0


class OTAUpdate(models.Model):
    """Model to track OTA update operations"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='ota_updates')
    firmware_version = models.ForeignKey(FirmwareVersion, on_delete=models.CASCADE)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    initiated_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    initiated_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    progress_percentage = models.IntegerField(default=0, help_text="Update progress (0-100)")
    error_message = models.TextField(blank=True, help_text="Error details if update failed")
    previous_version = models.CharField(max_length=50, blank=True, help_text="Previous firmware version")
    update_log = models.JSONField(default=list, blank=True, help_text="Detailed update log")

    class Meta:
        ordering = ['-initiated_at']
        indexes = [
            models.Index(fields=['device', '-initiated_at']),
            models.Index(fields=['status', '-initiated_at']),
        ]

    def __str__(self):
        return f"OTA Update: {self.device.device_name} -> {self.firmware_version.version_number}"

    @property
    def duration(self):
        """Calculate update duration"""
        if self.started_at and self.completed_at:
            return self.completed_at - self.started_at
        elif self.started_at:
            return timezone.now() - self.started_at
        return None

    def add_log_entry(self, message, level='info'):
        """Add entry to update log"""
        if not self.update_log:
            self.update_log = []
        
        self.update_log.append({
            'timestamp': timezone.now().isoformat(),
            'level': level,
            'message': message
        })
        self.save(update_fields=['update_log'])

    def mark_started(self):
        """Mark update as started"""
        self.status = 'in_progress'
        self.started_at = timezone.now()
        self.add_log_entry("OTA update started")
        self.save(update_fields=['status', 'started_at'])

    def mark_completed(self):
        """Mark update as completed"""
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.progress_percentage = 100
        self.add_log_entry("OTA update completed successfully")
        self.save(update_fields=['status', 'completed_at', 'progress_percentage'])

    def mark_failed(self, error_message):
        """Mark update as failed"""
        self.status = 'failed'
        self.error_message = error_message
        self.completed_at = timezone.now()
        self.add_log_entry(f"OTA update failed: {error_message}", level='error')
        self.save(update_fields=['status', 'error_message', 'completed_at'])

    def update_progress(self, percentage, message=None):
        """Update progress percentage"""
        self.progress_percentage = min(100, max(0, percentage))
        if message:
            self.add_log_entry(f"Progress {percentage}%: {message}")
        self.save(update_fields=['progress_percentage'])


class DeviceFirmwareInfo(models.Model):
    """Model to store current firmware information for devices"""
    device = models.OneToOneField(Device, on_delete=models.CASCADE, related_name='firmware_info')
    current_version = models.CharField(max_length=50, blank=True, help_text="Current firmware version")
    last_updated = models.DateTimeField(null=True, blank=True)
    update_available = models.BooleanField(default=False)
    available_version = models.ForeignKey(FirmwareVersion, null=True, blank=True, on_delete=models.SET_NULL)
    auto_update_enabled = models.BooleanField(default=False, help_text="Enable automatic updates")
    last_check = models.DateTimeField(null=True, blank=True, help_text="Last time checked for updates")

    def __str__(self):
        return f"{self.device.device_name} - {self.current_version or 'Unknown'}"

    def check_for_updates(self):
        """Check if newer firmware version is available"""
        try:
            latest_firmware = FirmwareVersion.objects.filter(
                device_type=self.device.device_type,
                is_active=True
            ).order_by('-created_at').first()

            if latest_firmware and latest_firmware.version_number != self.current_version:
                self.update_available = True
                self.available_version = latest_firmware
            else:
                self.update_available = False
                self.available_version = None

            self.last_check = timezone.now()
            self.save(update_fields=['update_available', 'available_version', 'last_check'])
            return self.update_available
        except Exception as e:
            return False