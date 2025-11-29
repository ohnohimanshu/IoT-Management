from django.urls import path
from . import views

urlpatterns = [
    # Main OTA dashboard
    path('', views.ota_dashboard, name='ota_dashboard'),
    
    # OTA update operations
    path('update/<str:device_id>/', views.initiate_ota_update, name='initiate_ota_update'),
    path('status/<int:update_id>/', views.ota_update_status, name='ota_update_status'),
    path('cancel/<int:update_id>/', views.cancel_ota_update, name='cancel_ota_update'),
    
    # Firmware management
    path('firmware/<int:firmware_id>/download/', views.firmware_download, name='firmware_download'),
    path('firmware/<int:firmware_id>/delete/', views.delete_firmware, name='delete_firmware'),
    
    # Device callbacks and API
    path('progress/<int:update_id>/', views.ota_progress_callback, name='ota_progress_callback'),
    path('check-updates/', views.check_device_updates, name='check_device_updates'),
]