from django.utils import timezone
from django.conf import settings
from devices.models import Device
from .email_service import send_daily_summary_email
import logging
import traceback
from celery import shared_task

logger = logging.getLogger(__name__)

@shared_task(bind=True, max_retries=3, default_retry_delay=300)
def send_daily_summaries(self):
    """
    Send daily summary emails for all devices at 9 AM
    
    This task:
    - Runs daily at 9 AM (IST)
    - Sends summary emails to all active devices
    - Includes retry logic on failure
    - Logs all attempts and results
    """
    try:
        logger.info("🚀 Starting daily summary email task")
        
        # Get all devices that are not in an error state
        devices = Device.objects.exclude(device_status__in=['error', 'offline'])
        
        if not devices.exists():
            logger.warning("⚠️ No active devices found for sending daily summaries")
            return {"status": "completed", "devices_processed": 0, "success": 0, "failed": 0}
        
        success_count = 0
        failed_count = 0
        
        for device in devices:
            try:
                logger.info(f"📧 Processing daily summary for device: {device.device_name} ({device.device_id})")
                
                if not device.email:
                    logger.warning(f"⚠️ Device {device.device_name} has no email configured, skipping")
                    failed_count += 1
                    continue
                
                success = send_daily_summary_email(device.device_id)
                
                if success:
                    success_count += 1
                    logger.info(f"✅ Successfully sent daily summary for device {device.device_name}")
                else:
                    failed_count += 1
                    logger.error(f"❌ Failed to send daily summary for device {device.device_name}")
                    
            except Exception as e:
                failed_count += 1
                logger.error(f"❌ Error processing device {device.device_name}: {str(e)}")
                traceback.print_exc()
        
        result = {
            "status": "completed",
            "devices_processed": len(devices),
            "success": success_count,
            "failed": failed_count
        }
        
        logger.info(f"✅ Completed daily summary email task - {result}")
        return result
        
    except Exception as e:
        logger.error(f"❌ Critical error in send_daily_summaries task: {str(e)}")
        traceback.print_exc()
        
        # Retry on critical errors
        try:
            self.retry(exc=e)
        except self.MaxRetriesExceededError:
            logger.critical(f"❌ Max retries exceeded for daily summary task")
            return {"status": "failed", "error": str(e), "retries_exhausted": True} 