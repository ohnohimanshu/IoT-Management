from celery import shared_task
from django.utils import timezone
from .services import OTAUpdateService
from .models import OTAUpdate
import logging

logger = logging.getLogger(__name__)


@shared_task
def check_for_firmware_updates():
    """
    Periodic task to check for firmware updates for all devices
    """
    try:
        service = OTAUpdateService()
        updates_found = service.check_all_devices_for_updates()
        logger.info(f"Firmware update check completed. Found {updates_found} devices with updates available.")
        return f"Found {updates_found} devices with updates available"
    except Exception as e:
        logger.error(f"Error in firmware update check task: {str(e)}")
        return f"Error: {str(e)}"


@shared_task
def auto_update_devices():
    """
    Periodic task to automatically update devices with auto-update enabled
    """
    try:
        service = OTAUpdateService()
        updated_count = service.auto_update_devices()
        logger.info(f"Auto-update task completed. Started updates for {updated_count} devices.")
        return f"Started auto-updates for {updated_count} devices"
    except Exception as e:
        logger.error(f"Error in auto-update task: {str(e)}")
        return f"Error: {str(e)}"


@shared_task
def cleanup_old_ota_updates():
    """
    Clean up old OTA update records (keep last 100 per device)
    """
    try:
        from devices.models import Device
        
        cleanup_count = 0
        devices = Device.objects.filter(device_type__in=['esp', 'esp32', 'esp8266'])
        
        for device in devices:
            # Keep only the latest 100 OTA updates per device
            old_updates = OTAUpdate.objects.filter(device=device).order_by('-initiated_at')[100:]
            
            for update in old_updates:
                update.delete()
                cleanup_count += 1
        
        logger.info(f"Cleaned up {cleanup_count} old OTA update records")
        return f"Cleaned up {cleanup_count} old OTA update records"
        
    except Exception as e:
        logger.error(f"Error in cleanup task: {str(e)}")
        return f"Error: {str(e)}"


@shared_task
def timeout_stalled_updates():
    """
    Mark stalled OTA updates as failed after timeout period
    """
    try:
        timeout_minutes = 30  # 30 minutes timeout
        timeout_time = timezone.now() - timezone.timedelta(minutes=timeout_minutes)
        
        stalled_updates = OTAUpdate.objects.filter(
            status='in_progress',
            started_at__lt=timeout_time
        )
        
        timeout_count = 0
        for update in stalled_updates:
            update.mark_failed(f"Update timed out after {timeout_minutes} minutes")
            timeout_count += 1
            logger.warning(f"Marked OTA update {update.id} as failed due to timeout")
        
        logger.info(f"Marked {timeout_count} stalled OTA updates as failed")
        return f"Marked {timeout_count} stalled updates as failed"
        
    except Exception as e:
        logger.error(f"Error in timeout task: {str(e)}")
        return f"Error: {str(e)}"