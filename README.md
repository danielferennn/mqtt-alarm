# Sistem Alarm Keamanan via MQTT

Simulasi sistem alarm keamanan berbasis **edge computing** menggunakan protokol **MQTT**.
Empat layanan berjalan bersama lewat Docker Compose: satu broker Mosquitto, dua publisher
sensor (pintu dan asap), dan satu unit alarm sebagai subscriber.

Proyek ini mendemonstrasikan konsep inti MQTT untuk perangkat edge:

- Pemisahan peran **publish/subscribe** melalui broker
- **Quality of Service (QoS)** 0/1/2 dan perbedaannya
- **Retained message** untuk menyimpan status terakhir perangkat
- **Last Will and Testament (LWT)** untuk mendeteksi perangkat yang terputus mendadak
- **Dependency & healthcheck** antar-layanan di Docker Compose

---

## Arsitektur

```text
                      +-------------------------+
                      |   Broker Mosquitto      |
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
                        |  publisher-pintu    |   |  unit alarm          |
                        |  publisher-asap     |   |  (subscriber)        |
                        +---------------------+   +----------------------+
```

**Alur data**

1. Setiap publisher tersambung ke broker, menerbitkan `online` ke topic status miliknya,
   dan memasang LWT `offline` pada topic yang sama.
2. Publisher pintu bergantian mengirim `tertutup` dan `terbuka`.
   Publisher asap mengirim `aman` (atau `terdeteksi` bila dikonfigurasi).
3. Unit alarm berlangganan `security/#` dan mencetak setiap pesan yang masuk.
4. Bila publisher berhenti mendadak (tanpa MQTT `DISCONNECT`), broker menerbitkan LWT
   `offline` dan unit alarm mencetak peringatan.

---

## Struktur proyek

```text
mqtt-alarm/
├── docker-compose.yml          # Definisi 4 layanan, healthcheck, dan volume
├── broker/
│   └── mosquitto.conf          # Konfigurasi broker (listener, persistence, logging)
├── alarm/
│   ├── alarm.py                # Subscriber: menerima pesan & mencetak ALERT
│   ├── requirements.txt
│   └── Dockerfile
├── publisher-pintu/
│   ├── publisher_pintu.py      # Publisher sensor pintu (QoS 1, retained)
│   ├── requirements.txt
│   └── Dockerfile
├── publisher-asap/
│   ├── publisher_asap.py       # Publisher sensor asap (QoS 2)
│   ├── requirements.txt
│   └── Dockerfile
└── README.md
```

---

## Prasyarat

- Docker Engine 20.10+ dengan plugin **Docker Compose v2**
- Port **1883** bebas di host
- Koneksi internet pada build pertama (mengunduh image dasar)

---

## Menjalankan sistem

Dari folder root proyek:

```sh
docker compose up --build -d
docker compose logs -f alarm
```

Layanan `publisher-pintu`, `publisher-asap`, dan `alarm` menunggu broker berstatus
`healthy` sebelum dijalankan, sehingga tidak ada percobaan koneksi yang gagal saat start.

Hentikan seluruh layanan:

```sh
docker compose down
```

Hapus sekaligus volume (data retained & log broker ikut terhapus):

```sh
docker compose down -v
```

---

## Topic dan QoS

| Fungsi                  | Topic                  | QoS | Retained |
| ----------------------- | ---------------------- | --: | -------- |
| Status pintu            | `security/pintu`       |   1 | Ya       |
| Status asap             | `security/asap`        |   2 | Tidak    |
| Status koneksi pintu    | `security/pintu/status`|   1 | Ya       |
| Status koneksi asap     | `security/asap/status` |   1 | Ya       |
| Langganan unit alarm    | `security/#`           |   2 | —        |

Catatan: QoS langganan dan QoS publikasi dinegosiasikan turun ke nilai terendah,
sehingga pesan QoS 1 dari publisher pintu tetap diterima unit alarm dengan `qos=1`.

---

## Konfigurasi

Diatur melalui environment variable pada `docker-compose.yml`.

| Variabel                | Layanan           | Default  | Keterangan                                            |
| ----------------------- | ----------------- | -------- | ----------------------------------------------------- |
| `BROKER_HOST`           | semua             | `broker` | Nama host broker di jaringan Compose                  |
| `BROKER_PORT`           | semua             | `1883`   | Port broker                                           |
| `INTERVAL_SECONDS`      | kedua publisher   | `5`      | Jeda antar publikasi                                  |
| `PUBLISH_TIMEOUT_SECONDS`| kedua publisher  | `5`      | Batas tunggu ack publish sebelum menandai gagal       |
| `ASAP_STATUS`           | `publisher-asap`  | `aman`   | `aman` atau `terdeteksi`                              |

---

## Skenario pengujian

### 1. Alur normal

```sh
docker compose up --build -d
docker compose logs -f alarm
```

Yang diharapkan: unit alarm menerima pesan bergantian dari `security/pintu` (QoS 1) dan
`security/asap` (QoS 2), serta pesan `online` pada kedua topic status.

### 2. Simulasi asap terdeteksi

```sh
docker compose up -d --build publisher-asap
# ubah ASAP_STATUS menjadi "terdeteksi" pada docker-compose.yml terlebih dahulu
docker compose logs --since=30s alarm
```

Baris yang diharapkan:

```text
ALERT: asap terdeteksi (security/asap)
```

Unit alarm juga mengenali nilai `detected`, `asap terdeteksi`, dan `smoke detected`
(tidak peka huruf besar/kecil).

### 3. Bukti Last Will and Testament (LWT)

`docker kill` mengakhiri proses tanpa MQTT `DISCONNECT`, sehingga broker menerbitkan
LWT `offline` ke subscriber.

Terminal 1:

```sh
docker compose logs -f alarm
```

Terminal 2:

```sh
docker kill publisher-pintu
docker compose logs --since=30s alarm
```

Baris yang diharapkan:

```text
ALERT: sensor pintu offline (security/pintu/status)
```

Pengujian yang sama berlaku untuk `docker kill publisher-asap`, dengan baris
`ALERT: sensor asap offline (security/asap/status)`.

Setelah `docker kill`, container tetap berhenti sampai dijalankan kembali secara eksplisit:

```sh
docker compose start publisher-pintu
```

Saat tersambung kembali, publisher menerbitkan `online` sehingga alarm tahu perangkat pulih.

### 4. Resiliensi saat broker direstart

```sh
docker restart mqtt-alarm-broker
```

Kedua publisher tidak crash: kegagalan publish ditangani sebagai peringatan,
lalu koneksi dipulihkan otomatis oleh library MQTT.

```text
[WARN] Gagal publish security/pintu -> tertutup: Message publish failed: The client is not currently connected.
...
[MQTT] Publisher pintu terhubung ke broker
[STATUS] security/pintu/status -> online
```

---

## Troubleshooting

| Gejala                                             | Penyebab & solusi                                                                 |
| -------------------------------------------------- | --------------------------------------------------------------------------------- |
| `port is already allocated`                        | Port 1883 dipakai proses lain. Hentikan proses tersebut atau ubah mapping port.    |
| Publisher berulang kali mencetak `[WARN] Gagal publish` | Broker sedang mati. Cek `docker compose ps` dan status health broker.        |
| Alarm langsung mencetak `ALERT: sensor ... offline` saat start | LWT `offline` yang tersisa (retained) dari sesi sebelumnya. Hilang setelah publisher tersambung dan mengirim `online`. Untuk kondisi bersih, jalankan `docker compose down -v` lebih dulu. |
| Perubahan `ASAP_STATUS` tidak berefek              | Container perlu dibuat ulang: `docker compose up -d --force-recreate publisher-asap`. |

---

## Catatan keamanan

Konfigurasi ini ditujukan untuk **demo dan pembelajaran**, bukan produksi:

- `allow_anonymous true` — broker menerima koneksi tanpa autentikasi.
- Port 1883 diekspos ke host tanpa TLS.

Untuk penggunaan nyata, aktifkan autentikasi (username/password atau sertifikat klien),
gunakan TLS pada port 8883, dan jangan mengekspos broker ke jaringan publik.
