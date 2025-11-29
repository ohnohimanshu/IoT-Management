import re
from urllib.parse import parse_qs
from django.utils import timezone
from devices.models import Device
from api.models import DeviceData

# --- Regex patterns for legacy LoRa payloads ---
DEVICE_ID_BRACKET_RE = re.compile(r"^<([^>]+)>")
DEVICE_ID_PREFIX_TEM_RE = re.compile(r"^([A-Za-z0-9]+)tem=")


# --- Helper: convert to float if possible ---
def _to_float_or_str(v):
    try:
        return float(v)
    except Exception:
        return v


# --- Extract device_id from JSON, payload, or topic ---
def extract_device_id(payload: str | dict, topic: str | None = None) -> str | None:
    """
    Extracts device_id from:
      1. JSON payload (device_id key)
      2. Legacy text payload (<4567> or 04tem=)
      3. Topic suffix (lora/p2p/<id>)
    """
    # Case 1: JSON payload
    if isinstance(payload, dict):
        dev_id = payload.get("device_id")
        if dev_id:
            return str(dev_id)

    # Case 2: legacy text payload
    if isinstance(payload, str) and payload:
        m = DEVICE_ID_BRACKET_RE.match(payload)
        if m:
            return m.group(1)
        m2 = DEVICE_ID_PREFIX_TEM_RE.match(payload)
        if m2:
            return m2.group(1)

    # Case 3: from topic
    if topic:
        parts = topic.split("/")
        if len(parts) >= 3 and parts[0] == "lora" and parts[1] == "p2p":
            return parts[2]

    return None


# --- Parse legacy key-value LoRa payload ---
def parse_kv_payload(payload: str) -> dict:
    """
    Converts 'tem=30.0&hum=65.0&status=ON' into:
      {'tem':'30.0','hum':'65.0','status':'ON'}
    Removes any '<id>' or '04' prefix before 'tem='.
    """
    if not payload:
        return {}

    # strip leading <id>
    if payload.startswith("<") and ">" in payload:
        payload = payload.split(">", 1)[1]

    # strip leading numeric prefix before tem=
    m2 = DEVICE_ID_PREFIX_TEM_RE.match(payload)
    if m2:
        payload = payload[len(m2.group(1)):]  # remove prefix like '04'

    q = parse_qs(payload, keep_blank_values=True, strict_parsing=False)
    flat = {k: (v[0] if isinstance(v, list) and v else "") for k, v in q.items()}
    return flat


# --- Normalize final fields for DeviceData ---
def normalize_fields(body: dict, device_id: str | None = None) -> dict:
    """
    Normalizes both:
      - JSON LoRa payloads (already parsed)
      - Legacy key-value payloads (tem=..., hum=..., etc.)
    Includes device_id in the final stored document.
    """
    payload = body.get("payload")
    parsed = {}

    # Case 1: Legacy payload string
    if isinstance(payload, str) and "tem=" in payload:
        parsed = parse_kv_payload(payload)
    # Case 2: JSON LoRa structure (already parsed)
    elif isinstance(body, dict):
        parsed = body

    doc = {
        "device_id": device_id or parsed.get("device_id"),
        "temperature": _to_float_or_str(parsed.get("temperature") or parsed.get("tem")),
        "humidity": _to_float_or_str(parsed.get("humidity") or parsed.get("hum")),
        "status": parsed.get("status"),
        "signal_strength": _to_float_or_str(parsed.get("signal_strength") or parsed.get("rssi")),
        "rssi": _to_float_or_str(parsed.get("rssi")) if parsed.get("rssi") not in (None, "") else None,
        "snr": _to_float_or_str(parsed.get("snr")) if parsed.get("snr") not in (None, "") else None,
        "ts": body.get("ts"),
        "raw": {
            "payload": payload if isinstance(payload, str) else None,
            "topic": body.get("topic"),
        },
    }

    # Remove empty or None values for cleanliness
    return {k: v for k, v in doc.items() if v not in (None, {}, [], "")}


# --- Save DeviceData + update Device ---
def persist_device_data(*, device_id: str, data: dict, topic: str | None = None) -> DeviceData:
    """
    Ensures device exists, updates last_seen, and stores normalized DeviceData.
    Only accepts data from REGISTERED devices.
    Also saves device_id inside DeviceData.data JSON.
    """
    if not device_id:
        raise ValueError("Missing device_id")

    # Only accept data from registered devices
    try:
        device = Device.objects.get(device_id=device_id)
    except Device.DoesNotExist:
        raise ValueError(f"Device '{device_id}' not registered. Please register through admin panel first.")
    
    device.last_seen = timezone.now()
    device.save(update_fields=["last_seen"])

    # Clean and normalize data
    full = dict(data or {})
    full.pop("hex", None)
    if topic:
        full["topic"] = topic

    doc = normalize_fields(full, device_id=device_id)

    # Save DeviceData JSON
    return DeviceData.objects.create(device=device, data=doc)
