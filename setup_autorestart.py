import os
import getpass

# Get current user
user = getpass.getuser()

# Define necessary paths
project_dir = "/home/data/Desktop/forubuntu/esp_projectfr/esp_project"  
venv_python = "/home/data/Desktop/forubuntu/esp_projectfr/esp_project/venv/bin/python3"

service_name = "django-app"
service_file_path = f"/etc/systemd/system/{service_name}.service"

# Define the systemd service content
service_content = f"""[Unit]
Description=Django Application
After=network.target

[Service]
User={user}
Group={user}
WorkingDirectory={project_dir}
ExecStart={venv_python} {project_dir}/manage.py runserver 10.7.33.126:8000
Restart=always
RestartSec=5
Environment="DJANGO_SETTINGS_MODULE=esp_project.settings"
Environment="PYTHONPATH={project_dir}"

[Install]
WantedBy=multi-user.target
"""

def create_service():
    """Create systemd service file."""
    try:
        print("Creating systemd service file...")
        with open("django-app.service", "w") as f:
            f.write(service_content)
        
        os.system(f"sudo mv django-app.service {service_file_path}")
        os.system(f"sudo chmod 644 {service_file_path}")
        print(f"Service file created at {service_file_path}")
    except Exception as e:
        print(f"Error creating service file: {e}")

def enable_and_start_service():
    """Enable and start the service."""
    try:
        os.system("sudo systemctl daemon-reload")
        os.system(f"sudo systemctl enable {service_name}")
        os.system(f"sudo systemctl start {service_name}")
        print(f"Service {service_name} started and enabled at boot.")
    except Exception as e:
        print(f"Error enabling or starting service: {e}")

def check_service_status():
    """Check service status."""
    os.system(f"sudo systemctl status {service_name}")

if __name__ == "__main__":
    create_service()
    enable_and_start_service()
    check_service_status()
