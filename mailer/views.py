import time
import traceback
import logging
import threading
import sys
from datetime import datetime, timedelta

from django.utils import timezone
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.template.loader import render_to_string
from django.core.exceptions import ValidationError
from django.db.models import Avg
from django.db import transaction
from django.db.utils import OperationalError
from django.views.decorators.csrf import csrf_exempt

from .models import EmailRecipient, Alert
from .forms import EmailRecipientForm
from .serializers import AlertSerializer
from api.models import DeviceData
from devices.models import Device, DeviceStatusHistory

# Import from modular components
from .utils import format_timestamp, validate_email_settings
from .email_service import send_email_alert
from .device_monitor import (
    monitor_device_status, verify_device_status, 
    update_device_status, process_device,
    INACTIVITY_THRESHOLD, EMAIL_RATE_LIMIT
)
from .chart_generator import generate_charts
from .temperature_monitor import monitor_temperature, stop_temperature_monitoring

logger = logging.getLogger(__name__)

# Global variables to track background tasks
_background_tasks = {
    'status_monitor': None,
    'summary_scheduler': None,
    'temperature_monitor': None
}

def stop_background_tasks():
    """Stop all background tasks"""
    global _background_tasks
    
    # Stop temperature monitoring
    if _background_tasks['temperature_monitor']:
        stop_temperature_monitoring()
        _background_tasks['temperature_monitor'] = None
    
    # Add other task stopping logic here if needed
    logger.info("All background tasks stopped")

# Function to schedule daily summary emails
def schedule_daily_summary():
    """
    Schedule and send daily summary emails to users
    """
    logger.info("🗓️ Starting daily summary scheduler")
    print("🗓️ Background Task Running: Daily Summary Scheduler")
    
    # Implementation of daily summary scheduler would go here
    # This is a placeholder for future implementation
    
    while True:
        # Sleep until next scheduled time (e.g., 8 AM daily)
        time.sleep(3600)  # Sleep for an hour between checks

def start_background_tasks():
    """Start all background tasks"""
    global _background_tasks
    
    # Start device status monitoring
    if not _background_tasks['status_monitor']:
        _background_tasks['status_monitor'] = threading.Thread(
            target=monitor_device_status,
            daemon=True,
            name='DeviceStatusMonitor'
        )
        _background_tasks['status_monitor'].start()
        logger.info("Device status monitoring started")
    
    # Start daily summary scheduler
    if not _background_tasks['summary_scheduler']:
        _background_tasks['summary_scheduler'] = threading.Thread(
            target=schedule_daily_summary,
            daemon=True,
            name='DailySummaryScheduler'
        )
        _background_tasks['summary_scheduler'].start()
        logger.info("Daily summary scheduler started")
    
    # Start temperature monitoring
    if not _background_tasks['temperature_monitor']:
        _background_tasks['temperature_monitor'] = threading.Thread(
            target=monitor_temperature,
            daemon=True,
            name='TemperatureMonitor'
        )
        _background_tasks['temperature_monitor'].start()
        logger.info("Temperature monitoring started")

@login_required
def send_device_status_email(request, device_id):
    try:
        # Get device by device_id field (string identifier), not by primary key
        device = get_object_or_404(Device, device_id=device_id)
        
        # Get all recipients for the current user or all if admin
        if request.user.role == 'admin':
            recipients = EmailRecipient.objects.values_list('email', flat=True)
        else:
            recipients = EmailRecipient.objects.filter(user=request.user).values_list('email', flat=True)
        
        if not recipients:
            # If no recipients found, use device's email as fallback
            recipients = [device.email]
        
        # Determine current status based on last_seen timestamp
        current_time = timezone.now()
        if not device.last_seen:
            current_status = "Inactive"
        else:
            time_diff = (current_time - device.last_seen).total_seconds()
            current_status = "Active" if time_diff < INACTIVITY_THRESHOLD else "Inactive"
        
        # Update device status if needed
        if device.last_status != current_status:
            previous_status = device.last_status
            device.last_status = current_status
            device.status_last_changed = current_time
            device.status_change_count += 1
            device.save(update_fields=[
                'last_status',
                'status_last_changed',
                'status_change_count'
            ])
            
            # Record history
            DeviceStatusHistory.objects.create(
                device=device,
                previous_status=previous_status or "Unknown",
                new_status=current_status,
                changed_at=current_time
            )
            
            # Create an alert for the status change
            severity = 'high' if current_status == 'Inactive' else 'medium'
            create_device_alert(
                device=device,
                user=device.user,
                title=f"Device {device.device_name} is now {current_status}",
                message=f"Device status changed from {previous_status or 'Unknown'} to {current_status} at {format_timestamp(current_time)}",
                severity=severity
            )
        
        # Check if email should be sent based on rate limiting
        can_send_email = True
        if device.last_email_sent:
            time_since_last = (current_time - device.last_email_sent).total_seconds()
            can_send_email = time_since_last >= EMAIL_RATE_LIMIT
            
        if not can_send_email:
            logger.info(f"⏳ Email rate limit in effect for {device.device_name}. Last email sent at {format_timestamp(device.last_email_sent)}")
            # Redirect based on user role without sending email
            if request.user.role == 'admin':
                return redirect('admin_dashboard')
            return redirect('device_admin_dashboard')
            
        # Send email to each recipient
        success_count = 0
        for recipient in recipients:
            # Pass device_id instead of device_name for more reliable device lookup
            success = send_email_alert(device.device_id, current_status, recipient)
            if success:
                success_count += 1
                logger.info(f"Email alert sent to {recipient} for device {device.device_name}")
            else:
                logger.warning(f"Failed to send email alert to {recipient} for device {device.device_name}")
                
            # Add a small delay between emails to prevent overwhelming the mail server
            if len(recipients) > 1:
                time.sleep(1)
        
        # Update last_email_sent timestamp if at least one email was sent successfully
        if success_count > 0:
            device.last_email_sent = current_time
            device.save(update_fields=['last_email_sent'])
    
    except Exception as e:
        logger.error(f"❌ Error sending device status email: {e}")
        traceback.print_exc()
    
    # Redirect based on user role
    if request.user.role == 'admin':
        return redirect('admin_dashboard')
    return redirect('device_admin_dashboard')

@login_required
def email_recipient_list(request):
    if request.user.role not in ['admin', 'device-administrator']:
        return JsonResponse({"error": "Access Denied"}, status=403)

    recipients = EmailRecipient.objects.all() if request.user.role == 'admin' else EmailRecipient.objects.filter(user=request.user)
    devices = Device.objects.all() if request.user.role == 'admin' else Device.objects.filter(user=request.user)

    form = EmailRecipientForm(request.POST or None)

    if request.method == 'POST' and form.is_valid():
        email_recipient = form.save(commit=False)
        email_recipient.user = request.user
        email_recipient.save()

        # Redirect to the correct dashboard based on role
        if request.user.role == 'admin':
            return redirect('admin_dashboard')
        return redirect('device_admin_dashboard')

    return render(request, 'recipient_list.html', {'form': form, 'recipients': recipients, 'devices': devices})

@login_required
def delete_email_recipient(request, recipient_id):
    recipient = get_object_or_404(EmailRecipient, id=recipient_id)

    # Ensure only the owner or an admin can delete
    if request.user.role != 'admin' and recipient.user != request.user:
        return JsonResponse({"error": "Access Denied"}, status=403)

    recipient.delete()

    # Redirect based on role
    if request.user.role == 'admin':
        return redirect('admin_dashboard')
    return redirect('device_admin_dashboard')

@login_required
def device_charts(request, device_id):
    """
    View to display device charts and metrics
    """
    try:
        device = get_object_or_404(Device, device_id=device_id)
        
        # Get data for the past 24 hours
        past_24hrs = timezone.now() - timedelta(hours=24)
        device_data = DeviceData.objects.filter(
            device=device,
            timestamp__gte=past_24hrs
        ).order_by('timestamp')
        
        # Generate charts
        metrics_buffer, status_buffer, status_report = generate_charts(device.device_name, device_data)
        
        if not metrics_buffer or not status_buffer:
            return JsonResponse({"error": "Failed to generate charts"}, status=500)
        
        # Convert buffers to base64 for embedding in HTML
        import base64
        metrics_base64 = base64.b64encode(metrics_buffer.getvalue()).decode('utf-8')
        status_base64 = base64.b64encode(status_buffer.getvalue()).decode('utf-8')
        
        context = {
            'device': device,
            'metrics_chart': f"data:image/png;base64,{metrics_base64}",
            'status_chart': f"data:image/png;base64,{status_base64}",
            'status_report': status_report
        }
        
        return render(request, 'device_charts.html', context)
        
    except Exception as e:
        logger.error(f"Error generating device charts: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)

@login_required
def daily_summary(request, device_id):
    """
    View to display daily summary charts
    """
    try:
        device = get_object_or_404(Device, device_id=device_id)
        
        # Get data for the current day
        today = timezone.now().date()
        device_data = DeviceData.objects.filter(
            device=device,
            timestamp__date=today
        ).order_by('timestamp')
        
        # Generate summary chart
        summary_buffer = generate_daily_summary_chart(device.device_name, device_data)
        
        if not summary_buffer:
            return JsonResponse({"error": "Failed to generate summary chart"}, status=500)
        
        # Convert buffer to base64 for embedding in HTML
        import base64
        summary_base64 = base64.b64encode(summary_buffer.getvalue()).decode('utf-8')
        
        context = {
            'device': device,
            'summary_chart': f"data:image/png;base64,{summary_base64}"
        }
        
        return render(request, 'daily_summary.html', context)
        
    except Exception as e:
        logger.error(f"Error generating daily summary: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)

# Alert-related functions
def create_device_alert(device, user, title, message, severity='medium'):
    """
    Create a new alert for a device and user
    """
    try:
        alert = Alert.objects.create(
            title=title,
            message=message,
            severity=severity,
            device=device,
            user=user
        )
        logger.info(f"Created {severity} alert for {device.device_name}: {title}")
        return alert
    except Exception as e:
        logger.error(f"Error creating alert: {str(e)}")
        return None

@login_required
def get_user_alerts(request):
    """
    Get all alerts for the current user
    """
    try:
        # Get alerts for the user's devices
        alerts = Alert.objects.filter(user=request.user).order_by('-timestamp')
        serializer = AlertSerializer(alerts, many=True)
        return JsonResponse(serializer.data, safe=False)
    except Exception as e:
        logger.error(f"Error getting user alerts: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)


def get_unread_alerts_count(request):
    """Get count of unread alerts for the current user"""
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Authentication required'}, status=401)
    
    # Get all alerts for the user and count unread ones manually
    alerts = Alert.objects.filter(user=request.user)
    unread_count = 0
    for alert in alerts:
        if not alert.is_read:
            unread_count += 1
    
    return JsonResponse({'count': unread_count})

@login_required
def mark_alert_read(request, alert_id):
    """
    Mark an alert as read
    """
    try:
        alert = get_object_or_404(Alert, id=alert_id)
        
        # Ensure the alert belongs to the current user
        if alert.user != request.user and request.user.role != 'admin':
            return JsonResponse({"error": "Access Denied"}, status=403)
        
        alert.is_read = True
        alert.save()
        
        return JsonResponse({"success": True})
    except Exception as e:
        logger.error(f"Error marking alert as read: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)

@login_required
def mark_all_alerts_read(request):
    """
    Mark all alerts for the current user as read
    """
    try:
        # Get all alerts for the user and update them one by one
        alerts = Alert.objects.filter(user=request.user)
        for alert in alerts:
            if not alert.is_read:
                alert.is_read = True
                alert.save()
        
        return JsonResponse({"success": True})
    except Exception as e:
        logger.error(f"Error marking all alerts as read: {str(e)}")
        return JsonResponse({"error": str(e)}, status=500)

@login_required
@csrf_exempt
def send_device_status_email_to_recipient(request):
    if request.method == 'POST':
        device_id = request.POST.get('device_id')
        recipient_email = request.POST.get('recipient_email')
        if not device_id or not recipient_email:
            return JsonResponse({'success': False, 'error': 'Missing device or recipient.'})
        try:
            device = Device.objects.get(device_id=device_id)
        except Device.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Device not found.'})
        # Determine status as in your existing view
        current_time = timezone.now()
        if not device.last_seen:
            current_status = "Inactive"
        else:
            time_diff = (current_time - device.last_seen).total_seconds()
            current_status = "Active" if time_diff < INACTIVITY_THRESHOLD else "Inactive"
        # Send email
        from .email_service import send_email_alert
        success = send_email_alert(device.device_id, current_status, recipient_email)
        if success:
            return JsonResponse({'success': True})
        else:
            return JsonResponse({'success': False, 'error': 'Failed to send email.'})
    return JsonResponse({'success': False, 'error': 'Invalid request.'})