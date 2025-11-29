import requests
import logging
import time
from django.conf import settings
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import OTAUpdate, DeviceFirmwareInfo

logger = logging.getLogger(__name__)


class OTAUpdateService:
    """Service class to handle OTA update operations"""

    def __init__(self):
        self.channel_layer = get_channel_layer()

    def start_ota_update(self, ota_update):
        """
        Start OTA update process for a device
        
        Args:
            ota_update: OTAUpdate instance
            
        Returns:
            bool: True if update started successfully, False otherwise
        """
        try:
            device = ota_update.device
            firmware = ota_update.firmware_version

            # Check if device is online
            if device.device_status != 'online':
                ota_update.mark_failed("Device is not online")
                return False

            # Mark update as started
            ota_update.mark_started()

            # Build firmware download URL
            firmware_url = self._build_firmware_url(firmware.id)
            
            # Prepare OTA command
            ota_command = {
                'type': 'ota_update',
                'firmware_url': firmware_url,
                'firmware_version': firmware.version_number,
                'firmware_size': firmware.file_size,
                'checksum': firmware.checksum,
                'update_id': ota_update.id,
                'callback_url': self._build_callback_url(ota_update.id)
            }

            # Send OTA command to device
            success = self._send_ota_command(device, ota_command)
            
            if success:
                ota_update.add_log_entry(f"OTA command sent to device {device.device_name}")
                
                # Send real-time update to dashboard
                self._send_dashboard_update(ota_update)
                
                return True
            else:
                ota_update.mark_failed("Failed to send OTA command to device")
                return False

        except Exception as e:
            logger.error(f"Error starting OTA update: {str(e)}")
            ota_update.mark_failed(f"Internal error: {str(e)}")
            return False

    def cancel_ota_update(self, ota_update):
        """
        Cancel an ongoing OTA update
        
        Args:
            ota_update: OTAUpdate instance
            
        Returns:
            bool: True if cancelled successfully, False otherwise
        """
        try:
            device = ota_update.device

            # Send cancel command to device
            cancel_command = {
                'type': 'ota_cancel',
                'update_id': ota_update.id
            }

            success = self._send_ota_command(device, cancel_command)
            
            if success:
                ota_update.status = 'cancelled'
                ota_update.completed_at = timezone.now()
                ota_update.add_log_entry("OTA update cancelled by user")
                ota_update.save(update_fields=['status', 'completed_at'])
                
                # Send real-time update to dashboard
                self._send_dashboard_update(ota_update)
                
                return True
            else:
                logger.error(f"Failed to send cancel command to device {device.device_name}")
                return False

        except Exception as e:
            logger.error(f"Error cancelling OTA update: {str(e)}")
            return False

    def _send_ota_command(self, device, command):
        """
        Send OTA command to device via HTTP or WebSocket
        
        Args:
            device: Device instance
            command: Command dictionary
            
        Returns:
            bool: True if command sent successfully, False otherwise
        """
        try:
            # Method 1: Try HTTP if device has static IP
            if device.static_ip:
                success = self._send_http_command(device, command)
                if success:
                    return True

            # Method 2: Try WebSocket
            success = self._send_websocket_command(device, command)
            if success:
                return True

            # Method 3: Try MQTT (if configured)
            success = self._send_mqtt_command(device, command)
            return success

        except Exception as e:
            logger.error(f"Error sending OTA command: {str(e)}")
            return False

    def _send_http_command(self, device, command):
        """Send command via HTTP to device"""
        try:
            if not device.static_ip:
                return False

            url = f"http://{device.static_ip}/ota"
            response = requests.post(
                url,
                json=command,
                timeout=10,
                headers={'Content-Type': 'application/json'}
            )

            if response.status_code == 200:
                logger.info(f"HTTP OTA command sent successfully to {device.device_name}")
                return True
            else:
                logger.warning(f"HTTP OTA command failed for {device.device_name}: {response.status_code}")
                return False

        except requests.exceptions.RequestException as e:
            logger.warning(f"HTTP request failed for {device.device_name}: {str(e)}")
            return False

    def _send_websocket_command(self, device, command):
        """Send command via WebSocket"""
        try:
            if not self.channel_layer:
                return False

            # Send to device-specific channel
            async_to_sync(self.channel_layer.group_send)(
                f"device_{device.device_id}",
                {
                    "type": "ota_command",
                    "command": command
                }
            )

            logger.info(f"WebSocket OTA command sent to {device.device_name}")
            return True

        except Exception as e:
            logger.warning(f"WebSocket command failed for {device.device_name}: {str(e)}")
            return False

    def _send_mqtt_command(self, device, command):
        """Send command via MQTT"""
        try:
            # Import here to avoid circular imports
            import paho.mqtt.client as mqtt
            import json

            # Get MQTT settings
            mqtt_settings = getattr(settings, 'MQTT', {})
            if not mqtt_settings:
                return False

            client = mqtt.Client()
            
            # Set credentials if provided
            username = mqtt_settings.get('USERNAME')
            password = mqtt_settings.get('PASSWORD')
            if username:
                client.username_pw_set(username, password)

            # Connect and publish
            host = mqtt_settings.get('HOST', 'localhost')
            port = mqtt_settings.get('PORT', 1883)
            
            client.connect(host, port, 60)
            
            topic = f"devices/{device.device_id}/ota"
            payload = json.dumps(command)
            
            result = client.publish(topic, payload, qos=1)
            client.disconnect()

            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info(f"MQTT OTA command sent to {device.device_name}")
                return True
            else:
                logger.warning(f"MQTT publish failed for {device.device_name}")
                return False

        except Exception as e:
            logger.warning(f"MQTT command failed for {device.device_name}: {str(e)}")
            return False

    def _build_firmware_url(self, firmware_id):
        """Build firmware download URL"""
        base_url = getattr(settings, 'BASE_URL', 'http://localhost:8000')
        return f"{base_url}/ota/firmware/{firmware_id}/download/"

    def _build_callback_url(self, update_id):
        """Build OTA progress callback URL"""
        base_url = getattr(settings, 'BASE_URL', 'http://localhost:8000')
        return f"{base_url}/ota/progress/{update_id}/"

    def _send_dashboard_update(self, ota_update):
        """Send real-time update to dashboard via WebSocket"""
        try:
            if not self.channel_layer:
                return

            from .serializers import OTAUpdateSerializer
            serializer = OTAUpdateSerializer(ota_update)

            async_to_sync(self.channel_layer.group_send)(
                "ota_dashboard",
                {
                    "type": "ota_update",
                    "data": serializer.data
                }
            )

        except Exception as e:
            logger.error(f"Error sending dashboard update: {str(e)}")

    def check_all_devices_for_updates(self):
        """Check all devices for available firmware updates"""
        try:
            from devices.models import Device
            
            esp_devices = Device.objects.filter(device_type__in=['esp', 'esp32', 'esp8266'])
            
            updates_found = 0
            for device in esp_devices:
                firmware_info, created = DeviceFirmwareInfo.objects.get_or_create(device=device)
                if firmware_info.check_for_updates():
                    updates_found += 1

            logger.info(f"Found {updates_found} devices with available updates")
            return updates_found

        except Exception as e:
            logger.error(f"Error checking for updates: {str(e)}")
            return 0

    def auto_update_devices(self):
        """Automatically update devices that have auto-update enabled"""
        try:
            devices_with_auto_update = DeviceFirmwareInfo.objects.filter(
                auto_update_enabled=True,
                update_available=True
            )

            updated_count = 0
            for firmware_info in devices_with_auto_update:
                device = firmware_info.device
                
                # Check if device is online
                if device.device_status != 'online':
                    continue

                # Check if there's already an active update
                active_update = OTAUpdate.objects.filter(
                    device=device,
                    status__in=['pending', 'in_progress']
                ).exists()

                if active_update:
                    continue

                # Create auto-update
                ota_update = OTAUpdate.objects.create(
                    device=device,
                    firmware_version=firmware_info.available_version,
                    initiated_by=device.added_by,  # Use device admin as initiator
                    previous_version=firmware_info.current_version
                )

                if self.start_ota_update(ota_update):
                    updated_count += 1
                    logger.info(f"Auto-update started for {device.device_name}")

            logger.info(f"Started auto-updates for {updated_count} devices")
            return updated_count

        except Exception as e:
            logger.error(f"Error in auto-update: {str(e)}")
            return 0