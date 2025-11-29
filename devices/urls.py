from django.urls import path
from . import views


urlpatterns = [
    path('device-admin/', views.device_admin_dashboard, name='device_admin_dashboard'),
    path('add/', views.add_device, name='add_device'),
    path('delete/<int:device_id>/', views.delete_device, name='delete_device'),
    path('set-global-interval/', views.set_global_interval, name='set_global_interval'),
    path('api/esp-devices/', views.esp_devices_api, name='esp_devices_api'),
       # URL for configuring a device (shows the pin config page)
    path('device/<str:device_id>/', views.device_config, name='device_config'),
    path('admin-dashboard/', views.admin_dashboard, name='admin_dashboard'),
    
    # URL for toggling a specific pin on a device
    path('toggle-pin/<str:device_id>/<int:pin_number>/', views.toggle_pin, name='toggle_pin'),
    path('edit-device/<int:device_id>/', views.edit_device, name='edit_device'),
    
    # New API endpoints for user dashboard
    path('api/device/<str:device_id>/toggle-status/', views.toggle_device_status, name='toggle_device_status'),
    
    # New device control endpoints
    path('api/device/<str:device_id>/command/', views.send_device_command, name='send_device_command'),

    path('api/devices/status/', views.get_device_statuses, name='get_device_statuses'),
    path('api/alerts/unread-count/', views.get_unread_alerts_count, name='get_unread_alerts_count'),
]
 