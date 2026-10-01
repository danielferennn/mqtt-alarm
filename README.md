# MQTT Security Alarm System

An **edge computing** security alarm simulation built on the **MQTT** protocol.
Four services run together via Docker Compose: a Mosquitto broker, two sensor
publishers (door and smoke), and an alarm unit acting as the subscriber.

This project demonstrates core MQTT concepts used by edge devices:

- **Publish/subscribe** decoupling through a broker
- **Quality of Service (QoS)** levels 0/1/2 and how they differ
- **Retained messages** for storing a device's last known state
- **Last Will and Testament (LWT)** for detecting devices that drop off abruptly
- **Service dependencies and healthchecks** in Docker Compose

---

## Architecture

```text
                      +-------------------------+
                      |   Mosquitto Broker      |
                      |   (eclipse-mosquitto:2) |
                      |      port 1883          |
                      +------------+------------+
                                   |
        security/pintu  -----------|-----------  security/#  (QoS 2)
        security/pintu/status      |                    |
        security/asap              |                    |
        security/asap/status       |                    |
                                   |                    |
                        +----------+----------+   +-----+----------------+
                        |  publisher-pintu    |   |  alarm unit          |
                        |  publisher-asap     |   |  (subscriber)        |
                        +---------------------+   +----------------------+
```

**Data flow**

1. Each publisher connects to the broker, publishes `online` to its own status
   topic, and registers an `offline` Last Will on that same topic.
2. The door publisher alternates between `tertutup` (closed) and `terbuka` (open).
   The smoke publisher sends `aman` (safe), or `terdeteksi` (detected) when configured.
3. The alarm unit subscribes to `security/#` and logs every incoming message.
4. If a publisher stops abruptly (without an MQTT `DISCONNECT`), the broker
   publishes the `offline` Last Will and the alarm unit raises an alert.

---

## Project structure

```text
mqtt-alarm/
├── docker-compose.yml          # Four services, healthcheck, and volumes
├── broker/
│   └── mosquitto.conf          # Broker config (listener, persistence, logging)
├── alarm/
│   ├── alarm.py                # Subscriber: receives messages and raises ALERTs
│   ├── requirements.txt
│   └── Dockerfile
├── publisher-pintu/
│   ├── publisher_pintu.py      # Door sensor publisher (QoS 1, retained)
│   ├── requirements.txt
│   └── Dockerfile
├── publisher-asap/
│   ├── publisher_asap.py       # Smoke sensor publisher (QoS 2)
│   ├── requirements.txt
│   └── Dockerfile
└── README.md
```

---

## Prerequisites

- Docker Engine 20.10+ with the **Docker Compose v2** plugin
- Port **1883** free on the host
- Internet access on the first build (to pull base images)

---

## Running the system

From the project root:

```sh
docker compose up --build -d
docker compose logs -f alarm
```

The `publisher-pintu`, `publisher-asap`, and `alarm` services wait until the
broker reports `healthy` before starting, so no connection attempt fails at boot.

Stop all services:

```sh
docker compose down
```

Remove the volumes as well (retained data and broker logs are deleted):

```sh
docker compose down -v
```

---

## Topics and QoS

| Purpose             | Topic                   | QoS | Retained |
| ------------------- | ----------------------- | --: | -------- |
| Door state          | `security/pintu`        |   1 | Yes      |
| Smoke state         | `security/asap`         |   2 | No       |
| Door connection     | `security/pintu/status` |   1 | Yes      |
| Smoke connection    | `security/asap/status`  |   1 | Yes      |
| Alarm subscription  | `security/#`            |   2 | —        |

Note: subscription QoS and publishing QoS are negotiated down to the lower
value, so QoS 1 messages from the door publisher still reach the alarm unit
with `qos=1`.

---

## Configuration

Set through environment variables in `docker-compose.yml`.

| Variable                  | Service         | Default  | Description                                    |
| ------------------------- | --------------- | -------- | ---------------------------------------------- |
| `BROKER_HOST`             | all             | `broker` | Broker hostname on the Compose network         |
| `BROKER_PORT`             | all             | `1883`   | Broker port                                    |
| `INTERVAL_SECONDS`        | both publishers | `5`      | Delay between publications                     |
| `PUBLISH_TIMEOUT_SECONDS` | both publishers | `5`      | Ack wait limit before a publish is marked failed |
| `ASAP_STATUS`             | `publisher-asap`| `aman`   | `aman` (safe) or `terdeteksi` (detected)       |

---

## Test scenarios

### 1. Normal flow

```sh
docker compose up --build -d
docker compose logs -f alarm
```

Expected: the alarm unit receives alternating messages from `security/pintu`
(QoS 1) and `security/asap` (QoS 2), plus `online` messages on both status topics.

### 2. Simulated smoke detection

Set `ASAP_STATUS` to `terdeteksi` in `docker-compose.yml`, then:

```sh
docker compose up -d --force-recreate publisher-asap
docker compose logs --since=30s alarm
```

Expected line:

```text
ALERT: asap terdeteksi (security/asap)
```

The alarm unit also recognises `detected`, `asap terdeteksi`, and
`smoke detected` (case-insensitive).

### 3. Proving the Last Will and Testament (LWT)

`docker kill` terminates the process without an MQTT `DISCONNECT`, so the broker
publishes the `offline` Last Will to subscribers.

Terminal 1:

```sh
docker compose logs -f alarm
```

Terminal 2:

```sh
docker kill publisher-pintu
docker compose logs --since=30s alarm
```

Expected line:

```text
ALERT: sensor pintu offline (security/pintu/status)
```

The same test works for `docker kill publisher-asap`, producing
`ALERT: sensor asap offline (security/asap/status)`.

After `docker kill`, the container stays stopped until started explicitly:

```sh
docker compose start publisher-pintu
```

On reconnect, the publisher publishes `online` again so the alarm knows the
device has recovered.

### 4. Resilience across a broker restart

```sh
docker restart mqtt-alarm-broker
```

Neither publisher crashes: a failed publish is handled as a warning, and the
connection is restored automatically by the MQTT library.

```text
[WARN] Gagal publish security/pintu -> tertutup: Message publish failed: The client is not currently connected.
...
[MQTT] Publisher pintu terhubung ke broker
[STATUS] security/pintu/status -> online
```

---

## Troubleshooting

| Symptom                                                        | Cause & fix                                                                     |
| -------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| `port is already allocated`                                    | Port 1883 is in use. Stop the other process or change the port mapping.          |
| Publishers repeatedly log `[WARN] Gagal publish`               | The broker is down. Check `docker compose ps` and the broker health status.      |
| Alarm immediately reports `ALERT: sensor ... offline` on start  | A retained `offline` Last Will left over from a previous session. It clears once the publisher reconnects and sends `online`. For a clean state, run `docker compose down -v` first. |
| Changing `ASAP_STATUS` has no effect                           | The container must be recreated: `docker compose up -d --force-recreate publisher-asap`. |

---

## Security notes

This configuration is intended for **demos and learning**, not for production:

- `allow_anonymous true` — the broker accepts connections without authentication.
- Port 1883 is exposed to the host without TLS.

For real deployments, enable authentication (username/password or client
certificates), use TLS on port 8883, and never expose the broker to a public network.
