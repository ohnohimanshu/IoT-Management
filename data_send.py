import requests
import time
import random

# API endpoint
url = 'http://10.7.11.12:8000/device/data/'

# Static values
device_id = '01'
status = 'ON'

def generate_sensor_data():
    """Simulate temperature, humidity, and signal strength"""
    return {
        'temperature': round(random.uniform(25.0, 30.0), 1),
        'humidity': round(random.uniform(35.0, 45.0), 1),
        'signal_strength': random.randint(-70, -50)
    }

while True:
    # Create payload with random sensor data
    sensor_data = generate_sensor_data()
    payload = {
        'device_id': device_id,
        'status': status,
        **sensor_data
    }

    try:
        response = requests.post(url, json=payload)
        print(f"[{time.strftime('%H:%M:%S')}] Sent: {payload}")
        print("Status:", response.status_code, "| Response:", response.text)
    except requests.exceptions.RequestException as e:
        print("Request failed:", e)

    # Delay between sends (e.g., 10 seconds)
    time.sleep(10)
