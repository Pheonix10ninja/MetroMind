import time
import requests
from datetime import datetime
import os
API_KEY = os.environ["MTA_API_KEY"]
URL = "https://bustime.mta.info/api/siri/vehicle-monitoring.json"

POLL_INTERVAL_SECONDS = 15

def fetch_data():
    params = {
        "key": API_KEY,
        "version": "2",
        "VehicleMonitoringDetailLevel": "minimum"
    }
    response = requests.get(URL, params=params, timeout=30)
    response.raise_for_status()
    return response.json()

def main():
    
    print("MetroMind collector started.")
    while True:
        try:
            data = fetch_data()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            vehicle_count = len(
                data["Siri"]["ServiceDelivery"]["VehicleMonitoringDelivery"][0]["VehicleActivity"]
            )
            print(f"[{now}] Received data for {vehicle_count} buses")
        except Exception as e:
            print("Error:", e)

        time.sleep(POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    main()
