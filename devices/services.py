from django.utils import timezone
from django.db import transaction
import logging

# Configure logging
logger = logging.getLogger(__name__)

# Constants
TIME_ZONE = 'Asia/Kolkata'  # Use Django's timezone utilities instead of direct pytz

class DeviceService:
    @staticmethod
    def save_device(device):
        """
        Handle device status changes and history tracking.
        """
        with transaction.atomic():
            try:
                now = timezone.localtime(timezone.now())
                
                if device.pk is not None:
                    try:
                        old_instance = device.__class__.objects.select_for_update().get(pk=device.pk)
                        
                        if old_instance.device_status != device.device_status:
                            logger.info(f"Status change detected for device {device.device_name}")
                            
                            # Create status history record
                            device.__class__.status_history.create(
                                device=device,
                                previous_status=old_instance.device_status,
                                new_status=device.device_status,
                                changed_at=now
                            )
                            
                            device.last_status = old_instance.device_status
                            device.status_change_count += 1
                            device.status_last_changed = now
                            
                            logger.info(f"Status change recorded for device {device.device_name}")
                    except device.__class__.DoesNotExist:
                        logger.warning(f"Could not find old instance for device {device.device_name}")
                    except Exception as e:
                        logger.error(f"Error processing status change for device {device.device_name}: {e}")
                        raise
                
                device.status_last_changed = now
                device.save()
                
            except Exception as e:
                logger.error(f"Error saving device {device.device_name}: {e}")
                raise

    @staticmethod
    def reset_status_change_count(device):
        """
        Reset status change count if 24 hours have passed since last change.
        """
        try:
            now = timezone.localtime(timezone.now())
            last_change = timezone.localtime(device.status_last_changed)
            
            hours_since_last_change = (now - last_change).total_seconds() / 3600
            
            if hours_since_last_change >= 24:
                logger.info(f"Resetting status change count for device {device.device_name}")
                
                with transaction.atomic():
                    device_obj = device.__class__.objects.select_for_update().get(pk=device.pk)
                    device_obj.status_change_count = 0
                    device_obj.save(update_fields=['status_change_count'])
                
                logger.info(f"Status change count reset for device {device.device_name}")
            else:
                logger.debug(f"Status change count not reset for device {device.device_name}")
                
        except Exception as e:
            logger.error(f"Error resetting status change count for device {device.device_name}: {e}")
            raise

def execute_scheduled_commands():
    """
    Run all scheduled commands for devices that are due and not yet executed.
    """
    from devices.models import ScheduledCommand
    from django.utils import timezone
    now = timezone.now()

    # Use correct field names from your model
    due_commands = ScheduledCommand.objects.filter(
        scheduled_time__lte=now,
        is_executed=False
    )

    for cmd in due_commands:
        try:
            # TODO: Add your actual device execution logic here
            cmd.is_executed = True
            cmd.updated_at = now  # since you have no 'executed_at' field
            cmd.save()
        except Exception as e:
            logger.error(f"Failed to execute scheduled command {cmd.id}: {e}")
