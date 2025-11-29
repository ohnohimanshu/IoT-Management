from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden, JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.views.decorators.http import require_POST
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status
from django.core.exceptions import ValidationError
from django.db import transaction
from django.views.decorators.http import require_http_methods
from django.urls import reverse
from django.contrib import messages

from .models import Device, PinConfig, PinToggleLog, ScheduledCommand
from api.models import DeviceData
from .serializers import DeviceSerializer
from accounts.models import CustomUser
from mailer.models import EmailRecipient, Alert
from mailer.forms import EmailRecipientForm
from .forms import GlobalIntervalForm, DeviceForm
from .services import DeviceService

from api.serializers import DeviceDataSerializer

import logging
import ipaddress
from django.utils.html import strip_tags
import json
from datetime import timedelta
import re

logger = logging.getLogger(__name__)

# Dashboard Views


@login_required
def device_admin_dashboard(request):
    try:
        if request.user.role == 'admin':
            devices = Device.objects.all()
            users = CustomUser.objects.all()
            recipients = EmailRecipient.objects.all()
            template = 'admin_dashboard.html'
        elif request.user.role == 'device-administrator':
            devices = Device.objects.filter(added_by=request.user)
            users = CustomUser.objects.all()
            recipients = EmailRecipient.objects.filter(user=request.user)
            template = 'device_admin_dashboard.html'
        else:
            return HttpResponseForbidden("Access Denied")

        # Update device statuses with error handling
        for device in devices:
            try:
                device.update_status()
            except Exception as e:
                logger.error(f"Error updating status for device {device.device_id}: {str(e)}")
                continue

        from mailer.models import Alert, EmailLog

        # Get alerts related to devices added by device-admin with pagination
        alerts = Alert.objects.filter(device__in=devices).order_by('-timestamp')[:10]

        # Get email logs for those devices with pagination
        email_logs = EmailLog.objects.filter(
            device__in=devices,
            email_type='alert'
        ).order_by('-sent_at')[:10]

        # Combine all alerts with proper error handling
        all_alerts = []

        for alert in alerts:
            try:
                all_alerts.append({
                    'id': alert.id,  # FIXED: Changed from log.id to alert.id
                    'title': alert.title,
                    'message': alert.message,
                    'severity': alert.severity,
                    'timestamp': alert.timestamp,
                    'device_id': alert.device.device_id if alert.device else None,
                    'is_read': alert.is_read,
                    'type': 'alert'
                })
            except Exception as e:
                logger.error(f"Error processing alert {alert.id}: {str(e)}")
                continue

        for log in email_logs:
            try:
                all_alerts.append({
                    'id': log.id,  
                    'title': log.subject,
                    'message': f"Email sent to {log.recipient_email}",
                    'severity': 'high' if 'Alert' in log.subject else 'medium',
                    'timestamp': log.sent_at,
                    'device_id': log.device.device_id,
                    'is_read': True,
                    'type': 'email'
                })
            except Exception as e:
                logger.error(f"Error processing email log {log.id}: {str(e)}")
                continue

        all_alerts.sort(key=lambda x: x['timestamp'], reverse=True)
        unread_alerts_count = sum(1 for alert in all_alerts if not alert.get('is_read', True))

        # Get recent alerts (top 10 from combined list)
        recent_alerts = all_alerts[:10]
        alerts_count = len(all_alerts)

        # Get active and inactive device counts
        active_devices_count = devices.filter(device_status='online').count()
        inactive_devices_count = devices.filter(device_status='offline').count()

        # Get recent pin toggle logs with error handling
        try:
            recent_pin_logs = PinToggleLog.objects.filter(
                device__in=devices
            ).order_by('-timestamp')[:10]
        except Exception as e:
            logger.error(f"Error fetching pin toggle logs: {str(e)}")
            recent_pin_logs = []

        # Handle email recipient form with proper CSRF protection
        form = EmailRecipientForm(request.POST or None)
        if request.method == 'POST' and form.is_valid():
            try:
                email_recipient = form.save(commit=False)
                email_recipient.user = request.user
                email_recipient.save()
                messages.success(request, 'Email recipient added successfully.')
                return redirect('device_admin_dashboard')
            except Exception as e:
                logger.error(f"Error saving email recipient: {str(e)}")
                messages.error(request, 'Error adding email recipient.')

        # Handle global interval form
        global_interval_form = None
        if request.user.role == 'device-administrator':
            try:
                admin_devices = Device.objects.filter(added_by=request.user)
                initial_interval = admin_devices.first().email_interval if admin_devices.exists() else 5
                global_interval_form = GlobalIntervalForm(initial={'email_interval': initial_interval})
            except Exception as e:
                logger.error(f"Error setting up global interval form: {str(e)}")

        context = {
            'devices': devices,
            'users': users,
            'recipients': recipients,
            'form': form,
            'global_interval_form': global_interval_form,
            'recent_alerts': recent_alerts,
            'alerts_count': alerts_count,
            'unread_alerts': unread_alerts_count,
            'active_devices_count': active_devices_count,
            'inactive_devices_count': inactive_devices_count,
            'health_status': 'Healthy' if active_devices_count > 0 else 'Warning',
            'last_health_check': timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
            'recent_pin_logs': recent_pin_logs
        }
        
        # Debug output - Check your terminal for this
        print("="*60)
        print(f"TEMPLATE: {template}")
        print(f"USER ROLE: {request.user.role}")
        print(f"DEVICES COUNT: {devices.count()}")
        print(f"ACTIVE: {active_devices_count}, INACTIVE: {inactive_devices_count}")
        print(f"USERS COUNT: {users.count()}")
        print(f"ALERTS COUNT: {alerts_count}")
        print(f"HEALTH STATUS: {context['health_status']}")
        print("="*60)
        
        return render(request, template, context)

    except Exception as e:
        logger.error(f"Error in dashboard: {str(e)}")
        import traceback
        traceback.print_exc()  # This will show you the full error in terminal
        messages.error(request, 'An error occurred while loading the dashboard.')
        return JsonResponse({'error': str(e)}, status=500)


@login_required
def admin_dashboard(request):
    try:
        if request.user.role != 'admin':
            return HttpResponseForbidden("Access Denied")

        devices = Device.objects.all()
        users = CustomUser.objects.all()
        recipients = EmailRecipient.objects.all()

        # Update device statuses
        for device in devices:
            device.update_status()

        # Get recent alerts
        recent_alerts = Alert.objects.all().order_by('-timestamp')[:10]
        total_alerts = Alert.objects.count()

        # Get active and inactive device counts
        active_devices = devices.filter(device_status='online').count()
        inactive_devices = devices.filter(device_status='offline').count()

        # Get recent pin toggle logs
        recent_pin_logs = PinToggleLog.objects.filter(
            device__in=devices
        ).order_by('-timestamp')[:10]

        # Handle email recipient form
        form = EmailRecipientForm(request.POST or None)
        if request.method == 'POST' and form.is_valid():
            email_recipient = form.save(commit=False)
            email_recipient.user = request.user
            email_recipient.save()
            return redirect('admin_dashboard')

        context = {
            'devices': devices,
            'users': users,
            'recipients': recipients,
            'form': form,
            'recent_alerts': recent_alerts,
            'total_alerts': total_alerts,
            'active_devices_count': active_devices,
            'inactive_devices_count': inactive_devices,
            'health_status': 'Healthy' if active_devices > 0 else 'Warning',
            'last_health_check': timezone.now().strftime('%Y-%m-%d %H:%M:%S'),
            'recent_pin_logs': recent_pin_logs
        }
        return render(request, 'admin_dashboard.html', context)

    except Exception as e:
        logger.error(f"Error in admin dashboard: {str(e)}")
        return JsonResponse({'error': 'Internal server error'}, status=500)

# Device CRUD Operations
@csrf_exempt
@login_required
def add_device(request):
    if request.method == 'POST' and request.user.role in ['device-administrator', 'admin']:
        try:
            # Validate required fields
            required_fields = ['device_name', 'device_id', 'email', 'user', 'device_type']
            data = {field: request.POST.get(field, '').strip() for field in required_fields}
            
            if not all(data.values()):
                return JsonResponse({"error": "All fields are required"}, status=400)
            
            # Validate device_id format
            try:
                data['device_id'] = validate_device_id(data['device_id'])
            except ValidationError as e:
                return JsonResponse({"error": str(e)}, status=400)
            
            # Validate device_name is not empty
            if not data['device_name'].strip():
                return JsonResponse({"error": "Device name cannot be empty"}, status=400)
            
            if data['device_type'] not in ['esp', 'lora', 'esp8266', 'esp32', 'arduino', 'raspberry_pi']:
                return JsonResponse({"error": "Invalid device type"}, status=400)

            # Check if device_id already exists
            if Device.objects.filter(device_id=data['device_id']).exists():
                return JsonResponse({"error": "Device ID already exists"}, status=400)

            # Get user instance
            try:
                user = CustomUser.objects.get(id=data['user'])
            except CustomUser.DoesNotExist:
                return JsonResponse({"error": "Invalid user ID"}, status=400)

            # Create device with correct fields
            device = Device.objects.create(
                device_name=data['device_name'],
                device_id=data['device_id'],
                user=user,
                email=data['email'],
                added_by=request.user,
                device_type=data['device_type'],
                settings={}
            )

            serializer = DeviceSerializer(device)
            return JsonResponse({
                "success": "Device added successfully", 
                "device": serializer.data
            }, status=201)

        except Exception as e:
            logger.error(f"Error adding device: {str(e)}")
            return JsonResponse({"error": str(e)}, status=500)

    return JsonResponse({"error": "Invalid request"}, status=403)

@login_required
@require_POST
def delete_device(request, device_id):
    try:
        device = Device.objects.get(id=device_id)

        # Check user permission
        if request.user.role == 'admin' or (
            request.user.role == 'device-administrator' and device.user == request.user
        ):
            device.delete()
            return JsonResponse({'success': True, 'message': 'Device deleted successfully'})
        else:
            return JsonResponse({'success': False, 'error': 'You do not have permission to delete this device.'}, status=403)

    except Device.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Device not found.'}, status=404)

@login_required
def edit_device(request, device_id):
    device = get_object_or_404(Device, id=device_id)
    if request.method == "POST":
        form = DeviceForm(request.POST, instance=device)
        if form.is_valid():
            form.save()
            # Redirect to appropriate dashboard URL based on user role
            if request.user.role == 'admin':
                return redirect('admin_dashboard')
            elif request.user.role == 'device-administrator':
                return redirect('device_admin_dashboard')
            else:
                # Fallback or error handling for other roles
                return redirect('/') # Redirect to homepage or a suitable page
        else:
            # Form is not valid, re-render template with errors
            pass # Continue to render with existing form and errors
    else:
        form = DeviceForm(instance=device)
    return render(request, "edit_device.html", {"form": form, "device": device})

@login_required
def set_global_interval(request):
    if request.user.role not in ['device-administrator', 'admin']:
        return HttpResponseForbidden("Not allowed")
    
    devices = Device.objects.filter(added_by=request.user)
    initial_interval = devices.first().email_interval if devices.exists() else 5
    
    if request.method == 'POST':
        form = GlobalIntervalForm(request.POST)
        if form.is_valid():
            interval = form.cleaned_data['email_interval']
            devices.update(email_interval=interval)
            return redirect('device_admin_dashboard')
    else:
        form = GlobalIntervalForm(initial={'email_interval': initial_interval})
    
    return redirect('device_admin_dashboard')

def esp_devices_api(request):
    devices = Device.objects.filter(device_type='esp')
    data = [
        {
            "device_id": device.device_id,
            "device_name": device.device_name,
            "device_status": device.check_status()  # Add this line to include the status
        }
        for device in devices
    ]
    return JsonResponse(data, safe=False)

@csrf_exempt
def get_pin_states(request, device_id):
    device = get_object_or_404(Device, device_id=device_id)
    pins = device.pins.all().order_by('pin_number')
    data = {"pin_states": {}}
    for pin in pins:
        if pin.mode == 'on':
            data["pin_states"][str(pin.pin_number)] = "on"
        else:
            data["pin_states"][str(pin.pin_number)] = "off"
    
    return JsonResponse(data)

# Device Configuration Views
@login_required
def device_config(request, device_id):
    try:
        device = get_object_or_404(Device, device_id=device_id)
        
        # Get existing pins
        existing_pins = device.pins.all()
        
        # Only create pins if none exist
        if not existing_pins.exists():
            pins_to_create = []
            for i in range(32):
                pins_to_create.append(PinConfig(
                    device=device,
                    pin_number=i,
                    mode='input',
                    pin_name=f"Pin {i}"
                ))
                
            if pins_to_create:
                PinConfig.objects.bulk_create(pins_to_create)
                existing_pins = device.pins.all()

        # Get all pins ordered by pin number
        pins = existing_pins.order_by('pin_number')
        toggle_pins = pins.filter(mode='output')
        
        # Get latest logs
        logs = device.toggle_logs.order_by('-timestamp')[:50]

        if request.method == 'POST':
            return handle_post_request(request, device, pins, toggle_pins)

        return render(request, 'config.html', {
            'device': device,
            'pins': pins,
            'toggle_pins': toggle_pins,
            'logs': logs,
            'from': request.GET.get('from', '')  # Pass the from parameter to the template
        })

    except Exception as e:
        logger.error(f"Error in device_config: {str(e)}")
        return JsonResponse({'error': 'Internal server error'}, status=500)

def handle_post_request(request, device, pins, toggle_pins):
    try:
        action = request.POST.get('action')
        
        # Update pin configurations
        for pin in pins:
            new_mode = request.POST.get(f'pin_{pin.pin_number}_mode')
            new_name = request.POST.get(f'pin_{pin.pin_number}_name')
            
            if new_mode or new_name:
                if new_mode:
                    pin.mode = new_mode
                if new_name:
                    pin.pin_name = new_name
                pin.save()
        
        # Update network settings
        network_fields = ['ssid', 'password', 'static_ip']
        for field in network_fields:
            value = request.POST.get(field)
            if value:
                setattr(device, field, value)
        device.save()
        
        if action == 'download':
            return generate_device_code(device, toggle_pins, request)
            
        # Preserve the 'from' parameter when redirecting
        from_param = request.GET.get('from', '')
        redirect_url = f"{reverse('device_config', args=[device.device_id])}"
        if from_param:
            redirect_url += f"?from={from_param}"
        return redirect(redirect_url)
    except Exception as e:
        logger.error(f"Error in handle_post_request: {str(e)}")
        return JsonResponse({'error': 'Internal server error'}, status=500)


def validate_network_settings(request):
    """
    Validate and sanitize network configuration settings.
    
    Args:
        request (HttpRequest): Request containing network settings
        
    Returns:
        dict: Validated network settings
        
    Raises:
        ValidationError: If settings are invalid
    """
    ssid = strip_tags(request.POST.get('ssid', '').strip())
    password = request.POST.get('password', '').strip()
    static_ip = request.POST.get('static_ip', '').strip()

    # Validate SSID
    if not ssid:
        raise ValidationError("SSID is required")
    if len(ssid) > 32:
        raise ValidationError("SSID must be 32 characters or less")

    # Validate password
    if password and (len(password) < 8 or len(password) > 64):
        raise ValidationError("Password must be between 8 and 64 characters")

    # Validate static IP if provided
    if static_ip:
        try:
            ipaddress.ip_address(static_ip)
        except ValueError:
            raise ValidationError("Invalid static IP address format")

    return {
        'ssid': ssid,
        'password': password,
        'static_ip': static_ip
    }


@csrf_exempt
@require_http_methods(["POST"])
def toggle_pin(request, device_id, pin_number):
    try:
        # Log the incoming request for debugging
        logger.info(f"Toggle pin request - Device: {device_id}, Pin: {pin_number}")
        logger.info(f"Request body: {request.body}")
        logger.info(f"Request headers: {request.headers}")
        
        # Get the device
        try:
            device = get_object_or_404(Device, device_id=device_id)
            logger.info(f"Found device: {device.device_name}")
        except Exception as e:
            logger.error(f"Error finding device: {str(e)}")
            raise
        
        # Parse request data
        try:
            data = json.loads(request.body)
            logger.info(f"Parsed request data: {data}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON data in request body: {str(e)}")
            return JsonResponse({'error': 'Invalid JSON data'}, status=400)
        
        new_status = data.get('action', 'off')
        pin_name = data.get('pin_name', f'Pin {pin_number}')
        
        logger.info(f"New status: {new_status}, Pin name: {pin_name}")
        
        # Validate status
        if new_status not in ['on', 'off']:
            logger.error(f"Invalid action: {new_status}")
            return JsonResponse({'error': 'Invalid action. Must be "on" or "off"'}, status=400)
        
        # Use transaction to ensure data consistency
        try:
            with transaction.atomic():
                # Get or create pin config
                try:
                    pin, created = PinConfig.objects.get_or_create(
                        device=device,
                        pin_number=pin_number,
                        defaults={
                            'pin_name': pin_name,
                            'mode': new_status
                        }
                    )
                    logger.info(f"Pin config {'created' if created else 'updated'}: {pin.pin_number}")
                except Exception as e:
                    logger.error(f"Error with PinConfig: {str(e)}")
                    raise
                
                # Update pin mode if it exists
                if not created:
                    pin.mode = new_status
                    pin.pin_name = pin_name  # Update name in case it changed
                    pin.save()
                    logger.info(f"Updated pin mode to: {new_status}")
                
                # Create log entry
                try:
                    log = PinToggleLog.objects.create(
                        device=device,
                        pin_number=pin_number,
                        pin_name=pin_name,
                        status=new_status,
                        timestamp=timezone.now() + timedelta(hours=5, minutes=30)
                    )
                    logger.info(f"Created toggle log entry: {log.id}")
                except Exception as e:
                    logger.error(f"Error creating PinToggleLog: {str(e)}")
                    raise
                
                logger.info(f"Pin {pin_number} toggled to {new_status} for device {device_id}")
        except Exception as e:
            logger.error(f"Transaction error: {str(e)}")
            raise
        
        return JsonResponse({
            'success': True,
            'status': new_status,
            'pin_number': pin_number,
            'pin_name': pin_name,
            'timestamp': log.timestamp.strftime("%b %d, %H:%M"),
            'message': f'Pin {pin_number} set to {new_status}'
        })
        
    except Device.DoesNotExist:
        logger.error(f"Device {device_id} not found")
        return JsonResponse({'error': 'Device not found'}, status=404)
    except Exception as e:
        logger.error(f"Error in toggle_pin: {str(e)}", exc_info=True)
        return JsonResponse({'error': f'Server error: {str(e)}'}, status=500)
    
@login_required
def device_status(request, device_id):
    try:
        device = get_object_or_404(Device, device_id=device_id)
        DeviceService.save_device(device)
        DeviceService.reset_status_change_count(device)
        
        return JsonResponse({
            'status': device.device_status,
            'last_seen': device.last_seen.isoformat() if device.last_seen else None,
            'status_change_count': device.status_change_count
        })
    except Exception as e:
        logger.error(f"Error in device_status: {str(e)}")
        return JsonResponse({'error': 'Internal server error'}, status=500)



@login_required
def toggle_device_status(request, device_id):
    """API endpoint to toggle device status"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    
    try:
        device = Device.objects.get(device_id=device_id, user=request.user)
        device.device_status = 'offline' if device.device_status == 'online' else 'online'
        device.save()
        
        return JsonResponse({
            'success': True,
            'new_status': device.device_status
        })
    except Device.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Device not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def send_device_command(request, device_id):
    """API endpoint to send commands to devices, including broadcast."""
    try:
        command = request.data.get('command')
        if not command:
            return Response({'error': 'Command is required'}, status=status.HTTP_400_BAD_REQUEST)

        # Parse command if it's a JSON string
        try:
            if isinstance(command, str):
                command = json.loads(command)
        except json.JSONDecodeError:
            return Response({'error': 'Invalid command format'}, status=status.HTTP_400_BAD_REQUEST)

        if device_id == 'all':
            # Broadcast to all devices
            devices = Device.objects.all()
            results = []
            for device in devices:
                try:
                    # Create command log
                    command_log = {
                        'device_id': device.device_id,
                        'command': command,
                        'timestamp': timezone.now(),
                        'status': 'pending'
                    }

                    # Save command to device settings
                    if not device.settings:
                        device.settings = {}
                    if 'command_history' not in device.settings:
                        device.settings['command_history'] = []
                    device.settings['command_history'].append(command_log)
                    device.save()

                    # Send command to device via WebSocket
                    from channels.layers import get_channel_layer
                    from asgiref.sync import async_to_sync
                    
                    channel_layer = get_channel_layer()
                    async_to_sync(channel_layer.group_send)(
                        f"device_{device.device_id}",
                        {
                            "type": "device.command",
                            "command": command
                        }
                    )

                    command_log['status'] = 'success'
                    command_log['response'] = f'Command {command} sent successfully'
                    results.append(command_log)

                except Exception as e:
                    logger.error(f"Error sending command to device {device.device_id}: {str(e)}")
                    command_log['status'] = 'failed'
                    command_log['response'] = str(e)
                    results.append(command_log)

            return Response({
                'success': True,
                'message': 'Broadcast command sent to all devices',
                'results': results
            })
        else:
            # Send to specific device
            device = get_object_or_404(Device, device_id=device_id)
            
            # Create command log
            command_log = {
                'device_id': device.device_id,
                'command': command,
                'timestamp': timezone.now(),
                'status': 'pending'
            }

            # Save command to device settings
            if not device.settings:
                device.settings = {}
            if 'command_history' not in device.settings:
                device.settings['command_history'] = []
            device.settings['command_history'].append(command_log)
            device.save()

            try:
                # Send command to device via WebSocket
                from channels.layers import get_channel_layer
                from asgiref.sync import async_to_sync
                
                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    f"device_{device.device_id}",
                    {
                        "type": "device.command",
                        "command": command
                    }
                )

                command_log['status'] = 'success'
                command_log['response'] = f'Command {command} sent successfully'
                device.save()

                return Response({
                    'success': True,
                    'message': 'Command sent successfully',
                    'command_log': command_log
                })

            except Exception as e:
                logger.error(f"Error sending command to device {device.device_id}: {str(e)}")
                command_log['status'] = 'failed'
                command_log['response'] = str(e)
                device.save()
                return Response({
                    'success': False,
                    'error': str(e),
                    'command_log': command_log
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    except Exception as e:
        logger.error(f"Error sending command: {str(e)}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@login_required
def esp_devices_view(request):
    """View to list ESP devices for the user"""
    try:
        esp_devices = Device.objects.filter(
            user=request.user,
            device_type__in=['esp', 'esp8266', 'esp32']
        )

        return render(request, 'esp_devices.html', {
            'esp_devices': esp_devices
        })
    except Exception as e:
        logger.error(f"Error in esp_devices_view: {str(e)}")
        return render(request, 'esp_devices.html', {
            'error': 'An error occurred while processing your request'
        })

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def get_device_pins(request, device_id):
    """API endpoint to get pins for a device"""
    try:
        device = get_object_or_404(Device, device_id=device_id)
        pins = device.pins.all().order_by('pin_number')
        
        pin_data = [{
            'pin_number': pin.pin_number,
            'pin_name': pin.pin_name,
            'mode': pin.mode
        } for pin in pins]
        
        return Response({
            'success': True,
            'pins': pin_data
        })
        
    except Exception as e:
        logger.error(f"Error getting device pins: {str(e)}")
        return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

@login_required
@api_view(['GET'])
def get_device_statuses(request):
    try:
        if request.user.role == 'admin':
            devices = Device.objects.all()
        else:
            devices = Device.objects.filter(added_by=request.user)
        
        # Update device statuses
        for device in devices:
            device.update_status()
        
        # Serialize device data
        device_data = [{
            'device_id': device.device_id,
            'device_status': device.device_status,
            'last_seen': device.last_seen.isoformat() if device.last_seen else None
        } for device in devices]
        
        return JsonResponse({'devices': device_data})
    except Exception as e:
        logger.error(f"Error getting device statuses: {str(e)}")
        return JsonResponse({'error': 'Internal server error'}, status=500)

@login_required
@api_view(['GET'])
def get_unread_alerts_count(request):
    try:
        if request.user.role == 'admin':
            devices = Device.objects.all()
        else:
            devices = Device.objects.filter(added_by=request.user)
        
        
        # Get unread alerts count
        unread_count = Alert.objects.filter(
            device__in=devices,
            is_read=False
        ).count()
        
        return JsonResponse({'count': unread_count})
    except Exception as e:
        logger.error(f"Error getting unread alerts count: {str(e)}")
        return JsonResponse({'error': 'Internal server error'}, status=500)

def validate_device_id(device_id):
    """Validate device_id format"""
    if not device_id or not device_id.strip():
        raise ValidationError("Device ID cannot be empty")
    
    device_id = device_id.strip()
    
    # Only alphanumeric, hyphens, underscores allowed
    if not re.match(r'^[a-zA-Z0-9_-]+$', device_id):
        raise ValidationError("Device ID can only contain alphanumeric characters, hyphens, and underscores")
    
    if len(device_id) > 100:
        raise ValidationError("Device ID must be 100 characters or less")
    
    return device_id

