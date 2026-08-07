#!/usr/bin/env bash
#
# host-setup.sh — one-time preparation of a Debian/Raspberry Pi OS host for
# the whz-lora field stack.
#
# Every step here fixes a defect that actually took the field host down; see
# docs/developer/analysis/pi-field-diagnosis-2026-08-01.md for the evidence.
# Docker Compose brings the stack up, but none of this is stack
# configuration — it is host configuration, and without it the stack runs on
# a host that loses its logs on every reboot, cannot enforce memory limits,
# and fills its SD card with unrotated container logs.
#
# Safe to run repeatedly: every step checks first and only acts when needed.
#
# Usage:
#   sudo ./scripts/host-setup.sh            apply the configuration
#   sudo ./scripts/host-setup.sh --check    report only, change nothing
#   ./scripts/host-setup.sh --help
#
# Both modes need root: /etc/wireguard is root-only, and journalctl and nmcli
# return nothing useful to an unprivileged caller, so an unprivileged check
# would report configured items as missing.
#
# --check exits non-zero when something is missing, so it works in a cron job
# or a monitoring probe.

set -euo pipefail

CHECK_ONLY=0
NEED_REBOOT=0
MISSING=0
CHANGED=0
STAMP="$(date +%Y-%m-%d)"

# --- output helpers --------------------------------------------------------

if [ -t 1 ]; then
    C_OK=$'\033[32m'; C_WARN=$'\033[33m'; C_ERR=$'\033[31m'
    C_HEAD=$'\033[1m'; C_OFF=$'\033[0m'
else
    C_OK=''; C_WARN=''; C_ERR=''; C_HEAD=''; C_OFF=''
fi

head_line() { printf '\n%s%s%s\n' "$C_HEAD" "$1" "$C_OFF"; }
ok()        { printf '  %s[ ok ]%s %s\n'   "$C_OK"   "$C_OFF" "$1"; }
changed()   { printf '  %s[ set ]%s %s\n'  "$C_OK"   "$C_OFF" "$1"; CHANGED=$((CHANGED+1)); }
missing()   { printf '  %s[miss]%s %s\n'   "$C_WARN" "$C_OFF" "$1"; MISSING=$((MISSING+1)); }
warn()      { printf '  %s[note]%s %s\n'   "$C_WARN" "$C_OFF" "$1"; }
fail()      { printf '  %s[fail]%s %s\n'   "$C_ERR"  "$C_OFF" "$1"; }

usage() {
    sed -n '3,25p' "$0" | sed 's/^# \{0,1\}//'
    exit 0
}

# --- argument parsing ------------------------------------------------------

for arg in "$@"; do
    case "$arg" in
        --check) CHECK_ONLY=1 ;;
        --help|-h) usage ;;
        *) echo "Unknown option: $arg (try --help)" >&2; exit 2 ;;
    esac
done

# Both modes need root — and --check just as much as the apply run.
# /etc/wireguard is root-only, and journalctl and nmcli quietly return
# nothing useful to an unprivileged caller, so an unprivileged check reports
# items as missing that are in fact configured. A check that lies is worse
# than no check.
if [ "$(id -u)" -ne 0 ]; then
    echo "This script needs root — including --check, which would otherwise" >&2
    echo "report false negatives for WireGuard, the journal and Wi-Fi." >&2
    echo "Use: sudo $0 $*" >&2
    exit 2
fi

# Run a mutating command unless --check is active.
apply() {
    [ "$CHECK_ONLY" -eq 1 ] && return 1
    return 0
}

# =========================================================================
# 1. Persistent journal
#    Raspberry Pi OS ships /usr/lib/systemd/journald.conf.d/
#    40-rpi-volatile-storage.conf with Storage=volatile, which silently
#    overrides Storage= in journald.conf. Consequence: every reboot wipes the
#    system log, so a crash can never be investigated afterwards. A drop-in
#    numbered above 40 wins. Size-capped to spare the SD card.
# =========================================================================

step_journal() {
    head_line "1. Persistent journal (finding B-9)"
    local dropin=/etc/systemd/journald.conf.d/99-whz-persistent.conf

    if [ -f "$dropin" ] && grep -q '^Storage=persistent' "$dropin"; then
        ok "drop-in present: $dropin"
    elif apply; then
        mkdir -p /etc/systemd/journald.conf.d /var/log/journal
        cat > "$dropin" <<'CONF'
# whz-lora: logs must survive a reboot, otherwise a crash cannot be
# investigated after the fact (finding B-9 of the 2026-08-01 field
# diagnosis). Overrides the Raspberry Pi OS default
# /usr/lib/systemd/journald.conf.d/40-rpi-volatile-storage.conf, which sets
# Storage=volatile. Size-capped to spare the SD card.
[Journal]
Storage=persistent
SystemMaxUse=200M
SystemMaxFileSize=20M
CONF
        systemd-tmpfiles --create --prefix /var/log/journal >/dev/null 2>&1 || true
        systemctl restart systemd-journald
        # The first switch from runtime to persistent storage needs an
        # explicit flush; on later boots systemd-journal-flush does it.
        systemctl start systemd-journal-flush.service >/dev/null 2>&1 || true
        killall -USR1 systemd-journald >/dev/null 2>&1 || true
        changed "journal switched to persistent (max 200 MB)"
    else
        missing "journal is volatile — logs are lost on every reboot"
    fi

    # Check for journal files on disk rather than piping journalctl into
    # grep -q: grep exits early, journalctl takes SIGPIPE, and under
    # `set -o pipefail` the whole test would report a failure that is not one.
    if [ -n "$(find /var/log/journal -name '*.journal' -print -quit 2>/dev/null)" ]; then
        ok "journal files present under /var/log/journal"
    elif [ "$CHECK_ONLY" -eq 1 ]; then
        missing "journal not yet writing to /var/log/journal"
    fi
}

# =========================================================================
# 2. Docker log rotation
#    The default json-file driver has no size limit. On the field host that
#    produced 639 MB of container logs in three weeks (ChirpStack alone
#    322 MB) — SD-card wear, and docker logs became unusable once the files
#    were damaged by hard resets.
#    Note: log-opts only apply to newly created containers, so an existing
#    stack needs `docker compose up -d --force-recreate` afterwards.
# =========================================================================

step_docker_logs() {
    head_line "2. Docker log rotation (finding B-5)"
    local cfg=/etc/docker/daemon.json

    if [ -f "$cfg" ] && grep -q '"max-size"' "$cfg"; then
        ok "daemon.json already caps the log size"
        return
    fi

    if ! apply; then
        missing "no log rotation — container logs grow without bound"
        return
    fi

    if [ -f "$cfg" ]; then
        # Do not clobber an existing daemon.json we did not write.
        cp -n "$cfg" "$cfg.bak-$STAMP"
        warn "existing $cfg found (backup: $cfg.bak-$STAMP) — please merge log-opts manually:"
        warn '  "log-driver": "json-file", "log-opts": {"max-size":"10m","max-file":"3"}'
        MISSING=$((MISSING+1))
        return
    fi

    mkdir -p /etc/docker
    cat > "$cfg" <<'CONF'
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
CONF
    if command -v dockerd >/dev/null 2>&1 && ! dockerd --validate --config-file "$cfg" >/dev/null 2>&1; then
        fail "daemon.json failed validation — reverting"
        rm -f "$cfg"
        MISSING=$((MISSING+1))
        return
    fi
    systemctl restart docker >/dev/null 2>&1 || true
    changed "log rotation set (10 MB x 3 per container)"
    warn "existing containers keep their old setting until:"
    warn "  docker compose up -d --force-recreate"
}

# =========================================================================
# 3. Memory cgroup
#    The Raspberry Pi device tree passes cgroup_disable=memory in its
#    bootargs. Without the memory controller Docker cannot enforce memory
#    limits and docker stats reports 0B — so a leaking container takes down
#    the whole host instead of just itself, and nothing is measurable
#    afterwards. cmdline.txt is read after the device tree bootargs, so the
#    later cgroup_enable wins.
#
#    cmdline.txt must stay a single line; a broken one makes the host
#    unbootable. Hence: back up, build in a temp file, validate, then move.
# =========================================================================

step_cgroup() {
    head_line "3. Memory cgroup (finding B-6)"

    if grep -qw memory /sys/fs/cgroup/cgroup.controllers 2>/dev/null; then
        ok "memory controller active"
        return
    fi

    local cmdline=/boot/firmware/cmdline.txt
    [ -f "$cmdline" ] || cmdline=/boot/cmdline.txt
    if [ ! -f "$cmdline" ]; then
        warn "no cmdline.txt found — not a Raspberry Pi? skipping"
        return
    fi

    if grep -q 'cgroup_enable=memory' "$cmdline"; then
        ok "cgroup_enable already in $cmdline — active after next reboot"
        NEED_REBOOT=1
        return
    fi

    if ! apply; then
        missing "memory controller inactive — Docker cannot enforce mem_limit"
        return
    fi

    cp -n "$cmdline" "$cmdline.bak-$STAMP"
    local tmp; tmp="$(mktemp)"
    printf '%s cgroup_enable=memory cgroup_memory=1\n' "$(tr -d '\n' < "$cmdline")" > "$tmp"

    # Validate before touching the real file: exactly one line, root= intact.
    local lines; lines="$(grep -c '' "$tmp")"
    if [ "$lines" -ne 1 ] || ! grep -q 'root=' "$tmp"; then
        fail "generated cmdline failed validation — $cmdline left untouched"
        rm -f "$tmp"
        MISSING=$((MISSING+1))
        return
    fi

    cat "$tmp" > "$cmdline"
    rm -f "$tmp"
    sync
    changed "cgroup_enable=memory added (backup: $cmdline.bak-$STAMP)"
    NEED_REBOOT=1
}

# =========================================================================
# 4. fake-hwclock
#    The Pi 5 has an RTC but no buffered battery, so it boots at 1970 and
#    jumps forward once NTP answers. On the field host that jump was 23 h
#    21 min, which corrupted container timestamps and can retire a freshly
#    issued token on the spot.
#    This only mitigates: it restores the last known time so the jump stays
#    small. The real fix is a battery on the Pi 5 RTC header.
# =========================================================================

step_fake_hwclock() {
    head_line "4. Clock across reboots (finding B-4)"

    if dpkg -s fake-hwclock >/dev/null 2>&1; then
        ok "fake-hwclock installed"
    elif apply; then
        DEBIAN_FRONTEND=noninteractive apt-get install -y -q fake-hwclock >/dev/null 2>&1 \
            && changed "fake-hwclock installed" \
            || { fail "could not install fake-hwclock (no network?)"; MISSING=$((MISSING+1)); return; }
    else
        missing "fake-hwclock missing — clock starts at 1970 after a power cut"
        return
    fi

    apply && fake-hwclock save >/dev/null 2>&1 || true
    warn "mitigation only — fit an RTC battery on the Pi 5 for a real fix (~5 EUR)"
}

# =========================================================================
# 5. Wi-Fi power save
#    Power save makes the host answer late or not at all after idle periods —
#    a classic cause of "the Pi is unreachable again". Set on the
#    NetworkManager profile so it survives a reboot.
# =========================================================================

step_wifi_powersave() {
    head_line "5. Wi-Fi power save (finding B-10)"

    if ! command -v nmcli >/dev/null 2>&1; then
        warn "NetworkManager not present — skipping"
        return
    fi

    local profiles
    profiles="$(nmcli -t -f NAME,TYPE con show 2>/dev/null | awk -F: '$2 ~ /wireless/ {print $1}')" || true
    if [ -z "$profiles" ]; then
        ok "no Wi-Fi profiles configured"
        return
    fi

    while IFS= read -r p; do
        [ -z "$p" ] && continue
        local cur
        # nmcli -g prints the symbolic name ("disable"/"default"), not the
        # numeric value that `nmcli con modify` expects.
        cur="$(nmcli -g 802-11-wireless.powersave con show "$p" 2>/dev/null || echo '')"
        if [ "$cur" = "disable" ] || [ "$cur" = "2" ]; then
            ok "power save disabled: $p"
        elif apply; then
            nmcli con modify "$p" 802-11-wireless.powersave 2 >/dev/null 2>&1 \
                && changed "power save disabled: $p" \
                || warn "could not change profile: $p"
        else
            missing "power save still on: $p"
        fi
    done <<< "$profiles"
}

# =========================================================================
# 6. WireGuard
#    Not created here — the config holds private keys and belongs on the
#    host, never in the repository. This only enables an existing config for
#    autostart and warns about the trap the field host actually fell into:
#    AllowedIPs covering the very subnet the host already sits in routes the
#    local network (including the path to the VPN endpoint) into the tunnel.
# =========================================================================

step_wireguard() {
    head_line "6. WireGuard autostart (finding B-2)"

    local conf
    conf="$(find /etc/wireguard -maxdepth 1 -name '*.conf' 2>/dev/null | head -1)" || true
    if [ -z "${conf:-}" ]; then
        warn "no config under /etc/wireguard — nothing to enable"
        warn "(expected: /etc/wireguard/<name>.conf, then wg-quick@<name>)"
        return
    fi

    local name; name="$(basename "$conf" .conf)"

    # The unit name must match the config file name — a mismatch means the
    # service starts and finds nothing.
    if systemctl is-enabled "wg-quick@$name" >/dev/null 2>&1; then
        ok "wg-quick@$name enabled"
    elif apply; then
        systemctl enable "wg-quick@$name" >/dev/null 2>&1 \
            && changed "wg-quick@$name enabled for autostart" \
            || { fail "could not enable wg-quick@$name"; MISSING=$((MISSING+1)); }
    else
        missing "wg-quick@$name not enabled — no VPN access after a reboot"
    fi

    # Warn when AllowedIPs overlaps a directly connected subnet. The tunnel's
    # own interface carries a route for the VPN subnet, so exclude it —
    # otherwise every correct config would trigger this warning.
    local allowed local_nets
    allowed="$(grep -i '^\s*AllowedIPs' "$conf" | cut -d= -f2- | tr ',' '\n' | tr -d ' ')" || true
    local_nets="$(ip -o -4 route show scope link 2>/dev/null | awk -v wg="$name" '$3 != wg {print $1}')" || true
    while IFS= read -r net; do
        [ -z "$net" ] && continue
        if printf '%s\n' "$local_nets" | grep -qx "$net"; then
            warn "AllowedIPs contains $net, which is also a local subnet —"
            warn "  starting the tunnel would route the local network through it."
            warn "  Restrict AllowedIPs to the VPN subnet (e.g. 10.8.0.0/24)."
        fi
    done <<< "$allowed"

    if systemctl is-active "wg-quick@$name" >/dev/null 2>&1; then
        ok "tunnel is up ($(ip -br -4 addr show "$name" 2>/dev/null | awk '{print $3}'))"
    fi
}

# =========================================================================

main() {
    printf '%swhz-lora host setup%s — %s\n' "$C_HEAD" "$C_OFF" \
        "$([ "$CHECK_ONLY" -eq 1 ] && echo 'check only, nothing is changed' || echo 'applying configuration')"

    step_journal
    step_docker_logs
    step_cgroup
    step_fake_hwclock
    step_wifi_powersave
    step_wireguard

    head_line "Summary"
    if [ "$CHECK_ONLY" -eq 1 ]; then
        if [ "$MISSING" -eq 0 ]; then
            ok "host fully configured"
            exit 0
        fi
        printf '  %d item(s) missing — run: sudo %s\n' "$MISSING" "$0"
        exit 1
    fi

    printf '  %d change(s) applied, %d item(s) need attention\n' "$CHANGED" "$MISSING"
    if [ "$NEED_REBOOT" -eq 1 ]; then
        printf '\n  %sA reboot is required for the memory cgroup to take effect.%s\n' "$C_WARN" "$C_OFF"
        printf '  Afterwards verify with: %s --check\n' "$0"
    fi
    [ "$MISSING" -eq 0 ] || exit 1
}

main
