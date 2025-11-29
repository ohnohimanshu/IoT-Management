import time
import traceback
import logging
from django.utils import timezone
from django.db import transaction
from devices.models import Device, DeviceStatusHistory
from .email_service import send_email_alert

logger = logging.getLogger(__name__)

# Constants
INACTIVITY_THRESHOLD = 30  # Seconds before a device is considered inactive
EMAIL_RATE_LIMIT = 60  # Minimum seconds between emails for the same device
STATUS_CONFIRMATION_WAIT = 90  # Wait 90 seconds to confirm status change before sending email
MONITOR_INTERVAL = 30  # How often to run the monitoring loop

def verify_device_status(device, now):
    """
    Determine the current status of a device based on last_seen timestamp
    Returns: (new_status, has_changed)
    """
    if not device.last_seen:
        return "Inactive", device.last_status != "Inactive"
    
    seconds = (now - device.last_seen).total_seconds()
    new_status = "Active" if seconds < INACTIVITY_THRESHOLD else "Inactive"
    
    # Make sure we detect changes in both directions
    has_changed = new_status != device.last_status
    
    logger.debug(f"Status check for {device.device_name}: current={new_status}, last={device.last_status}, changed={has_changed}")
    return new_status, has_changed

def update_device_status(device, new_status, now):
    """
    Update the device status in the database and create a status history record
    """
    try:
        with transaction.atomic():
            device.refresh_from_db()
            previous = device.last_status
            
            # Calculate duration of previous status
            duration = None
            if previous:
                last_change = DeviceStatusHistory.objects.filter(
                    device=device,
                    new_status=previous
                ).order_by('-changed_at').first()
                
                if last_change:
                    duration = now - last_change.changed_at

            device.last_status = new_status
            device.device_status = new_status.lower()  # Update both status fields
            device.status_last_changed = now
            device.status_change_count += 1
            device.save(update_fields=['last_status', 'device_status', 'status_last_changed', 'status_change_count'])

            # Create status history record with duration
            DeviceStatusHistory.objects.create(
                device=device,
                previous_status=previous,
                new_status=new_status,
                changed_at=now,
                duration=duration,
                reason=f"Status change detected after {INACTIVITY_THRESHOLD}s threshold",
                is_confirmed=True
            )
            print(f"🔄 Status updated for {device.device_name}: {previous} -> {new_status}")
            return True
    except Exception as e:
        logger.error(f"Status update failed for {device.device_name}: {e}")
        return False

def process_device(device_id):
    """
    Process a single device to determine status changes and send notifications
    """
    max_retries = 3
    retry_delay = 1  # seconds
    
    for attempt in range(max_retries):
        try:
            with transaction.atomic():
                # Remove nowait=True to prevent immediate failure on lock
                device = Device.objects.select_for_update().get(id=device_id)
                now = timezone.now()

                if not device.email:
                    logger.debug(f"{device.device_name} missing email")
                    return True

                current_status, has_changed = verify_device_status(device, now)
                
                # If status is same as last_status, check if there's a pending status that should be cleared
                if not has_changed:
                    if device.pending_status:
                        # Status has reverted to previous state, clear pending status
                        logger.info(f"Status reverted for {device.device_name}: pending {device.pending_status} cleared")
                        device.pending_status = None
                        device.pending_status_time = None
                        device.save(update_fields=['pending_status', 'pending_status_time'])
                    return True
                
                # If status has changed
                logger.info(f"Potential status change for {device.device_name}: {device.last_status} -> {current_status}")
                
                # Check if there's already a pending status change
                if device.pending_status == current_status:
                    # Same pending status - check if it's been stable for STATUS_CONFIRMATION_WAIT seconds
                    time_pending = (now - device.pending_status_time).total_seconds()
                    
                    if time_pending >= STATUS_CONFIRMATION_WAIT:
                        # RE-VERIFY status one final time before sending email
                        device.refresh_from_db()  # Get latest data from database
                        current_status_recheck, _ = verify_device_status(device, now)
                        
                        if current_status_recheck != current_status:
                            # Status changed during confirmation wait - cancel email
                            logger.info(f"❌ Status changed during confirmation for {device.device_name}: {current_status} -> {current_status_recheck}. Cancelling email.")
                            print(f"❌ Status changed during confirmation for {device.device_name}: {current_status} -> {current_status_recheck}. Cancelling email.")
                            device.pending_status = None
                            device.pending_status_time = None
                            device.save(update_fields=['pending_status', 'pending_status_time'])
                            return True
                        
                        # Status is STILL the same after confirmation wait - proceed with email
                        logger.info(f"✅ Confirmed status change after {time_pending:.1f}s: {device.device_name} {device.last_status} -> {current_status}")
                        print(f"✅ Confirmed status change after {time_pending:.1f}s: {device.device_name} {device.last_status} -> {current_status}")
                        
                        # First send the email notification (BEFORE updating status in DB)
                        time_since_last = (now - device.last_email_sent).total_seconds() if device.last_email_sent else float('inf')
                        
                        if time_since_last >= EMAIL_RATE_LIMIT:
                            # Force email sending with explicit logging
                            logger.info(f"⚠️ Attempting to send email for {device.device_name} → {current_status}")
                            print(f"⚠️ Attempting to send email for {device.device_name} → {current_status} to {device.email}")
                            
                            # Make sure device email is not empty
                            if not device.email:
                                logger.error(f"❌ Device {device.device_name} has no email address configured")
                                print(f"❌ Device {device.device_name} has no email address configured")
                            else:
                                # Try to send email with detailed logging
                                email_success = send_email_alert(device.device_id, current_status, device.email)
                                logger.info(f"📧 Email sending {'successful' if email_success else 'FAILED'}")
                                print(f"📧 Email sending {'successful' if email_success else 'FAILED'}")
                        else:
                            logger.info(f"Email rate limited for {device.device_name} ({time_since_last:.1f}s < {EMAIL_RATE_LIMIT}s)")
                            print(f"Email rate limited for {device.device_name} ({time_since_last:.1f}s < {EMAIL_RATE_LIMIT}s)")
                        
                        # Then update status in database
                        update_device_status(device, current_status, now)
                        
                        # Clear pending status
                        device.pending_status = None
                        device.pending_status_time = None
                        device.save(update_fields=['pending_status', 'pending_status_time'])
                    else:
                        logger.debug(f"Waiting for confirmation: {device.device_name} {current_status} for {time_pending:.1f}s/{STATUS_CONFIRMATION_WAIT}s")
                else:
                    # New pending status or different pending status - update and reset timer
                    logger.info(f"Setting pending status for {device.device_name}: {current_status}")
                    device.pending_status = current_status
                    device.pending_status_time = now
                    device.save(update_fields=['pending_status', 'pending_status_time'])
            
            return True

        except Device.DoesNotExist:
            logger.error(f"Device ID {device_id} not found")
            return False
        except Exception as e:
            if attempt < max_retries - 1:
                logger.warning(f"Attempt {attempt + 1} failed for device {device_id}: {str(e)}")
                time.sleep(retry_delay)
                retry_delay *= 2  # Exponential backoff
            else:
                logger.error(f"All {max_retries} attempts failed for device {device_id}: {str(e)}")
                traceback.print_exc()
                return False
    
    return False

def monitor_device_status():
    """
    Main monitoring loop - continuously checks all devices for status changes
    """
    logger.info("🚀 Starting device monitoring loop")
    print("🚀 Background Task Running: Device Status Monitor")
    
    while True:
        start = time.time()
        success, fail = 0, 0
        
        try:
            ids = Device.objects.values_list('id', flat=True)
            for device_id in ids:
                if process_device(device_id):
                    success += 1
                else:
                    fail += 1
            
            logger.info(f"Monitoring cycle complete: {success} ok, {fail} errors")
        except Exception as e:
            logger.critical(f"Monitor cycle failed: {e}")
            traceback.print_exc()
        
        # Wait for next monitoring interval, accounting for processing time
        elapsed = time.time() - start
        wait_time = max(0, MONITOR_INTERVAL - elapsed)
        time.sleep(wait_time)