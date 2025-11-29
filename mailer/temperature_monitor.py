import logging
import time
from django.utils import timezone
from devices.models import Device
from .email_service import send_temperature_email_alert
from .models import Alert

logger = logging.getLogger(__name__)

# Global flag to control the monitoring thread
_monitoring_active = True

# Dictionary to track devices that are currently in high temperature state
_high_temp_devices = {}

def stop_temperature_monitoring():
    """Stop the temperature monitoring thread"""
    global _monitoring_active
    _monitoring_active = False

def send_temperature_alert(device, temperature, is_high_temp):
    """
    Send temperature alert email and create alert in database
    Args:
        device: Device object
        temperature: Current temperature
        is_high_temp: Boolean indicating if this is a high temperature alert
    Returns:
        bool: True if alert was sent successfully
    """
    try:
        # Create appropriate alert message
        if is_high_temp:
            alert_message = f"Device temperature ({temperature}°C) exceeds threshold (25°C)"
            current_status = f"Temperature Alert: {temperature}°C"
        else:
            alert_message = f"Device temperature ({temperature}°C) is now below threshold (25°C)"
            current_status = f"Temperature Normal: {temperature}°C"

        # Create alert in database
        Alert.objects.create(
            title="High Temperature Alert" if is_high_temp else "Temperature Normal Alert",
            message=alert_message,
            severity='high' if is_high_temp else 'low',
            device=device,
            user=device.added_by or device.user
        )

        # Send email alert
        success = send_temperature_email_alert(
            device_identifier=device.device_id,
            temperature=temperature,
            is_high_temp=is_high_temp,
            recipient_email=device.email
        )

        if success:
            logger.info(f"Temperature alert sent for device {device.device_name}: {alert_message}")
            return True
        else:
            logger.error(f"Failed to send temperature alert for device {device.device_name}")
            return False

    except Exception as e:
        logger.error(f"Error sending temperature alert: {str(e)}")
        return False

def check_device_temperature(device_data):
    """
    Check if device temperature exceeds threshold and send alerts if necessary
    Args:
        device_data: Dictionary containing device data including temperature
    Returns:
        bool: True if alert was sent, False otherwise
    """
    try:
        # Extract temperature from device data
        temperature = device_data.get('temperature')
        if temperature is None:
            logger.warning(f"No temperature data found in device data: {device_data}")
            return False

        # Convert temperature to float if it's a string
        if isinstance(temperature, str):
            try:
                temperature = float(temperature)
            except ValueError:
                logger.error(f"Invalid temperature value: {temperature}")
                return False

        device_id = device_data.get('device_id')
        if not device_id:
            logger.error("Device ID not found in device data")
            return False

        try:
            device = Device.objects.get(device_id=device_id)
            
            # Determine the high temperature threshold to use
            high_temp_threshold = device.high_temp_threshold if device.high_temp_threshold is not None else 25.0
            
            # Check if temperature exceeds threshold
            if temperature > high_temp_threshold:
                # If device wasn't previously in high temp state, send initial alert
                if device_id not in _high_temp_devices:
                    _high_temp_devices[device_id] = timezone.now()
                    return send_temperature_alert(device, temperature, True)
                # If device was in high temp state, check if 5 minutes have passed
                elif (timezone.now() - _high_temp_devices[device_id]).total_seconds() >= 300:
                    _high_temp_devices[device_id] = timezone.now()
                    return send_temperature_alert(device, temperature, True)
            else:
                # If temperature is now below threshold and device was previously in high temp state
                if device_id in _high_temp_devices:
                    del _high_temp_devices[device_id]
                    return send_temperature_alert(device, temperature, False)

            return False

        except Device.DoesNotExist:
            logger.error(f"Device not found with ID: {device_id}")
            return False
        except Exception as e:
            logger.error(f"Error processing temperature alert: {str(e)}")
            return False

    except Exception as e:
        logger.error(f"Unexpected error in check_device_temperature: {str(e)}")
        return False

def process_device_temperature(device_data_list):
    """
    Process temperature data for multiple devices
    Args:
        device_data_list: List of dictionaries containing device data
    Returns:
        dict: Summary of processed alerts
    """
    results = {
        'total_devices': len(device_data_list),
        'alerts_sent': 0,
        'errors': 0
    }

    for device_data in device_data_list:
        try:
            if check_device_temperature(device_data):
                results['alerts_sent'] += 1
        except Exception as e:
            logger.error(f"Error processing device data: {str(e)}")
            results['errors'] += 1

    return results

def monitor_temperature():
    """
    Background function to continuously monitor device temperatures
    This function runs in a separate thread and checks device temperatures periodically
    """
    global _monitoring_active
    
    logger.info("Starting temperature monitoring thread")
    
    while _monitoring_active:
        try:
            # Get all active devices
            devices = Device.objects.filter(device_status='active')
            
            for device in devices:
                try:
                    # Get the latest device data
                    latest_data = device.get_latest_data()
                    if latest_data:
                        # Process the temperature data
                        check_device_temperature(latest_data)
                except Exception as e:
                    logger.error(f"Error processing device {device.device_name}: {str(e)}")
                    continue
            
            # Sleep for 5 minutes before next check
            time.sleep(300)
            
        except Exception as e:
            logger.error(f"Error in temperature monitoring thread: {str(e)}")
            time.sleep(60)  # Sleep for 1 minute on error before retrying
    
    logger.info("Temperature monitoring thread stopped") 