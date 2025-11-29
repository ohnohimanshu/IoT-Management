from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from devices.models import Device
from api.models import DeviceData
from .serializers import DeviceSerializer, DeviceDataSerializer
from django.utils import timezone
import re
import logging

logger = logging.getLogger(__name__)

@api_view(['POST'])
def device_data_upload(request):
    try:
        device_id = request.data.get('device_id', '').strip()
        
        # Validate device_id is provided
        if not device_id:
            return Response(
                {'error': 'Device ID is required'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate device_id format - only alphanumeric, hyphens, underscores
        # This prevents injection of special characters like ';', '3', etc.
        if not re.match(r'^[a-zA-Z0-9_-]+$', device_id):
            logger.warning(f"Invalid device_id format attempted: {device_id}")
            return Response(
                {'error': 'Invalid Device ID format. Only alphanumeric characters, hyphens, and underscores are allowed'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Validate device_id length
        if len(device_id) > 100:
            return Response(
                {'error': 'Device ID must be 100 characters or less'}, 
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Only accept data from REGISTERED devices
        try:
            device = Device.objects.get(device_id=device_id)
        except Device.DoesNotExist:
            logger.warning(f"Data upload from unregistered device: {device_id}")
            return Response(
                {'error': 'Device not registered. Please register the device through the admin panel first.'}, 
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Update last_seen timestamp
        device.last_seen = timezone.now()
        device.save(update_fields=['last_seen'])

        # Create device data record
        data = {
            'device': device,
            'data': request.data
        }
        
        device_data = DeviceData.objects.create(**data)
        serializer = DeviceDataSerializer(device_data)
        
        return Response(serializer.data, status=status.HTTP_201_CREATED)
        
    except Device.DoesNotExist:
        return Response(
            {'error': 'Device not found'}, 
            status=status.HTTP_403_FORBIDDEN
        )
    except Exception as e:
        logger.error(f"Error in device_data_upload: {str(e)}")
        return Response(
            {'error': 'Internal server error'}, 
            status=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
