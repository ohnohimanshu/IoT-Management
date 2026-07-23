
from django.db import models
from accounts.models import CustomUser
from devices.models import Device
from django.utils import timezone

class MailerConfiguration(models.Model):
    """Singleton model to store mailer configuration settings"""
    
    # Device Monitor Settings
    inactivity_threshold = models.IntegerField(
        default=30,  # Default in seconds
        help_text="Seconds before device is considered inactive"
    )
    email_rate_limit = models.IntegerField(
        default=60,  # Default in seconds
        help_text="Minimum seconds between emails for same device"
    )
    status_confirmation_wait = models.IntegerField(
        default=90,  # Default in seconds
        help_text="Wait seconds to confirm status change before sending email"
    )
    monitor_interval = models.IntegerField(
        default=30,  # Default in seconds
        help_text="How often to run the monitoring loop (check all devices)"
    )
    
    # Temperature Monitor Settings
    temperature_check_interval = models.IntegerField(
        default=300,  # Default 5 minutes
        help_text="Interval to check device temperatures (seconds)"
    )
    temperature_alert_interval = models.IntegerField(
        default=300,  # Default 5 minutes
        help_text="Interval to send repeat temperature alerts (seconds)"
    )
    
    # LoRa Monitor Settings
    lora_check_interval = models.IntegerField(
        default=30,  # Default in seconds
        help_text="LoRa device check interval (seconds)"
    )
    lora_notification_interval = models.IntegerField(
        default=300,  # Default 5 minutes
        help_text="LoRa device notification interval (seconds)"
    )
    
    class Meta:
        db_table = 'mailer_configuration'
        
    def save(self, *args, **kwargs):
        # Ensure only one instance exists
        self.pk = 1
        super(MailerConfiguration, self).save(*args, **kwargs)
        
    @classmethod
    def get_config(cls):
        """Get or create the singleton configuration instance"""
        obj, created = cls.objects.get_or_create(pk=1)
        return obj
        
    def __str__(self):
        return "Mailer Configuration"

class EmailRecipient(models.Model):
    email = models.EmailField()
    added_at = models.DateTimeField(auto_now_add=True)  # Automatically set on creation
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return self.email




class Alert(models.Model):
    SEVERITY_CHOICES = (
        ('high', 'High'),
        ('medium', 'Medium'),
        ('low', 'Low'),
    )
    
    title = models.CharField(max_length=200)
    message = models.TextField()
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='medium')
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='alerts', null=True, blank=True)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='alerts')
    timestamp = models.DateTimeField(default=timezone.now)
    is_read = models.BooleanField(default=False)
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['device', '-timestamp']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.severity} ({self.timestamp.strftime('%Y-%m-%d %H:%M')})"
    

class EmailLog(models.Model):
    EMAIL_TYPE_CHOICES = (
        ('alert', 'Alert'),
        ('summary', 'Daily Summary'),
    )
    
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='email_logs')
    recipient_email = models.EmailField()
    email_type = models.CharField(max_length=10, choices=EMAIL_TYPE_CHOICES)
    subject = models.CharField(max_length=200)
    sent_at = models.DateTimeField(auto_now_add=True)
    status = models.BooleanField(default=True)  # True for success, False for failure
    error_message = models.TextField(null=True, blank=True)
    
    class Meta:
        ordering = ['-sent_at']
        indexes = [
            models.Index(fields=['device', '-sent_at']),
            models.Index(fields=['recipient_email', '-sent_at']),
        ]
    
    def __str__(self):
        return f"{self.email_type} email to {self.recipient_email} for {self.device.device_name}"
