# Runbook — rebuilding the field Pi from bare metal

Everything needed to take a blank Raspberry Pi 5 to a running field host
with the Kerlink gateway attached. The reasoning behind the split between
host and container lives in
[ADR-0019](../decisions/adr-0019.md); this page is only the sequence.

The short version: **run `scripts/host-setup.sh`, then bring the stack up.**
The script is idempotent and has a `--check` mode, so it is also the way to
audit a host you did not build yourself.

## What is host configuration and what is not

Three layers cannot live in a container, and knowing which is which saves
hours of looking in the wrong place:

| Layer | Example | Why not a container |
|---|---|---|
| Firmware | `usb_max_current_enable=1` | read by the bootloader, before Docker exists |
| Kernel | `cdc_eem` creating `usb0` | a container cannot create an interface the kernel has not |
| Host network | the `kerlink-usb` profile, WireGuard | addresses and routes belong to the host's stack |

Everything above that — ChirpStack, both gateway bridges, Mosquitto,
PostgreSQL, Redis and the cockpit — is in `docker-compose.yml` and runs
unprivileged. There is **no** `privileged`, `devices:`, `cap_add` or
`network_mode: host` anywhere, and none is needed: the gateway is a USB
*Ethernet* gadget, not a serial device, so there is nothing to pass
through.

## 1. Operating system

Raspberry Pi OS (Debian 13 trixie, arm64). Set the hostname, enable SSH,
install your key.

## 2. Docker

Install Docker Engine and the Compose plugin from Docker's own repository —
not the Debian packages, which lag. Add your user to the `docker` group and
log out and in once.

## 3. Clone and configure

```bash
git clone <repo> ~/whz-lora
cd ~/whz-lora
cp .env.example .env
```

Fill in `.env`. At minimum change `CHIRPSTACK_API_SECRET` (generate with
`openssl rand -base64 32`) and `COCKPIT_PASSWORD`. The file is gitignored
and must stay that way — it holds the only copy of those secrets.

## 4. Host configuration

```bash
sudo ./scripts/host-setup.sh          # apply
sudo ./scripts/host-setup.sh --check  # audit, changes nothing
```

Eight steps, each idempotent and each reporting `ok`, `set` or `miss`:

1. **Persistent journal** — Raspberry Pi OS ships `Storage=volatile`, so
   every reboot wipes the log and a crash can never be investigated
   afterwards.
2. **Docker log rotation** — an uncapped container log fills the SD card.
3. **Memory cgroup** — needed for `mem_limit` in the compose file to mean
   anything. Requires a reboot.
4. **Clock across reboots** — `fake-hwclock`. A mitigation, not a fix: fit
   an RTC battery (~5 EUR) if the timestamps matter, which for a
   measurement campaign they do.
5. **Wi-Fi power save** — off, or the host disappears from the network
   between packets.
6. **WireGuard autostart** — enables an existing config; it never creates
   one, because that would put a private key in the repository.
7. **Kerlink USB link** — the `kerlink-usb` NetworkManager profile.
8. **Firmware settings** — the two `config.txt` lines. Requires a reboot.

Steps 7 and 8 are the ones without which no byte arrives; see below.

## 5. Reboot, then start the stack

```bash
sudo reboot
# after it comes back:
cd ~/whz-lora && docker compose up -d --wait
```

`--wait` returns only when every healthcheck passes, so a silent failure
cannot masquerade as success.

## 6. Verify the path, hop by hop

Do not stop at "the containers are up". The chain has five hops and each
can fail on its own:

```bash
# 1. gateway -> Pi: UDP both ways on usb0, roughly every 10 s
sudo timeout 30 tcpdump -ni usb0 -c 4 'udp port 1700'

# 2. host -> container: docker-proxy holds the port
sudo ss -ulnp | grep 1700

# 3. bridge -> MQTT: stats events being published
docker logs --since 3m whz-lora-chirpstack-gateway-bridge-1 | grep 'publishing event'

# 4. MQTT: see the traffic itself
set -a; . ./.env; set +a
docker exec whz-lora-mosquitto-1 timeout 30 \
  mosquitto_sub -h 127.0.0.1 -u "$MQTT_TEST_USERNAME" -P "$MQTT_TEST_PASSWORD" -t '#' -v -C 2

# 5. cockpit ingest is subscribed
docker logs whz-lora-cockpit-1 | grep -i 'MQTT subscribed'
```

Then open the cockpit on port 8000 and ChirpStack on 8080.

## The two settings that decide whether anything works

Worth knowing by heart, because when they are wrong everything *looks*
fine — interfaces up, containers healthy, no error anywhere.

**The link-local route.** The gateway sends from `169.254.x.x`, not from
`192.168.120.x`:

```
169.254.82.2.38343 > 192.168.120.31.1700
```

So `usb0` needs `192.168.120.31/24` **and** a route for `169.254.0.0/16`.
Without the route the return path is dead.

**`never-default: yes`.** A point-to-point USB link that claims the default
route takes the host off the internet. Same failure class as a WireGuard
peer whose `AllowedIPs` covers the LAN it is sitting on — a trap this host
has already fallen into once.

Both are set by step 7 and checked by `--check`.

## When the gateway browns out

Symptom: the link drops under load, or `usb0` disappears and returns. The
Pi 5 caps total USB current at 600 mA unless `usb_max_current_enable=1` is
set, and that setting needs a supply that can actually deliver it — use a
27 W unit or better. A QC 27 W charger works but still logs the occasional
under-voltage warning.

## Restoring measurement data

`cockpit-data/` is a bind mount holding `cockpit.db`, the photos, the floor
plans and every run CSV. It is gitignored and is **not** part of a rebuild
— restore it from a backup if the campaign is meant to continue.

Take the database with SQLite's online backup rather than copying the file,
which would catch a torn state with an open WAL:

```bash
docker exec whz-lora-cockpit-1 python3 -c \
  "import sqlite3;s=sqlite3.connect('/data/cockpit.db');d=sqlite3.connect('/data/backup.db');s.backup(d);d.close();s.close()"
```

Then archive `cockpit-data/` as a whole. After restoring, reconcile the
`photo` rows against the files on disk — the two have drifted apart before.
