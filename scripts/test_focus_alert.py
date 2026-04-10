import sys
from typing import Any, Dict

import requests


def main() -> None:
    if len(sys.argv) < 4:
        print("translated: python test_focus_alert.py <base_url> <mac> <alert_token>")
        print("translated: python test_focus_alert.py http://127.0.0.1:8000 AA:BB:CC:DD:EE:FF <devicealert_token>")
        print("")
        print("translatedGet  alert_token：")
        print("1) translated Web translated“translated”，translated alert_token（translated）。")
        print("2) translated owner translated：POST /api/device/{mac}/alert-token Get 。")
        sys.exit(1)

    base_url = sys.argv[1].rstrip("/")
    mac = sys.argv[2]
    alert_token = sys.argv[3]

    url = f"{base_url}/api/device/{mac}/alert"
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    headers["X-Agent-Token"] = alert_token

    payload: Dict[str, Any] = {
        "sender": "translated",
        "message": "translated，translated！",
        "level": "critical",
    }

    print(f"POST {url}")
    print(f"Headers: {headers}")
    print(f"Payload: {payload}")

    resp = requests.post(url, json=payload, headers=headers, timeout=5)
    print(f"Status: {resp.status_code}")
    try:
        print("Body:", resp.json())
    except Exception:
        print("Body (raw):", resp.text)


if __name__ == "__main__":
    main()

