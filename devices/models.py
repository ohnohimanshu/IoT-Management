from django.db import models
from django.utils import timezone
from accounts.models import CustomUser
from djongo import models as djongo_models
import requests
from datetime import timedelta
import logging

logger = logging.getLogger(__name__)

class Device(models.Model):
    device_name = models.CharField(max_length=100)
    device_id = models.CharField(max_length=100, unique=True)
    device_status = models.CharField(max_length=20, default='offline')
    last_seen = models.DateTimeField(null=True, blank=True)
    last_email_sent = models.DateTimeField(null=True, blank=True)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE)
    email = models.EmailField()
    email_interval = models.IntegerField(default=5)
    added_by = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='devices_added')
    ssid = models.CharField(max_length=100, blank=True, null=True)
    password = models.CharField(max_length=100, blank=True, null=True)
    static_ip = models.CharField(max_length=15, blank=True, null=True)
    device_type = models.CharField(max_length=20, choices=[
        ('esp', 'ESP'),
        ('lora', 'LoRa'),
        ('esp8266', 'ESP8266'),
        ('esp32', 'ESP32'),
        ('arduino', 'Arduino'),
        ('raspberry_pi', 'Raspberry Pi')
    ])
    last_status = models.CharField(max_length=20, null=True, blank=True)
    status_change_count = models.IntegerField(default=0)
    status_last_changed = models.DateTimeField(default=timezone.now)
    settings = djongo_models.JSONField(default=dict, null=True, blank=True)
    pending_status = models.CharField(max_length=20, null=True, blank=True)
    pending_status_time = models.DateTimeField(null=True, blank=True)
    notification_type = models.CharField(max_length=20, default='all', choices=[
        ('all', 'All Updates'),
        ('status_change', 'Status Changes Only'),
        ('critical', 'Critical Alerts Only')
    ])
    send_immediate = models.BooleanField(default=False)
    command_history = models.JSONField(default=list, blank=True)
    scheduled_commands = models.JSONField(default=list, blank=True)
    high_temp_threshold = models.FloatField(null=True, blank=True, help_text="Custom high temperature alert threshold for this device.")

    class Meta:
        db_table = 'devices_device'

    def __str__(self):
        return self.device_name

    def get_latest_data(self):
        """Get the latest data point for this device"""
        try:
            # Import here to avoid circular import
            from api.models import DeviceData
            latest_data = DeviceData.objects.filter(device=self).order_by('-timestamp').first()
            if latest_data:
                return {
                    'device_id': self.device_id,
                    'temperature': latest_data.data.get('temperature'),
                    'humidity': latest_data.data.get('humidity'),
                    'timestamp': latest_data.timestamp,
                    **latest_data.data  # Include all other data fields
                }
            return None
        except Exception as e:
            print(f"Error getting latest data for device {self.device_name}: {str(e)}")
            return None

    def check_status(self):
        """Check if the device is active based on last_seen timestamp"""
        if not self.last_seen:
            return 'offline'
        
        time_diff = (timezone.now() - self.last_seen).total_seconds()
        return 'online' if time_diff < 300 else 'offline'  # 5 minutes threshold

    def update_status(self):
        """Update device status based on last_seen timestamp"""
        current_status = self.check_status()
        if current_status != self.device_status:
            self.device_status = current_status
            self.save(update_fields=['device_status'])
        return current_status

    def add_command_to_history(self, command, status='pending', response=''):
        """Add a command to the device's command history"""
        if not self.command_history:
            self.command_history = []
            
        command_log = {
            'command': command,
            'status': status,
            'response': response,
            'timestamp': timezone.now().isoformat()
        }
        
        self.command_history.append(command_log)
        self.save(update_fields=['command_history'])
        return command_log

    def schedule_command(self, command, schedule_time):
        """Schedule a command for future execution"""
        if not self.scheduled_commands:
            self.scheduled_commands = []
            
        scheduled_command = {
            'command': command,
            'schedule_time': schedule_time.isoformat(),
            'status': 'pending',
            'created_at': timezone.now().isoformat()
        }
        
        self.scheduled_commands.append(scheduled_command)
        self.save(update_fields=['scheduled_commands'])
        return scheduled_command

    def get_pending_commands(self):
        """Get all pending scheduled commands that are due"""
        if not self.scheduled_commands:
            return []
            
        now = timezone.now()
        pending_commands = []
        
        for cmd in self.scheduled_commands:
            if cmd['status'] == 'pending':
                schedule_time = timezone.datetime.fromisoformat(cmd['schedule_time'].replace('Z', '+00:00'))
                if schedule_time <= now:
                    pending_commands.append(cmd)
                    
        return pending_commands

class PinConfig(models.Model):
    device = models.ForeignKey(Device, related_name='pins', on_delete=models.CASCADE)
    pin_number = models.IntegerField()
    pin_name = models.CharField(max_length=50)
    mode = models.CharField(max_length=10, choices=[
        ('input', 'Input'),
        ('output', 'Output'),
        ('on', 'On'),
        ('off', 'Off')
    ])

    class Meta:
        unique_together = ('device', 'pin_number')

class PinToggleLog(models.Model):
    device = models.ForeignKey(Device, related_name='toggle_logs', on_delete=models.CASCADE)
    pin_number = models.IntegerField()
    pin_name = models.CharField(max_length=50, default='Unknown Pin')  # Add default
    status = models.CharField(max_length=10, default='off')  # Add default
    timestamp = models.DateTimeField(default=timezone.now)
    
    class Meta:
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.device.device_name} - Pin {self.pin_number} - {self.status} at {self.timestamp}"

class DeviceStatusHistory(models.Model):
    device = models.ForeignKey(Device, related_name='status_history', on_delete=models.CASCADE)
    previous_status = models.CharField(max_length=20)
    new_status = models.CharField(max_length=20)
    changed_at = models.DateTimeField(auto_now_add=True)
    duration = models.DurationField(null=True, blank=True, help_text="Duration of the previous status")
    reason = models.CharField(max_length=100, null=True, blank=True, help_text="Reason for status change")
    is_confirmed = models.BooleanField(default=True, help_text="Whether this status change was confirmed")

    class Meta:
        indexes = [
            models.Index(fields=['device', '-changed_at']),
            models.Index(fields=['changed_at']),
        ]
        ordering = ['-changed_at']

    def __str__(self):
        return f"{self.device.device_name} - {self.previous_status} → {self.new_status} at {self.changed_at}"

    @classmethod
    def get_daily_summary(cls, device, start_time, end_time):
        """
        Get status history summary for a specific time period
        Returns: dict with status statistics
        
        This method now correctly handles:
        - Initial device state before the time window
        - Scenarios with no status changes
        - Accurate time calculations that sum to the full period
        """
        # Get status changes within the time period
        history = cls.objects.filter(
            device=device,
            changed_at__gte=start_time,
            changed_at__lte=end_time
        ).order_by('changed_at')

        # Get the most recent status change BEFORE start_time to determine initial state
        initial_state_record = cls.objects.filter(
            device=device,
            changed_at__lt=start_time
        ).order_by('-changed_at').first()

        # Determine what status the device had at start_time
        if initial_state_record:
            current_status_at_start = initial_state_record.new_status
        else:
            # No history before start_time, use device's current status or default to offline
            current_status_at_start = device.device_status if device.device_status else 'offline'
        
        # Normalize status to lowercase for consistent comparison
        current_status_at_start = current_status_at_start.lower()

        # Initialize tracking variables
        periods = []
        total_active_time = 0
        total_inactive_time = 0
        changes = []

        # Helper function to determine if a status is "active"
        def is_active_status(status):
            return status.lower() in ['active', 'online']

        # Case 1: No status changes during the period
        if not history.exists():
            # Calculate full duration based on initial state
            total_duration_minutes = (end_time - start_time).total_seconds() / 60
            
            if is_active_status(current_status_at_start):
                total_active_time = total_duration_minutes
                total_inactive_time = 0
                active_percentage = 100.0
            else:
                total_active_time = 0
                total_inactive_time = total_duration_minutes
                active_percentage = 0.0

            # Add single period for the entire duration
            periods.append({
                'start_time': start_time,
                'end_time': end_time,
                'from_status': current_status_at_start,
                'to_status': current_status_at_start,
                'duration': total_duration_minutes
            })

            return {
                'total_changes': 0,
                'total_active_time': total_active_time,
                'total_inactive_time': total_inactive_time,
                'active_percentage': active_percentage,
                'detailed_periods': periods,
                'changes': []
            }

        # Case 2: There are status changes during the period
        # First, add the initial period from start_time to first change
        first_change = history[0]
        initial_duration = (first_change.changed_at - start_time).total_seconds() / 60

        if initial_duration > 0:
            # Track time for initial period
            if is_active_status(current_status_at_start):
                total_active_time += initial_duration
            else:
                total_inactive_time += initial_duration

            # Add to periods list
            periods.append({
                'start_time': start_time,
                'end_time': first_change.changed_at,
                'from_status': current_status_at_start,
                'to_status': current_status_at_start,
                'duration': initial_duration
            })

        # Now process all status changes within the period
        for i, record in enumerate(history):
            # Calculate duration for this status
            if i < len(history) - 1:
                # Duration until next change
                duration = history[i + 1].changed_at - record.changed_at
            else:
                # Duration until end of period
                duration = end_time - record.changed_at

            # Convert duration to minutes
            duration_minutes = duration.total_seconds() / 60

            # Track active/inactive time based on the NEW status
            if is_active_status(record.new_status):
                total_active_time += duration_minutes
            else:
                total_inactive_time += duration_minutes

            # Add to periods list
            periods.append({
                'start_time': record.changed_at,
                'end_time': record.changed_at + duration,
                'from_status': record.previous_status,
                'to_status': record.new_status,
                'duration': duration_minutes
            })

            # Add to changes list (all changes are not initial since we handled initial period separately)
            changes.append({
                'timestamp': record.changed_at,
                'status': record.new_status,
                'is_initial': False
            })

        # Calculate active percentage
        total_time = total_active_time + total_inactive_time
        active_percentage = (total_active_time / total_time * 100) if total_time > 0 else 0

        return {
            'total_changes': len(history),
            'total_active_time': total_active_time,
            'total_inactive_time': total_inactive_time,
            'active_percentage': active_percentage,
            'detailed_periods': periods,
            'changes': changes
        }

    @classmethod
    def get_status_duration(cls, device, status, start_time, end_time):
        """
        Get total duration of a specific status within a time period
        """
        history = cls.objects.filter(
            device=device,
            changed_at__gte=start_time,
            changed_at__lte=end_time,
            new_status=status
        ).order_by('changed_at')

        total_duration = 0
        for record in history:
            if record.duration:
                total_duration += record.duration.total_seconds()

        return total_duration / 60  # Convert to minutes

class ScheduledCommand(models.Model):
    device = models.ForeignKey(Device, on_delete=models.CASCADE, related_name='command_schedules')
    pin_number = models.IntegerField()
    action = models.CharField(max_length=10, choices=[('on', 'On'), ('off', 'Off')])
    scheduled_time = models.DateTimeField()
    repeat = models.CharField(max_length=10, choices=[
        ('once', 'Once'),
        ('daily', 'Daily'),
        ('weekly', 'Weekly')
    ], default='once')
    is_executed = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-scheduled_time']

    def __str__(self):
        return f"{self.device.device_name} - Pin {self.pin_number} {self.action} at {self.scheduled_time}"

    def execute(self):
        try:
            # Create a command to send to the device
            command = {
                'pin_number': self.pin_number,
                'action': self.action,
                'timestamp': timezone.now().isoformat()
            }
            
            # Send command to device
            response = requests.post(
                f"http://{self.device.static_ip}/command",
                json=command,
                timeout=5
            )
            
            if response.status_code == 200:
                # Log the pin toggle
                PinToggleLog.objects.create(
                    device=self.device,
                    pin_number=self.pin_number,
                    action=self.action,
                    status='success'
                )
                
                # Update repeat schedule if needed
                if self.repeat != 'once':
                    self.scheduled_time = self.get_next_schedule_time()
                    self.is_executed = False
                    self.save()
                else:
                    self.is_executed = True
                    self.save()
                
                return True
            else:
                logger.error(f"Failed to execute scheduled command: {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Error executing scheduled command: {str(e)}")
            return False

    def get_next_schedule_time(self):
        if self.repeat == 'daily':
            return self.scheduled_time + timedelta(days=1)
        elif self.repeat == 'weekly':
            return self.scheduled_time + timedelta(weeks=1)
        return self.scheduled_time

