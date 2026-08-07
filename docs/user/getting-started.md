# Getting Started

`whz-lora` runs an independent LoRaWAN network on the WHZ campus,
powered by a self-hosted ChirpStack v4 stack in Docker Compose.
Sensors talk to a Kerlink gateway, the gateway forwards their frames
to the stack, and the stack publishes them as JSON on MQTT for
research scripts to consume.

This page is for operators bringing up a fresh installation.

## Prerequisites

| Tool | Why |
|---|---|
| Docker Desktop for Windows | LoRaWAN Network Server runtime |
| Python 3.12+ | Smoke test + provisioning helpers |
| Node.js 20+ | Codec unit tests |
| `gh` CLI | Issues, PRs, and repository management |
| `pip install -r requirements.txt` | Documentation build dependencies |

## Prepare a Linux field host (Raspberry Pi)

Skip this on a Windows workstation — it applies to the Raspberry Pi (or any
Debian host) that runs the stack in the field.

A Linux host needs a handful of settings that Docker Compose cannot make for
you. Without them the host loses its logs on every reboot, cannot enforce
container memory limits, and fills its SD card with unrotated container logs.
Each one is there because it actually took the field host down once — see the
[field diagnosis](https://github.com/theautomatist/whz-lora/blob/main/docs/developer/analysis/pi-field-diagnosis-2026-08-01.md).

```bash
sudo ./scripts/host-setup.sh            # apply
sudo ./scripts/host-setup.sh --check    # report only, changes nothing
```

The script is safe to run repeatedly: it checks every item first and only
acts when something is missing. `--check` exits non-zero when anything is
outstanding, so it also works as a cron or monitoring probe. Both modes need
root — an unprivileged run cannot read `/etc/wireguard` and would report
configured items as missing.

It covers the persistent journal, Docker log rotation, the memory cgroup,
`fake-hwclock`, Wi-Fi power save and WireGuard autostart. It does **not**
create a WireGuard configuration — private keys belong on the host, never in
this repository; it only enables an existing one and warns when its
`AllowedIPs` would route the host's own local subnet through the tunnel.

Adding the memory cgroup edits the kernel command line and therefore needs a
reboot to take effect. The script backs up `cmdline.txt` first and validates
the result before writing it.

## Bring the stack up

```powershell
git clone https://github.com/theautomatist/whz-lora.git
cd whz-lora
Copy-Item .env.example .env
docker compose up -d --wait
```

There is no API key to create by hand: leave `CHIRPSTACK_API_KEY` at its
placeholder and the cockpit authenticates through the admin login, renewing
its token automatically. Setting a real key only saves the login round-trip.

When all seven services report `(healthy)` (~2 min on a cold pull,
seconds on a warm one), the management UI is at
[http://localhost:8080](http://localhost:8080).
Default login is `admin` / `admin`; you will be forced to change it
on first sign-in.

## Bring a gateway online

The first physical step is connecting a Kerlink Wirnet iFemtoCell
Evolution to your PC over USB and pointing its packet forwarder at
the stack.  Detailed procedure with every gotcha we encountered is at
**[Bringing a Kerlink Wirnet iFemtoCell Evolution online](kerlink-ifemtocell-bring-up.md)**.

## Connect an end device

Sensors are registered through the ChirpStack web UI:

1. Tenants → default tenant → Applications → *+ Add Application*.
2. Inside the application, Device Profiles → *+ Add* — pick `eu868`
   and the MAC version your device advertises (most factory devices
   are LoRaWAN 1.0.3, OTAA).
3. Devices → *+ Add* — enter the DevEUI, AppEUI and AppKey printed
   on the device label.
4. Power the device on, hold near the gateway, watch the *Live frames*
   tab — a join request followed by an uplink should appear within
   one or two minutes.

## Receive uplinks as MQTT

Once a device is sending, its decoded payloads land on the embedded
Mosquitto broker.  Example subscriber (Python, `paho-mqtt`):

```python
import paho.mqtt.client as mqtt
c = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2)
c.username_pw_set("testsubscriber", "testsubscriber")
c.on_message = lambda _c,_u,m: print(m.topic, m.payload.decode())
c.connect("localhost", 1883)
c.subscribe("application/+/device/+/event/up")
c.loop_forever()
```

The `testsubscriber` user is provisioned by `mosquitto/entrypoint.sh`
on stack-up; rotate its password in `.env` before any non-CI use.

## Verifying the install

The repository includes an end-to-end smoke test that exercises the
full pipeline without needing a real device — it provisions a virtual
gateway, injects a synthetic uplink, and confirms an MQTT event
arrives within 30 seconds.

```powershell
pip install -r scripts/requirements-test.txt
$env:MQTT_TEST_USERNAME = "testsubscriber"
$env:MQTT_TEST_PASSWORD = "testsubscriber"
$env:CHIRPSTACK_API_KEY = "change-me-api-key-from-chirpstack-ui"
python scripts/smoke_test.py
```

Last line should read `SUCCESS — end-to-end verification passed.`
