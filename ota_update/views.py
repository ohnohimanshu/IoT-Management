import os
import hashlib
import requests
import logging
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponse, Http404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.core.files.storage import default_storage
from django.conf import settings
from django.utils import timezone
from django.db import transaction
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

from devices.models import Device
from .models import FirmwareVersion, OTAUpdate, DeviceFirmwareInfo
from .forms import FirmwareUploadForm
from .services import OTAUpdateService
from .serializers import OTAUpdateSerializer, FirmwareVersionSerializer

logger = logging.getLogger(__name__)


@login_required
def ota_dashboard(request):
    """Main OTA dashboard view"""
    if request.user.role not in ['admin', 'device-administrator']:
        messages.error(request, 'Access denied. Admin privileges required.')
        return redirect('user_dashboard')

    # Get ESP devices based on user role
    if request.user.role == 'admin':
        esp_devices = Device.objects.filter(device_type__in=['esp', 'esp32', 'esp8266'])
    else:
        esp_devices = Device.objects.filter(
            device_type__in=['esp', 'esp32', 'esp8266'],
            added_by=request.user
        )

    # Initialize default values
    firmware_versions = []
    recent_updates = []
    devices_with_firmware = []
    active_updates_count = 0
    upload_form = None
    migration_needed = False

    # Check if OTA tables exist by trying to import and query them
    try:
        # Try to get firmware versions
        firmware_versions = list(FirmwareVersion.objects.filter(is_active=True).order_by('-created_at'))
    except Exception as e:
        logger.warning(f"OTA tables not available: {str(e)}")
        migration_needed = True

    if not migration_needed:
        try:
            # Get all OTA updates for these devices (before slicing)
            all_updates = OTAUpdate.objects.filter(
                device__in=esp_devices
            ).order_by('-initiated_at')
            
            # Get recent OTA updates (sliced)
            recent_updates = list(all_updates[:10])
            
            # Get active updates count (from unsliced queryset)
            active_updates_count = all_updates.filter(status='in_progress').count()
        except Exception as e:
            logger.warning(f"Error fetching OTA updates: {str(e)}")

        # Get devices with firmware info
        for device in esp_devices:
            try:
                firmware_info, created = DeviceFirmwareInfo.objects.get_or_create(device=device)
                if created:
                    firmware_info.check_for_updates()
                
                devices_with_firmware.append({
                    'device': device,
                    'firmware_info': firmware_info,
                    'latest_update': device.ota_updates.order_by('-initiated_at').first()
                })
            except Exception as e:
                logger.warning(f"Error processing device {device.device_name}: {str(e)}")
                # Add device without firmware info if there's an error
                devices_with_firmware.append({
                    'device': device,
                    'firmware_info': None,
                    'latest_update': None
                })
                continue

        # Handle firmware upload and device selection
        try:
            upload_form = FirmwareUploadForm()
            if request.method == 'POST' and 'upload_firmware' in request.POST:
                # Get selected devices
                target_devices = request.POST.getlist('target_devices')
                if not target_devices:
                    messages.error(request, 'Please select at least one device for the update.')
                    return redirect('ota_dashboard')
                
                # Handle form data (with or without Django form)
                if hasattr(request, 'FILES') and 'firmware_file' in request.FILES:
                    # Create firmware version
                    firmware = FirmwareVersion(
                        name=request.POST.get('name'),
                        version_number=request.POST.get('version_number'),
                        device_type=request.POST.get('device_type'),
                        description=request.POST.get('description', ''),
                        firmware_file=request.FILES['firmware_file'],
                        created_by=request.user
                    )
                    
                    # Calculate checksum
                    if firmware.firmware_file:
                        firmware.firmware_file.seek(0)
                        checksum = hashlib.sha256(firmware.firmware_file.read()).hexdigest()
                        firmware.checksum = checksum
                        firmware.firmware_file.seek(0)
                    
                    firmware.save()
                    
                    # Check if immediate update is requested
                    immediate_update = request.POST.get('immediate_update') == '1'
                    
                    if immediate_update:
                        # Start OTA updates for selected devices
                        service = OTAUpdateService()
                        successful_updates = 0
                        failed_updates = 0
                        
                        for device_id in target_devices:
                            try:
                                device = Device.objects.get(device_id=device_id)
                                
                                # Check if device is online
                                if device.device_status != 'online':
                                    logger.warning(f"Skipping offline device: {device.device_name}")
                                    continue
                                
                                # Check if device type matches firmware
                                if device.device_type not in [firmware.device_type, 'esp']:
                                    logger.warning(f"Device type mismatch for {device.device_name}")
                                    continue
                                
                                # Create OTA update record
                                ota_update = OTAUpdate.objects.create(
                                    device=device,
                                    firmware_version=firmware,
                                    initiated_by=request.user,
                                    previous_version=getattr(device.firmware_info, 'current_version', 'Unknown') if hasattr(device, 'firmware_info') else 'Unknown'
                                )
                                
                                # Start the update
                                if service.start_ota_update(ota_update):
                                    successful_updates += 1
                                else:
                                    failed_updates += 1
                                    
                            except Device.DoesNotExist:
                                logger.error(f"Device not found: {device_id}")
                                failed_updates += 1
                            except Exception as e:
                                logger.error(f"Error starting update for device {device_id}: {str(e)}")
                                failed_updates += 1
                        
                        if successful_updates > 0:
                            messages.success(request, f'Firmware uploaded and OTA updates started for {successful_updates} device(s)!')
                        if failed_updates > 0:
                            messages.warning(request, f'{failed_updates} device(s) could not be updated.')
                    else:
                        messages.success(request, f'Firmware {firmware.name} uploaded successfully! You can now manually start updates for selected devices.')
                    
                    return redirect('ota_dashboard')
                else:
                    messages.error(request, 'Please select a firmware file to upload.')
        except Exception as e:
            logger.warning(f"Error with firmware upload: {str(e)}")
            messages.error(request, f'Error uploading firmware: {str(e)}')
    else:
        # If migration is needed, add devices without firmware info
        for device in esp_devices:
            devices_with_firmware.append({
                'device': device,
                'firmware_info': None,
                'latest_update': None
            })

    # Add migration warning if needed
    if migration_needed:
        messages.warning(request, 'OTA database tables are not available. Run migrations to enable full OTA functionality.')

    context = {
        'esp_devices': esp_devices,
        'devices_with_firmware': devices_with_firmware,
        'firmware_versions': firmware_versions,
        'recent_updates': recent_updates,
        'upload_form': upload_form,
        'total_devices': esp_devices.count(),
        'devices_with_updates': sum(1 for d in devices_with_firmware if d.get('firmware_info') and d['firmware_info'].update_available),
        'active_updates': active_updates_count,
        'migration_needed': migration_needed,
    }

    return render(request, 'ota_update/dashboard.html', context)


@login_required
@require_http_methods(["POST"])
def initiate_ota_update(request, device_id):
    """Initiate OTA update for a specific device"""
    try:
        device = get_object_or_404(Device, device_id=device_id)
        
        # Check permissions
        if request.user.role not in ['admin', 'device-administrator']:
            return JsonResponse({'error': 'Access denied'}, status=403)
        
        if request.user.role == 'device-administrator' and device.added_by != request.user:
            return JsonResponse({'error': 'Access denied'}, status=403)

        firmware_version_id = request.POST.get('firmware_version_id')
        if not firmware_version_id:
            return JsonResponse({'error': 'Firmware version is required'}, status=400)

        firmware_version = get_object_or_404(FirmwareVersion, id=firmware_version_id)

        # Check if device type matches firmware
        if device.device_type not in [firmware_version.device_type, 'esp']:
            return JsonResponse({
                'error': f'Firmware is not compatible with {device.device_type} devices'
            }, status=400)

        # Check if there's already an active update
        active_update = OTAUpdate.objects.filter(
            device=device,
            status__in=['pending', 'in_progress']
        ).first()

        if active_update:
            return JsonResponse({
                'error': 'Device already has an active OTA update'
            }, status=400)

        # Create OTA update record
        with transaction.atomic():
            ota_update = OTAUpdate.objects.create(
                device=device,
                firmware_version=firmware_version,
                initiated_by=request.user,
                previous_version=getattr(device.firmware_info, 'current_version', 'Unknown') if hasattr(device, 'firmware_info') else 'Unknown'
            )

            # Start the OTA update process
            service = OTAUpdateService()
            success = service.start_ota_update(ota_update)

            if success:
                return JsonResponse({
                    'success': True,
                    'message': f'OTA update initiated for {device.device_name}',
                    'update_id': ota_update.id
                })
            else:
                ota_update.mark_failed("Failed to initiate OTA update")
                return JsonResponse({
                    'error': 'Failed to initiate OTA update'
                }, status=500)

    except Exception as e:
        logger.error(f"Error initiating OTA update: {str(e)}")
        return JsonResponse({'error': 'Internal server error'}, status=500)


@login_required
def ota_update_status(request, update_id):
    """Get OTA update status"""
    try:
        ota_update = get_object_or_404(OTAUpdate, id=update_id)
        
        # Check permissions
        if request.user.role not in ['admin', 'device-administrator']:
            return JsonResponse({'error': 'Access denied'}, status=403)
        
        if request.user.role == 'device-administrator' and ota_update.device.added_by != request.user:
            return JsonResponse({'error': 'Access denied'}, status=403)

        serializer = OTAUpdateSerializer(ota_update)
        return JsonResponse(serializer.data)

    except Exception as e:
        logger.error(f"Error getting OTA update status: {str(e)}")
        return JsonResponse({'error': 'Internal server error'}, status=500)


@login_required
@require_http_methods(["POST"])
def cancel_ota_update(request, update_id):
    """Cancel an ongoing OTA update"""
    try:
        ota_update = get_object_or_404(OTAUpdate, id=update_id)
        
        # Check permissions
        if request.user.role not in ['admin', 'device-administrator']:
            return JsonResponse({'error': 'Access denied'}, status=403)
        
        if request.user.role == 'device-administrator' and ota_update.device.added_by != request.user:
            return JsonResponse({'error': 'Access denied'}, status=403)

        if ota_update.status not in ['pending', 'in_progress']:
            return JsonResponse({
                'error': 'Cannot cancel update that is not pending or in progress'
            }, status=400)

        # Cancel the update
        service = OTAUpdateService()
        success = service.cancel_ota_update(ota_update)

        if success:
            return JsonResponse({
                'success': True,
                'message': 'OTA update cancelled successfully'
            })
        else:
            return JsonResponse({
                'error': 'Failed to cancel OTA update'
            }, status=500)

    except Exception as e:
        logger.error(f"Error cancelling OTA update: {str(e)}")
        return JsonResponse({'error': 'Internal server error'}, status=500)


@csrf_exempt
def firmware_download(request, firmware_id):
    """Serve firmware file for download by ESP devices"""
    try:
        firmware = get_object_or_404(FirmwareVersion, id=firmware_id, is_active=True)
        
        if not firmware.firmware_file:
            raise Http404("Firmware file not found")

        # Get the file path
        file_path = firmware.firmware_file.path
        
        if not os.path.exists(file_path):
            raise Http404("Firmware file not found on disk")

        # Serve the file
        with open(file_path, 'rb') as f:
            response = HttpResponse(f.read(), content_type='application/octet-stream')
            response['Content-Disposition'] = f'attachment; filename="{firmware.name}_{firmware.version_number}.bin"'
            response['Content-Length'] = firmware.file_size
            response['X-Firmware-Version'] = firmware.version_number
            response['X-Firmware-Checksum'] = firmware.checksum
            return response

    except Exception as e:
        logger.error(f"Error serving firmware file: {str(e)}")
        raise Http404("Firmware file not found")


@csrf_exempt
@api_view(['POST'])
def ota_progress_callback(request, update_id):
    """Callback endpoint for ESP devices to report OTA progress"""
    try:
        ota_update = get_object_or_404(OTAUpdate, id=update_id)
        
        data = request.data
        progress = data.get('progress', 0)
        status_msg = data.get('status', '')
        error = data.get('error', '')

        if error:
            ota_update.mark_failed(error)
        elif progress == 100:
            ota_update.mark_completed()
            # Update device firmware info
            firmware_info, created = DeviceFirmwareInfo.objects.get_or_create(
                device=ota_update.device
            )
            firmware_info.current_version = ota_update.firmware_version.version_number
            firmware_info.last_updated = timezone.now()
            firmware_info.update_available = False
            firmware_info.save()
        else:
            ota_update.update_progress(progress, status_msg)

        return Response({'success': True})

    except Exception as e:
        logger.error(f"Error in OTA progress callback: {str(e)}")
        return Response({'error': 'Internal server error'}, status=500)


@login_required
def delete_firmware(request, firmware_id):
    """Delete a firmware version"""
    if request.method == 'POST':
        try:
            firmware = get_object_or_404(FirmwareVersion, id=firmware_id)
            
            # Check permissions
            if request.user.role not in ['admin', 'device-administrator']:
                messages.error(request, 'Access denied')
                return redirect('ota_dashboard')
            
            if request.user.role == 'device-administrator' and firmware.created_by != request.user:
                messages.error(request, 'Access denied')
                return redirect('ota_dashboard')

            # Check if firmware is being used in any active updates
            active_updates = OTAUpdate.objects.filter(
                firmware_version=firmware,
                status__in=['pending', 'in_progress']
            ).count()

            if active_updates > 0:
                messages.error(request, 'Cannot delete firmware that is being used in active updates')
                return redirect('ota_dashboard')

            # Delete the firmware file
            if firmware.firmware_file:
                firmware.firmware_file.delete()

            firmware.delete()
            messages.success(request, f'Firmware {firmware.name} deleted successfully')

        except Exception as e:
            logger.error(f"Error deleting firmware: {str(e)}")
            messages.error(request, 'Error deleting firmware')

    return redirect('ota_dashboard')


@login_required
def check_device_updates(request):
    """Check for available updates for all ESP devices"""
    try:
        if request.user.role not in ['admin', 'device-administrator']:
            return JsonResponse({'error': 'Access denied'}, status=403)

        # Get ESP devices based on user role
        if request.user.role == 'admin':
            esp_devices = Device.objects.filter(device_type__in=['esp', 'esp32', 'esp8266'])
        else:
            esp_devices = Device.objects.filter(
                device_type__in=['esp', 'esp32', 'esp8266'],
                added_by=request.user
            )

        updates_available = 0
        for device in esp_devices:
            firmware_info, created = DeviceFirmwareInfo.objects.get_or_create(device=device)
            if firmware_info.check_for_updates():
                updates_available += 1

        return JsonResponse({
            'success': True,
            'updates_available': updates_available,
            'total_devices': esp_devices.count()
        })

    except Exception as e:
        logger.error(f"Error checking device updates: {str(e)}")
        return JsonResponse({'error': 'Internal server error'}, status=500)