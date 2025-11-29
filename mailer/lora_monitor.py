import time
from datetime import datetime, timedelta
from django.utils import timezone
from django.db.models import Q
from devices.models import Device
from .email_service import send_lora_power_status_email, send_email_alert
import logging
import threading

logger = logging.getLogger(__name__)

class LoraDeviceMonitor:
    def __init__(self):
        self.offline_devices = {}  # Dictionary to track offline devices and their last notification time
        self.inactive_devices = {}  # Dictionary to track devices not sending data
        self.check_interval = 30   # Check every 30 seconds
        self.notification_interval = 300  # Send notification every 5 minutes (300 seconds)
        self.inactivity_threshold = 30  # Seconds before a device is considered inactive
        self.inactivity_confirmation_wait = 90  # Wait 90 seconds before sending inactivity email

    def check_device_status(self, device_data):
        """
        Check the status of a LoRa device and handle notifications
        device_data should contain: device_id, status, timestamp
        """
        try:
            device_id = device_data.get('device_id')
            status = device_data.get('status', '').upper()
            timestamp = device_data.get('timestamp', timezone.now())

            if not device_id or not status:
                logger.error("Invalid device data received")
                return

            logger.info(f"Received status '{status}' for device {device_id} at {timestamp}")

            # Get the device
            try:
                device = Device.objects.get(device_id=device_id)
            except Device.DoesNotExist:
                logger.error(f"Device {device_id} not found")
                return

            # Only process LoRa devices
            if not device.device_type.lower() == 'lora':
                logger.info(f"Device {device_id} is not a LoRa device, skipping")
                return

            current_time = timezone.now()
            current_state = device.last_status

            logger.info(f"Current state for device {device_id}: {current_state}")
            
            # Validate status - only accept 'ON' or 'OFF'
            if status not in ['ON', 'OFF']:
                logger.warning(f"Invalid status '{status}' received for device {device_id}. Ignoring.")
                return
                
            # This function should only be called when there's a real status change
            # The API view should have already verified this is a genuine status change
            # Double-check to be safe
            if current_state != status:
                logger.info(f"Confirmed status change for device {device_id}: {current_state} -> {status}")
                
                # Update the device's last_status in the database
                device.last_status = status
                device.save(update_fields=['last_status'])

                if status == 'OFF':
                    # Device just went offline - start tracking for 30s delay
                    self.offline_devices[device_id] = {
                        'first_offline': timestamp,
                        'last_notification': None # No notification sent yet
                    }
                    logger.info(f"Device {device_id} went OFF. Starting 30s delay before first notification.")

                elif status == 'ON':
                    # Device just came back online - send only ONE notification
                    if device_id in self.offline_devices:
                        logger.info(f"Sending ONE email for device {device_id} due to state change from {current_state} to {status}")
                        send_lora_power_status_email(device_id, 'ON', device.email)
                        del self.offline_devices[device_id]
            else:
                # Status hasn't changed - this shouldn't happen with the API filter in place
                # but handle it gracefully just in case
                logger.warning(f"Received redundant status update for device {device_id}: {status} (already in this state)")
                
                # Still check if it's an OFF status requiring delayed or periodic notification
                if status == 'OFF' and device_id in self.offline_devices:
                    offline_data = self.offline_devices[device_id]
                    first_offline = offline_data['first_offline']
                    last_notification = offline_data['last_notification']
                    time_since_offline = (current_time - first_offline).total_seconds()

                    logger.info(f"Device {device_id} is still OFF. Offline duration: {time_since_offline:.1f}s. Last notification sent at: {last_notification}")

                    # Check if 30 seconds have passed to send the initial OFF email
                    if time_since_offline >= 30 and last_notification is None:
                        logger.info(f"Device {device_id} has been OFF for >= 30s and initial email not sent. Sending now.")
                        send_lora_power_status_email(device_id, 'OFF', device.email)
                        self.offline_devices[device_id]['last_notification'] = current_time
                        logger.info(f"Initial OFF email sent for device {device_id}. Updated last_notification.")

                    # Check if it's time to send a periodic email (after the initial one has been sent)
                    elif last_notification is not None and \
                         (current_time - last_notification).total_seconds() >= self.notification_interval:
                        logger.info(f"Device {device_id} is still OFF. Sending periodic email. Interval: {self.notification_interval}s")
                        send_lora_power_status_email(device_id, 'OFF', device.email)
                        self.offline_devices[device_id]['last_notification'] = current_time
                        logger.info(f"Periodic OFF email sent for device {device_id}. Updated last_notification.")

                elif status == 'ON':
                    # If status is ON and unchanged, ensure it's not in offline_devices (shouldn't happen with correct logic, but good for cleanup)
                    if device_id in self.offline_devices:
                        logger.warning(f"Device {device_id} is ON but found in offline_devices. Removing.")
                        del self.offline_devices[device_id]

        except Exception as e:
            logger.error(f"Error in check_device_status: {str(e)}")

    def cleanup_old_offline_devices(self):
        """Remove devices that have been offline for too long from tracking"""
        current_time = timezone.now()
        devices_to_remove = []

        for device_id, data in self.offline_devices.items():
            # Remove devices that have been offline for more than 24 hours
            offline_duration = (current_time - data['first_offline']).total_seconds()
            if offline_duration > 86400:  # 24 hours
                logger.info(f"🧹 Removing device {device_id} from offline tracking - offline for {offline_duration/3600:.1f} hours")
                devices_to_remove.append(device_id)

        for device_id in devices_to_remove:
            del self.offline_devices[device_id]
            logger.info(f"🗑️ Cleaned up device {device_id} from offline tracking")

        if devices_to_remove:
            logger.info(f"🧹 Offline cleanup completed: removed {len(devices_to_remove)} devices from tracking")
            
    def cleanup_old_inactive_devices(self):
        """Remove devices that have been inactive for too long from tracking"""
        current_time = timezone.now()
        devices_to_remove = []

        for device_id, data in self.inactive_devices.items():
            # Remove devices that have been inactive for more than 24 hours
            inactive_duration = (current_time - data['first_inactive']).total_seconds()
            if inactive_duration > 86400:  # 24 hours
                logger.info(f"🧹 Removing device {device_id} from inactive tracking - inactive for {inactive_duration/3600:.1f} hours")
                devices_to_remove.append(device_id)

        for device_id in devices_to_remove:
            del self.inactive_devices[device_id]
            logger.info(f"🗑️ Cleaned up device {device_id} from inactive tracking")

        if devices_to_remove:
            logger.info(f"🧹 Inactive cleanup completed: removed {len(devices_to_remove)} devices from tracking")

    def get_status(self):
        """Get current monitoring status"""
        status_info = {
            'offline_devices': {},
            'inactive_devices': {},
            'check_interval': self.check_interval,
            'notification_interval': self.notification_interval,
            'inactivity_threshold': self.inactivity_threshold,
            'inactivity_confirmation_wait': self.inactivity_confirmation_wait,
            'total_offline_devices': len(self.offline_devices),
            'total_inactive_devices': len(self.inactive_devices)
        }
        
        # Add detailed info for each offline device
        current_time = timezone.now()
        for device_id, data in self.offline_devices.items():
            offline_duration = (current_time - data['first_offline']).total_seconds()
            last_notification = data.get('last_notification')
            time_since_last_notification = None
            
            if last_notification:
                time_since_last_notification = (current_time - last_notification).total_seconds()
            
            status_info['offline_devices'][device_id] = {
                'first_offline': data['first_offline'].isoformat(),
                'offline_duration_seconds': offline_duration,
                'offline_duration_minutes': offline_duration / 60,
                'last_notification': last_notification.isoformat() if last_notification else None,
                'time_since_last_notification_seconds': time_since_last_notification
            }
        
        # Add detailed info for each inactive device
        for device_id, data in self.inactive_devices.items():
            inactive_duration = (current_time - data['first_inactive']).total_seconds()
            last_notification = data.get('last_notification')
            time_since_last_notification = None
            
            if last_notification:
                time_since_last_notification = (current_time - last_notification).total_seconds()
            
            status_info['inactive_devices'][device_id] = {
                'first_inactive': data['first_inactive'].isoformat(),
                'inactive_duration_seconds': inactive_duration,
                'inactive_duration_minutes': inactive_duration / 60,
                'last_notification': last_notification.isoformat() if last_notification else None,
                'time_since_last_notification_seconds': time_since_last_notification
            }
        
        return status_info

    def force_check_all_lora_devices(self):
        """Manually check all LoRa devices in database and sync with tracking"""
        logger.info("🔍 Starting manual check of all LoRa devices")
        
        try:
            lora_devices = Device.objects.filter(device_type__iexact='lora')
            logger.info(f"Found {lora_devices.count()} LoRa devices in database")
            
            for device in lora_devices:
                current_status = device.last_status.upper() if device.last_status else 'UNKNOWN'
                is_tracked = device.device_id in self.offline_devices
                
                logger.info(f"Device {device.device_id}: status={current_status}, tracked={is_tracked}")
                
                if current_status == 'OFF' and not is_tracked:
                    logger.info(f"Adding device {device.device_id} to offline tracking (found during manual check)")
                    self.offline_devices[device.device_id] = {
                        'first_offline': timezone.now(),
                        'last_notification': timezone.now()
                    }
                elif current_status == 'ON' and is_tracked:
                    logger.info(f"Removing device {device.device_id} from offline tracking (found online during manual check)")
                    del self.offline_devices[device.device_id]
                    
        except Exception as e:
            logger.error(f"❌ Error during manual check of LoRa devices: {str(e)}")
            import traceback
            traceback.print_exc()

    def check_device_inactivity(self):
        """Check all LoRa devices for inactivity (not sending data)"""
        try:
            current_time = timezone.now()
            lora_devices = Device.objects.filter(device_type__iexact='lora')
            
            for device in lora_devices:
                device_id = device.device_id
                
                # Skip devices that are already being tracked for power status (OFF)
                if device_id in self.offline_devices:
                    continue
                    
                # Check if device has been inactive
                if device.last_seen:
                    time_since_last_seen = (current_time - device.last_seen).total_seconds()
                    
                    # Device not sending data for more than inactivity_threshold
                    if time_since_last_seen > self.inactivity_threshold:
                        if device_id not in self.inactive_devices:
                            # First time detecting inactivity - start tracking but don't send email yet
                            logger.info(f"Device {device_id} not sending data for {time_since_last_seen:.1f}s. Starting 60s confirmation tracking.")
                            self.inactive_devices[device_id] = {
                                'first_inactive': current_time,
                                'last_notification': None  # No notification sent yet
                            }
                        else:
                            # Already tracking this inactive device
                            inactive_data = self.inactive_devices[device_id]
                            first_inactive = inactive_data['first_inactive']
                            last_notification = inactive_data['last_notification']
                            time_since_inactive = (current_time - first_inactive).total_seconds()
                            
                            # Send initial notification only after 90 seconds of inactivity
                            if last_notification is None and time_since_inactive >= self.inactivity_confirmation_wait:
                                logger.info(f"Device {device_id} has been inactive for {time_since_inactive:.1f}s (>= 60s). Sending initial notification.")
                                send_email_alert(device_id, "Inactive", device.email)
                                self.inactive_devices[device_id]['last_notification'] = current_time
                            elif last_notification is None and time_since_inactive < self.inactivity_confirmation_wait:
                                logger.debug(f"Device {device_id} inactive for {time_since_inactive:.1f}s. Waiting for 60s confirmation ({self.inactivity_confirmation_wait - time_since_inactive:.1f}s remaining).")
                            
                            # Send periodic notifications every notification_interval seconds (after initial email sent)
                            elif last_notification is not None and \
                                 (current_time - last_notification).total_seconds() >= self.notification_interval:
                                logger.info(f"Device {device_id} still inactive. Sending periodic notification every {self.notification_interval}s.")
                                send_email_alert(device_id, "Inactive", device.email)
                                self.inactive_devices[device_id]['last_notification'] = current_time
                    else:
                        # Device is active again
                        if device_id in self.inactive_devices:
                            inactive_data = self.inactive_devices[device_id]
                            
                            # Check if we had sent a notification before device came back online
                            if inactive_data['last_notification'] is not None:
                                # Add hysteresis: track when device became active
                                if 'active_since' not in inactive_data:
                                    # First time seeing device active - start tracking
                                    inactive_data['active_since'] = current_time
                                    logger.info(f"Device {device_id} is active. Starting 30s stability check before sending recovery email.")
                                else:
                                    # Check if device has been stable for 30 seconds
                                    time_active = (current_time - inactive_data['active_since']).total_seconds()
                                    if time_active >= 30:
                                        logger.info(f"Device {device_id} stable for {time_active:.1f}s. Sending 'Active' email.")
                                        send_email_alert(device_id, "Active", device.email)
                                        del self.inactive_devices[device_id]
                                    else:
                                        logger.debug(f"Device {device_id} active for {time_active:.1f}s. Waiting for 30s stability.")
                            else:
                                # Device came back online before we ever sent an inactivity alert
                                logger.info(f"Device {device_id} came back online before 90s confirmation. No alert was sent.")
                                del self.inactive_devices[device_id]
        except Exception as e:
            logger.error(f"Error checking device inactivity: {str(e)}")
            import traceback
            traceback.print_exc()
    
    def run(self):
        """Main monitoring loop"""
        logger.info("🚀 Starting LoRa device monitor")
        logger.info(f"⚙️ Configuration: check_interval={self.check_interval}s, notification_interval={self.notification_interval}s, inactivity_threshold={self.inactivity_threshold}s")
        
        while True:
            try:
                # Check for device inactivity
                self.check_device_inactivity()
                
                # Cleanup old devices
                self.cleanup_old_offline_devices()
                self.cleanup_old_inactive_devices()
                
                # Sleep until next check
                time.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"Error in monitor loop: {str(e)}")
                import traceback
                traceback.print_exc()
                time.sleep(self.check_interval)  # Still sleep to avoid tight error loop

    def start(self):
        """Start the monitor in a background thread"""
        monitor_thread = threading.Thread(target=self.run, daemon=True)
        monitor_thread.start()
        logger.info("🧵 LoRa device monitor thread started")
        return monitor_thread

# Create a singleton instance
lora_monitor = LoraDeviceMonitor()
_monitor_thread = None

def start_monitor():
    """Start the LoRa device monitor in a separate thread"""
    global _monitor_thread
    if _monitor_thread is None or not _monitor_thread.is_alive():
        _monitor_thread = threading.Thread(target=lora_monitor.run, daemon=True)
        _monitor_thread.start()
        logger.info("Started LoRa device monitor thread")
        return True
    else:
        logger.info("LoRa device monitor thread already running")
        return False

def get_monitor_status():
    """Get the status of the LoRa device monitor"""
    return {
        'is_running': _monitor_thread is not None and _monitor_thread.is_alive(),
        'monitor_status': lora_monitor.get_status()
    }

def force_check_devices():
    """Force a check of all LoRa devices"""
    lora_monitor.force_check_all_lora_devices()
    return True

def get_offline_devices():
    """Get the list of offline devices"""
    return lora_monitor.offline_devices

def get_inactive_devices():
    """Get the list of inactive devices"""
    return lora_monitor.inactive_devices

def reset_tracking():
    """Reset the tracking of offline and inactive devices"""
    lora_monitor.offline_devices = {}
    lora_monitor.inactive_devices = {}
    logger.info("Reset tracking of offline and inactive devices")
    return True