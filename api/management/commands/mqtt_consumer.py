# api/management/commands/mqtt_consumer.py
from django.core.management.base import BaseCommand
from django.conf import settings
from api.utils import extract_device_id, persist_device_data
import paho.mqtt.client as mqtt
import json, logging, time, sys

# Force visible logs in `docker compose logs -f mqtt_consumer`
logging.basicConfig(
    level=logging.INFO,
    stream=sys.stdout,
    format="%(levelname)s:%(name)s:%(message)s"
)
log = logging.getLogger(__name__)

def mqtt_cfg():
    cfg = getattr(settings, "MQTT", {})
    return {
        "HOST": cfg.get("HOST", "esp_project_mosquitto"),   # service name in compose
        "PORT": int(cfg.get("PORT", 1883)),
        "TOPIC": cfg.get("TOPIC", "lora/p2p/#"),
        "USERNAME": cfg.get("USERNAME") or None,
        "PASSWORD": cfg.get("PASSWORD") or None,
        "CLIENT_ID": cfg.get("CLIENT_ID", "django-consumer"),
        "TLS": bool(cfg.get("TLS", False)),
    }

class Command(BaseCommand):
    help = "Subscribe to MQTT and store LoRa packets to DeviceData (no hex)."

    def handle(self, *args, **opts):
        cfg = mqtt_cfg()
        log.warning("MQTT bootstrap: host=%s port=%s topic=%s client_id=%s",
                    cfg["HOST"], cfg["PORT"], cfg["TOPIC"], cfg["CLIENT_ID"])

        client = mqtt.Client(client_id=cfg["CLIENT_ID"], clean_session=True)

        if cfg["USERNAME"]:
            client.username_pw_set(cfg["USERNAME"], cfg["PASSWORD"] or "")
        if cfg["TLS"]:
            client.tls_set()

        def on_connect(c, u, flags, rc):
            log.warning("on_connect rc=%s", rc)
            if rc == 0:
                log.warning("MQTT connected; subscribing %s", cfg["TOPIC"])
                c.subscribe(cfg["TOPIC"], qos=0)
            else:
                log.error("MQTT connect failed rc=%s", rc)

        def on_message(c, u, msg):
            log.warning("on_message topic=%s payload_len=%d", msg.topic, len(msg.payload or b""))
            try:
                body = json.loads((msg.payload or b"").decode("utf-8", errors="ignore"))
                device_id = body.get("device_id") or extract_device_id(body.get("payload",""), msg.topic)

                if not device_id:
                    log.warning("Skip: missing device_id topic=%s body=%s", msg.topic, body)
                    return
                
                try:
                    rec = persist_device_data(device_id=device_id, data=body, topic=msg.topic)
                    log.warning("Stored DeviceData id=%s device_id=%s", rec.id, device_id)
                except ValueError as e:
                    log.warning("Rejected data from unregistered device: %s", e)
                    return
                    
            except Exception as e:
                log.exception("Error handling MQTT message: %s", e)

        client.on_connect = on_connect
        client.on_message = on_message

        while True:
            try:
                log.warning("Connecting to broker %s:%s ...", cfg["HOST"], cfg["PORT"])
                client.connect(cfg["HOST"], cfg["PORT"], keepalive=60)
                client.loop_forever(retry_first_connection=True)
            except Exception as e:
                log.error("MQTT connection error: %s; retry in 5s", e)
                time.sleep(5)
