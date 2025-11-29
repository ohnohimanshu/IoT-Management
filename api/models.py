from django.db import models
from djongo import models as djongo_models

class DeviceData(models.Model):
    device = models.ForeignKey(
        'devices.Device',  # Use string reference to avoid circular import
        on_delete=models.CASCADE,
        related_name='sensor_readings'
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    data = djongo_models.JSONField(default=dict)  # MongoDB compatible JSON field

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['device', '-timestamp']),
        ]

    def __str__(self):
        return f"{self.device.device_name} - {self.timestamp}"

    def get_sensor_data(self):
        """Helper method to get formatted sensor data"""
        return {
            'temperature': self.data.get('temperature'),
            'humidity': self.data.get('humidity'),
            'other_sensors': {
                k: v for k, v in self.data.items()
                if k not in ['temperature', 'humidity']
            }
        }