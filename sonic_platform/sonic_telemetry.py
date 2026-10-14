import redis
import time
import random

STATE_DB = 6

r = redis.Redis(host='localhost', port=6379, db=STATE_DB, decode_responses=True)

PORT = "Ethernet0"

def update_telemetry():
    key = f"CUSTOM_TELEMETRY|{PORT}"

    data = {
        "temperature": str(random.randint(50, 90)),
        "error_rate": str(round(random.random(), 5)),
        "status": "OK"
    }

    r.hset(key, mapping=data)
    print(f"Updated: {data}")

def main():
    while True:
        update_telemetry()
        time.sleep(5)

if __name__ == "__main__":
    main()
