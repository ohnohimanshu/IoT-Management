from django.db import models
from devices.models import Device

class ProcessedData(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='processed_data')
    average_temperature = models.FloatField()
    average_humidity = models.FloatField()
    average_signal_strength = models.FloatField(null=True, blank=True)  # New Field
    data_date = models.DateField()

    def __str__(self):
        return f"Processed data for {self.device.device_name} on {self.data_date}"
