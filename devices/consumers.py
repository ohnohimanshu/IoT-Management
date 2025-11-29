import json
import logging
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import Device
from api.models import DeviceData

logger = logging.getLogger(__name__)

class DeviceDataConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        try:
            self.device_id = self.scope['url_route']['kwargs']['device_id']
            self.room_group_name = f'device_data_{self.device_id}'
            logger.info(f"WebSocket connecting for device_id: {self.device_id}")

            # Join room group
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )

            await self.accept()
            logger.info(f"WebSocket connection accepted for device_id: {self.device_id}")

            # Send initial data
            initial_data = await self.get_latest_data()
            if initial_data:
                await self.send(text_data=json.dumps(initial_data))
                logger.info(f"Sent initial data for device_id: {self.device_id}")
            else:
                logger.warning(f"No initial data available for device_id: {self.device_id}")

        except Exception as e:
            logger.error(f"Error in WebSocket connect: {str(e)}", exc_info=True)
            await self.close()

    async def disconnect(self, close_code):
        try:
            # Leave room group
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            logger.info(f"WebSocket disconnected for device_id: {self.device_id}")
        except Exception as e:
            logger.error(f"Error in WebSocket disconnect: {str(e)}", exc_info=True)

    async def receive(self, text_data):
        try:
            logger.info(f"Received WebSocket message for device_id: {self.device_id}")
            # Handle incoming messages if needed
            pass
        except Exception as e:
            logger.error(f"Error in WebSocket receive: {str(e)}", exc_info=True)

    async def device_data_update(self, event):
        try:
            # Send message to WebSocket
            await self.send(text_data=json.dumps(event['data']))
            logger.info(f"Sent data update for device_id: {self.device_id}")
        except Exception as e:
            logger.error(f"Error in device_data_update: {str(e)}", exc_info=True)

    async def device_command(self, event):
        try:
            # Send the command to the WebSocket client
            await self.send(text_data=json.dumps({
                'type': 'device_command',
                'command': event['command']
            }))
            logger.info(f"Sent device command for device_id: {self.device_id}")
        except Exception as e:
            logger.error(f"Error in device_command: {str(e)}", exc_info=True)

    @database_sync_to_async
    def get_latest_data(self):
        try:
            device = Device.objects.get(device_id=self.device_id)
            logger.info(f"Found device: {device.device_name}")
            
            latest_data = DeviceData.objects.filter(device=device).order_by('-timestamp')[:10]
            logger.info(f"Retrieved {latest_data.count()} latest records")
            
            formatted_data = []
            for data in latest_data:
                try:
                    # Handle MongoDB JSONField data
                    if hasattr(data.data, 'items'):  # Check if it's a dict-like object
                        data_dict = dict(data.data)
                    else:
                        data_dict = json.loads(str(data.data))
                    
                    data_dict['timestamp'] = data.timestamp.isoformat()
                    formatted_data.append(data_dict)
                except (json.JSONDecodeError, TypeError, AttributeError) as e:
                    logger.error(f"Error formatting data for entry {data.id}: {str(e)}")
                    continue
            
            logger.info(f"Successfully formatted {len(formatted_data)} records")
            return formatted_data
            
        except Device.DoesNotExist:
            logger.error(f"Device not found: {self.device_id}")
            return []
        except Exception as e:
            logger.error(f"Error in get_latest_data: {str(e)}", exc_info=True)
            return [] 