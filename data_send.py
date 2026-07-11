import requests
import time
import random

# API endpoint
BASE_URL = 'http://10.7.31.114:8000/device/data/'

# Device configs
DEVICES = [
    {
        "device_id": "01",
        "type": "env"
    },
    {
        "device_id": "02",
        "type": "air_quality"
    }
]

def generate_env_data():
    """Temperature, humidity, signal"""
    return {
        'temperature': round(random.uniform(25.0, 30.0), 1),
        'humidity': round(random.uniform(35.0, 45.0), 1),
        'signal_strength': random.randint(-70, -50)
    }

def generate_mq5_data():
    """Controlled MQ5 sensor data"""
    return {
        'air_quality': random.randint(130, 150),  # constrained range
        'gas_detected': False,                   # always false
        'signal_strength': random.randint(-70, -50)
    }

def send_data(device):
    payload = {
        'device_id': device["device_id"],
        'status': 'ON'
    }

    if device["type"] == "env":
        payload.update(generate_env_data())
    elif device["type"] == "air_quality":
        payload.update(generate_mq5_data())

    try:
        response = requests.post(BASE_URL, json=payload)
        print(f"[{time.strftime('%H:%M:%S')}] Device {device['device_id']} Sent: {payload}")
        print("Status:", response.status_code, "| Response:", response.text)
    except requests.exceptions.RequestException as e:
        print(f"Device {device['device_id']} failed:", e)


# Main loop
while True:
    for device in DEVICES:
        send_data(device)
    
    time.sleep(10)