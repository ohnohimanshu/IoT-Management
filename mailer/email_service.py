import time
import traceback
import logging
from django.utils import timezone
from django.conf import settings
from django.core.mail import send_mail, EmailMessage
from devices.models import Device
from .utils import format_timestamp, validate_email_settings
from .chart_generator import generate_charts
from datetime import datetime, timedelta
from .models import EmailLog
from api.models import DeviceData
from devices.models import DeviceStatusHistory

logger = logging.getLogger(__name__)

# Constants
MAX_RETRIES = 3  # Maximum email sending attempts

def log_email_attempt(device, recipient_email, email_type, subject, status=True, error_message=None):
    """Helper function to log email attempts"""
    EmailLog.objects.create(
        device=device,
        recipient_email=recipient_email,
        email_type=email_type,
        subject=subject,
        status=status,
        error_message=error_message
    )

def send_email_alert(device_identifier, current_status, recipient_email):
    """
    Send data transmission status notification email to both owner and administrator
    Returns: Boolean indicating success or failure
    """
    print(f"🔔 SENDING DATA STATUS ALERT: {device_identifier} -> {current_status}")
    logger.info(f"🔔 SENDING DATA STATUS ALERT: {device_identifier} -> {current_status}")
    
    # Validate email settings with detailed logging
    if not validate_email_settings(settings):
        logger.error("❌ Email settings misconfigured - cannot send email")
        print("❌ Email settings misconfigured - cannot send email")
        return False

    try:
        # First try to get the device by its ID
        try:
            device = Device.objects.get(device_id=device_identifier)
            logger.info(f"Found device by ID: {device_identifier}")
        except Device.DoesNotExist:
            # If that fails, try to get it by name
            try:
                device = Device.objects.get(device_name=device_identifier)
                logger.info(f"Found device by name: {device_identifier}")
            except Device.DoesNotExist:
                logger.error(f"❌ Device {device_identifier} not found")
                print(f"❌ Device {device_identifier} not found")
                return False

        # Create appropriate email subject and content based on status
        if current_status == "Active":
            subject = f"✅ Update: {device.device_name} is Sending Data"
            message = f"Dear User,\n\n"
            message += f"Good news! Your device '{device.device_name}' has resumed sending data and is now functioning normally.\n"
            message += f"Device Details:\n"
            message += f"- Device Name: {device.device_name}\n"
            message += f"- Device ID: {device.device_id}\n"
            message += f"- Data Resumed: {format_timestamp(timezone.now())}\n"
            message += f"- Last Data Received: {format_timestamp(device.last_seen)}\n\n"
            message += f"The device is now transmitting data as expected. No further action is required.\n\n"
            message += f"Best regards,\nSystem Administrator"
        else:
            subject = f"⚠️ Alert: {device.device_name} Not Sending Data"
            message = f"Dear User,\n\n"
            message += f"This is an automated alert to inform you that your device '{device.device_name}' has stopped sending data.\n"
            message += f"Device Details:\n"
            message += f"- Device Name: {device.device_name}\n"
            message += f"- Device ID: {device.device_id}\n"
            message += f"- Last Data Received: {format_timestamp(device.last_seen)}\n"
            message += f"- Alert Time: {format_timestamp(timezone.now())}\n\n"
            message += f"Please check the following:\n"
            message += f"1. Device power supply and connections\n"
            message += f"2. Network connectivity\n"
            message += f"3. Device configuration\n\n"
            message += f"Best regards,\nSystem Administrator"

        # Prepare recipient list - include both owner and admin if available
        recipient_list = [device.email]
        if device.added_by and device.added_by.email and device.added_by.email != device.email:
            recipient_list.append(device.added_by.email)  # Administrator's email

        # Log email details for debugging
        logger.info(f"Preparing to send email with subject: '{subject}'")
        logger.info(f"Email will be sent from: {settings.DEFAULT_FROM_EMAIL}")
        logger.info(f"Email recipients: {recipient_list}")

        # Try to send the email with retries
        for attempt in range(MAX_RETRIES):
            try:
                # Log the exact parameters being used
                logger.info(f"Attempt {attempt + 1}: Sending email with parameters:")
                logger.info(f"  - Subject: {subject}")
                logger.info(f"  - From: {settings.DEFAULT_FROM_EMAIL}")
                logger.info(f"  - To: {recipient_list}")
                
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=recipient_list,
                    fail_silently=False,
                )
                
                # Log successful email sending for each recipient
                for recipient in recipient_list:
                    log_email_attempt(device, recipient, 'alert', subject)
                    logger.info(f"✅ Email sent to {recipient} for {device.device_name} -> {current_status}")
                
                print(f"✅ Email alert sent: {device.device_name} -> {current_status}")
                
                # Update the device's last_email_sent timestamp and status
                device.last_email_sent = timezone.now()
                device.device_status = current_status.lower()
                device.last_status = current_status
                device.save(update_fields=['last_email_sent', 'device_status', 'last_status'])
                
                return True
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"❌ Attempt {attempt + 1}: Email send failed - {error_msg}")
                print(f"❌ Attempt {attempt + 1}: Email send failed - {error_msg}")
                traceback.print_exc()
                
                # Log failed attempt for each recipient
                for recipient in recipient_list:
                    log_email_attempt(device, recipient, 'alert', subject, False, error_msg)
                
                time.sleep(min(2 ** attempt, 60))  # Exponential backoff
        
        # If we get here, all attempts failed
        logger.error(f"❌ All {MAX_RETRIES} email attempts failed for {device.device_name}")
        print(f"❌ All {MAX_RETRIES} email attempts failed for {device.device_name}")
        return False
        
    except Exception as e:
        logger.error(f"❌ Unexpected error in send_email_alert: {str(e)}")
        print(f"❌ Unexpected error in send_email_alert: {str(e)}")
        traceback.print_exc()
        return False

def send_temperature_email_alert(device_identifier, temperature, is_high_temp, recipient_email):
    """
    Send temperature alert email to device owner and administrator.
    Returns: Boolean indicating success or failure.
    """
    alert_type = "High Temperature Alert" if is_high_temp else "Temperature Normal Alert"
    print(f"🔔 SENDING TEMPERATURE ALERT: {device_identifier} -> {alert_type} ({temperature}°C)")
    logger.info(f"🔔 SENDING TEMPERATURE ALERT: {device_identifier} -> {alert_type} ({temperature}°C)")
    
    if not validate_email_settings(settings):
        logger.error("❌ Email settings misconfigured - cannot send temperature email")
        print("❌ Email settings misconfigured - cannot send temperature email")
        return False

    try:
        try:
            device = Device.objects.get(device_id=device_identifier)
            logger.info(f"Found device by ID: {device_identifier}")
        except Device.DoesNotExist:
            try:
                device = Device.objects.get(device_name=device_identifier)
                logger.info(f"Found device by name: {device_identifier}")
            except Device.DoesNotExist:
                logger.error(f"❌ Device {device_identifier} not found for temperature alert")
                print(f"❌ Device {device_identifier} not found for temperature alert")
                return False

        # Create email subject and content
        subject = f"{alert_type} - {device.device_name}"
        message = f"Device '{device.device_name}' has reported a {alert_type.lower()}:\n"
        message += f"Current Temperature: {temperature}°C\n"
        message += f"Alert Time: {format_timestamp(timezone.now())}\n"
        message += f"Last seen: {format_timestamp(device.last_seen)}"

        recipient_list = [device.email]
        if device.added_by and device.added_by.email and device.added_by.email != device.email:
            recipient_list.append(device.added_by.email)

        logger.info(f"Preparing to send temperature email with subject: '{subject}'")
        logger.info(f"Email will be sent from: {settings.DEFAULT_FROM_EMAIL}")
        logger.info(f"Email recipients: {recipient_list}")

        for attempt in range(MAX_RETRIES):
            try:
                logger.info(f"Attempt {attempt + 1}: Sending temperature email with parameters:")
                logger.info(f"  - Subject: {subject}")
                logger.info(f"  - From: {settings.DEFAULT_FROM_EMAIL}")
                logger.info(f"  - To: {recipient_list}")
                
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=recipient_list,
                    fail_silently=False,
                )
                
                for recipient in recipient_list:
                    log_email_attempt(device, recipient, 'temperature_alert', subject)
                    logger.info(f"✅ Temperature email sent to {recipient} for {device.device_name} -> {alert_type}")
                
                print(f"✅ Temperature email alert sent: {device.device_name} -> {alert_type}")
                
                # We don't update device status for temperature alerts here
                
                return True
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"❌ Attempt {attempt + 1}: Temperature email send failed - {error_msg}")
                print(f"❌ Attempt {attempt + 1}: Temperature email send failed - {error_msg}")
                traceback.print_exc()
                
                for recipient in recipient_list:
                    log_email_attempt(device, recipient, 'temperature_alert', subject, False, error_msg)
                
                time.sleep(min(2 ** attempt, 60))
        
        logger.error(f"❌ All {MAX_RETRIES} temperature email attempts failed for {device.device_name}")
        print(f"❌ All {MAX_RETRIES} temperature email attempts failed for {device.device_name}")
        return False
        
    except Exception as e:
        logger.error(f"❌ Unexpected error in send_temperature_email_alert: {str(e)}")
        print(f"❌ Unexpected error in send_temperature_email_alert: {str(e)}")
        traceback.print_exc()
        return False


def send_daily_summary_email(device_identifier):
    """
    Send daily summary email with charts and reports to device owner and administrator
    Returns: Boolean indicating success or failure
    """
    logger.info(f"📊 Preparing daily summary for device: {device_identifier}")
    
    if not validate_email_settings(settings):
        logger.error("❌ Email settings misconfigured - cannot send email")
        return False

    try:
        # Get device information
        try:
            device = Device.objects.get(device_id=device_identifier)
        except Device.DoesNotExist:
            try:
                device = Device.objects.get(device_name=device_identifier)
            except Device.DoesNotExist:
                logger.error(f"❌ Device {device_identifier} not found")
                return False

        # Get past 24 hours data
        end_time = timezone.now()
        start_time = end_time - timedelta(hours=24)
        
        # Get device data from DeviceData model
        past_24hrs_data = DeviceData.objects.filter(
            device=device,
            timestamp__gte=start_time,
            timestamp__lte=end_time
        ).order_by('timestamp')

        if not past_24hrs_data:
            logger.warning(f"No data available for device {device.device_name} in the past 24 hours")
            return False

        # Generate charts and get status report from the same data source
        # This ensures text report and graph use the same data (DeviceData table)
        metrics_chart, status_chart, status_report = generate_charts(device.device_name, past_24hrs_data)

        # Fallback to DeviceStatusHistory if chart generation didn't return status_report
        if not status_report:
            logger.warning("Chart generation didn't return status_report, using DeviceStatusHistory as fallback")
            status_report = DeviceStatusHistory.get_daily_summary(device, start_time, end_time)

        if not all([metrics_chart, status_chart]):
            logger.error("Failed to generate required charts for daily summary")
            return False

        # Prepare email content
        subject = f"Daily Summary Report - {device.device_name}"
        
        # Format timestamps for display
        start_time_str = start_time.strftime('%Y-%m-%d %H:%M')
        end_time_str = end_time.strftime('%Y-%m-%d %H:%M')
        
        # Discover all sensor data keys dynamically
        all_data_keys = set()
        for entry in past_24hrs_data:
            all_data_keys.update(entry.data.keys())
        
        # Exclude 'status' and other non-sensor keys from data keys
        excluded_keys = {'status', 'device_id', 'id', 'created_at', 'updated_at'}
        sensor_data_keys = [key for key in all_data_keys if key not in excluded_keys]
        
        # Calculate average values for all numeric sensor data keys
        average_metrics = {}
        for key in sensor_data_keys:
            values = []
            for entry in past_24hrs_data:
                value = entry.data.get(key)
                if value is not None:
                    try:
                        numeric_value = float(value)
                        values.append(numeric_value)
                    except (ValueError, TypeError):
                        logger.warning(f"Skipping non-numeric value for key '{key}' on device {device.device_name}: {value}")
                        continue

            # Calculate average only if there are numeric values
            if values:
                average_metrics[key] = sum(values) / len(values)

        # Format Key Metrics section
        metrics_section = "📊 KEY METRICS:\n" + "=" * 20 + "\n"
        if average_metrics:
            for key, avg_value in average_metrics.items():
                # Create readable name and determine units
                readable_name = key.replace('_', ' ').title()
                units = ""
                key_lower = key.lower()
                
                if 'temp' in key_lower:
                    units = "°C"
                elif 'humid' in key_lower:
                    units = "%"
                elif 'signal' in key_lower or 'rssi' in key_lower:
                    units = "dBm"
                elif 'voltage' in key_lower or 'volt' in key_lower:
                    units = "V"
                elif 'current' in key_lower:
                    units = "A"
                elif 'pressure' in key_lower:
                    units = "Pa"
                elif 'light' in key_lower or 'lux' in key_lower:
                    units = "lx"
                elif 'ph' in key_lower:
                    units = "pH"
                
                unit_text = f" {units}" if units else ""
                metrics_section += f"📈 Average {readable_name}: {avg_value:.2f}{unit_text}\n"
        else:
            metrics_section += "No metric data available.\n"

        # Format Status Summary section
        status_summary_section = "\n📊 STATUS SUMMARY:\n" + "=" * 20 + "\n"
        if status_report:
            total_changes = status_report.get('total_changes', 0)
            total_active_time = status_report.get('total_active_time', 0)
            total_inactive_time = status_report.get('total_inactive_time', 0)
            active_percentage = status_report.get('active_percentage', 0)
            
            status_summary_section += f"📊 Number of Status Changes: {total_changes}\n"
            status_summary_section += f"⏱️ Total Active Time: {total_active_time:.1f} minutes\n"
            status_summary_section += f"⏸️ Total Inactive Time: {total_inactive_time:.1f} minutes\n"
            status_summary_section += f"📈 Active Percentage: {active_percentage:.1f}%\n"
        else:
            status_summary_section += "No status data available.\n"
             
        # Format Detailed Status Changes section
        status_changes_section = "\n📌 DETAILED STATUS CHANGES:\n" + "=" * 30 + "\n"
        if status_report and status_report.get('detailed_periods'):
            # Helper function to capitalize status for display
            def format_status(status):
                status_str = str(status).lower()
                if status_str in ['active', 'online']:
                    return 'Active'
                elif status_str in ['inactive', 'offline']:
                    return 'Inactive'
                else:
                    return status_str.capitalize()
            
            # Filter to only show periods where there was an actual status change
            transitions = [
                period for period in status_report['detailed_periods']
                if period['from_status'].lower() != period['to_status'].lower()
            ]
            
            if transitions:
                # Sort transitions by start time
                transitions.sort(key=lambda x: x['start_time'])
                
                # Format transitions showing actual from → to changes
                for transition in transitions:
                    timestamp_str = transition['start_time'].strftime('%Y-%m-%d %H:%M')
                    from_status = format_status(transition['from_status'])
                    to_status = format_status(transition['to_status'])
                    
                    status_changes_section += f"{timestamp_str}: {from_status} → {to_status}\n"
                
                # Add period calculations
                status_changes_section += "\n📊 STATUS PERIODS:\n" + "-" * 20 + "\n"
                for period in status_report['detailed_periods']:
                    start_time = period['start_time'].strftime('%H:%M')
                    end_time = period['end_time'].strftime('%H:%M')
                    duration = period['duration']
                    status = format_status(period['to_status'])
                    
                    status_changes_section += f"{start_time} to {end_time}: {status} ({duration:.1f} minutes)\n"
            else:
                # No transitions, but show the single period
                status_changes_section += "No status changes recorded in the past 24 hours.\n"
                status_changes_section += "\n📊 STATUS PERIODS:\n" + "-" * 20 + "\n"
                for period in status_report['detailed_periods']:
                    start_time = period['start_time'].strftime('%H:%M')
                    end_time = period['end_time'].strftime('%H:%M')
                    duration = period['duration']
                    status = format_status(period['to_status'])
                    
                    status_changes_section += f"{start_time} to {end_time}: {status} ({duration:.1f} minutes)\n"
        else:
            status_changes_section += "No status change data available.\n"

        # Construct the full email message
        message = f"""
Summary Report for: {device.device_name}
{'=' * 50}

{metrics_section}
{status_summary_section}
{status_changes_section}

📱 DEVICE INFORMATION:
{'=' * 25}
Device ID: {device.device_id}
Device Type: {device.get_device_type_display() if hasattr(device, 'get_device_type_display') else device.device_type}
Owner: {device.email}
{f"Administrator: {device.added_by.email}" if device.added_by and device.added_by.email and device.added_by.email != device.email else ""}

📅 REPORT PERIOD:
{'=' * 20}
From: {start_time_str} UTC
To: {end_time_str} UTC

---
This report was generated automatically by the Device Monitoring System.
For technical support, please contact your system administrator.
"""

        # Prepare recipient list - include both owner and admin if available
        recipient_list = [device.email]  # Owner's email
        if device.added_by and device.added_by.email and device.added_by.email != device.email:
            recipient_list.append(device.added_by.email)  # Administrator's email

        # Create email message with attachments
        email = EmailMessage(
            subject=subject,
            body=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipient_list
        )

        # Attach charts with descriptive names
        email.attach(f'{device.device_name}_sensor_metrics.png', metrics_chart.getvalue(), 'image/png')
        email.attach(f'{device.device_name}_status_timeline.png', status_chart.getvalue(), 'image/png')

        # Send email with retries
        for attempt in range(MAX_RETRIES):
            try:
                email.send(fail_silently=False)
                
                # Log successful email sending for each recipient
                for recipient in recipient_list:
                    log_email_attempt(device, recipient, 'summary', subject)
                    logger.info(f"✅ Daily summary email sent to {recipient} for {device.device_name}")
                
                return True
            except Exception as e:
                error_msg = str(e)
                logger.error(f"❌ Attempt {attempt + 1}: Email send failed - {error_msg}")
                
                # Log failed attempt for each recipient
                for recipient in recipient_list:
                    log_email_attempt(device, recipient, 'summary', subject, False, error_msg)
                
                time.sleep(min(2 ** attempt, 60))

        logger.error(f"❌ All {MAX_RETRIES} email attempts failed for {device.device_name}")
        return False

    except Exception as e:
        logger.error(f"❌ Unexpected error in send_daily_summary_email: {str(e)}")
        traceback.print_exc()
        return False



def send_lora_power_status_email(device_identifier, power_status, recipient_email):
    """
    Send LoRa device power status notification email.
    For OFF status: Sends email every 5 minutes until status is ON
    For ON status: Sends single notification that power is restored
    """
    print(f"🔔 SENDING LORA POWER STATUS ALERT: {device_identifier} -> {power_status}")
    logger.info(f"🔔 SENDING LORA POWER STATUS ALERT: {device_identifier} -> {power_status}")
    
    if not validate_email_settings(settings):
        logger.error("❌ Email settings misconfigured - cannot send power status email")
        print("❌ Email settings misconfigured - cannot send power status email")
        return False

    try:
        try:
            device = Device.objects.get(device_id=device_identifier)
            logger.info(f"Found device by ID: {device_identifier}")
        except Device.DoesNotExist:
            try:
                device = Device.objects.get(device_name=device_identifier)
                logger.info(f"Found device by name: {device_identifier}")
            except Device.DoesNotExist:
                logger.error(f"❌ Device {device_identifier} not found for power status alert")
                print(f"❌ Device {device_identifier} not found for power status alert")
                return False

        # Check if this is a LoRa device
        if not device.device_type.lower() == 'lora':
            logger.info(f"Device {device_identifier} is not a LoRa device, skipping power status email")
            return True

        # Normalize power status
        power_status = power_status.upper()
        
        # Create email subject and content based on power status
        if power_status == 'OFF':
            subject = f"⚠️ Power Alert: {device.device_name} is Offline"
            message = f"Dear User,\n\n"
            message += f"This is an automated alert to inform you that your LoRa device '{device.device_name}' has lost power.\n"
            message += f"Device Details:\n"
            message += f"- Device Name: {device.device_name}\n"
            message += f"- Device ID: {device.device_id}\n"
            message += f"- Last Seen: {format_timestamp(device.last_seen)}\n"
            message += f"- Alert Time: {format_timestamp(timezone.now())}\n\n"
            message += f"Please check the device's power supply and connections. You will receive this alert every 5 minutes until power is restored.\n\n"
            message += f"Best regards,\nSystem Administrator"
        else:  # ON status
            subject = f"✅ Power Restored: {device.device_name} is Online"
            message = f"Dear User,\n\n"
            message += f"Good news! Your LoRa device '{device.device_name}' has regained power and is now operational.\n"
            message += f"Device Details:\n"
            message += f"- Device Name: {device.device_name}\n"
            message += f"- Device ID: {device.device_id}\n"
            message += f"- Power Restored: {format_timestamp(timezone.now())}\n\n"
            message += f"The device is now functioning normally. No further action is required.\n\n"
            message += f"Best regards,\nSystem Administrator"

        recipient_list = [device.email]
        if device.added_by and device.added_by.email and device.added_by.email != device.email:
            recipient_list.append(device.added_by.email)

        logger.info(f"Preparing to send power status email with subject: '{subject}'")
        logger.info(f"Email will be sent from: {settings.DEFAULT_FROM_EMAIL}")
        logger.info(f"Email recipients: {recipient_list}")

        for attempt in range(MAX_RETRIES):
            try:
                logger.info(f"Attempt {attempt + 1}: Sending power status email with parameters:")
                logger.info(f"  - Subject: {subject}")
                logger.info(f"  - From: {settings.DEFAULT_FROM_EMAIL}")
                logger.info(f"  - To: {recipient_list}")
                
                send_mail(
                    subject=subject,
                    message=message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=recipient_list,
                    fail_silently=False,
                )
                
                for recipient in recipient_list:
                    log_email_attempt(device, recipient, 'power_status_alert', subject)
                    logger.info(f"✅ Power status email sent to {recipient} for {device.device_name} -> {power_status}")
                
                print(f"✅ Power status email alert sent: {device.device_name} -> {power_status}")
                
                # **CRITICAL FIX: Only update last_email_sent, NOT last_status**
                # The monitor now handles status updates
                device.last_email_sent = timezone.now()
                device.save(update_fields=['last_email_sent'])
                
                logger.info(f"Updated device {device_identifier} last_email_sent timestamp")
                
                return True
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"❌ Attempt {attempt + 1}: Power status email send failed - {error_msg}")
                print(f"❌ Attempt {attempt + 1}: Power status email send failed - {error_msg}")
                traceback.print_exc()
                
                for recipient in recipient_list:
                    log_email_attempt(device, recipient, 'power_status_alert', subject, False, error_msg)
                
                time.sleep(min(2 ** attempt, 60))  # Exponential backoff
        
        logger.error(f"All {MAX_RETRIES} power status email attempts failed for {device.device_name}")
        print(f"All {MAX_RETRIES} power status email attempts failed for {device.device_name}")
        return False
        
    except Exception as e:
        logger.error(f"Unexpected error in send_lora_power_status_email: {str(e)}")
        print(f"Unexpected error in send_lora_power_status_email: {str(e)}")
        traceback.print_exc()
        return False