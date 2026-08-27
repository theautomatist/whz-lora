#!/bin/sh
# Keep the WireGuard tunnel on whichever endpoint port is actually alive.
#
# Why this exists: the field host travels. The VPN server's port is being
# changed while the host is already off-site, so at some point one port
# stops answering and another starts. A host that is only configured for
# one of them is unreachable in exactly the window where remote access
# matters most — and nobody is standing next to it to fix that.
#
# It flips the peer's endpoint with `wg set` rather than restarting
# wg-quick: the interface, its address and its routes stay up, so nothing
# else on the host notices. A restart would tear the tunnel down even when
# the current port was fine.
#
# Deliberately dumb: no state file, no history. The only input is the
# handshake age reported by the kernel, which is the one fact that cannot
# lie about whether the tunnel works.
#
# On the fallback port: UDP 443 rather than a high one. Two reasons. It sits
# outside the ephemeral range (32768-60999 here), so the server's kernel
# cannot hand it out as an outgoing source port and break the listener's
# bind. And it is where QUIC lives, so a campus network that permits modern
# web traffic permits this too — which matters, because the host spends its
# working life on eduroam, where high UDP ports are the first thing dropped.
set -eu

IFACE="${WG_IFACE:-PI5}"
HOST="${WG_HOST:-vpn2go.kuhligk.de}"
PORT_A="${WG_PORT_A:-51820}"
PORT_B="${WG_PORT_B:-443}"
# WireGuard rehandshakes about every 2 minutes when traffic flows, and
# PersistentKeepalive is 25 s here. Three minutes without one means the
# path is genuinely gone, not merely quiet.
STALE_AFTER="${WG_STALE_AFTER:-180}"

log() { logger -t wg-failover -p daemon.info "$*"; echo "$*"; }

# The interface being absent is a different failure from a dead endpoint —
# flipping a port on a down interface would achieve nothing.
if ! wg show "$IFACE" >/dev/null 2>&1; then
    log "$IFACE is down — asking systemd to bring it back"
    systemctl restart "wg-quick@$IFACE" || log "restart of wg-quick@$IFACE failed"
    exit 0
fi

peer="$(wg show "$IFACE" peers | head -1)"
if [ -z "$peer" ]; then
    log "$IFACE has no peer configured — nothing to fail over"
    exit 0
fi

last="$(wg show "$IFACE" latest-handshakes | awk -v p="$peer" '$1==p {print $2}')"
[ -n "${last:-}" ] || last=0

now="$(date +%s)"
if [ "$last" -gt 0 ]; then
    age=$(( now - last ))
else
    # Never handshaked since the interface came up. Give it one full
    # window before declaring the port dead, otherwise every start would
    # flip immediately.
    age="$STALE_AFTER"
fi

if [ "$age" -lt "$STALE_AFTER" ]; then
    exit 0
fi

current="$(wg show "$IFACE" endpoints | awk -v p="$peer" '$1==p {print $2}')"
current_port="${current##*:}"

case "$current_port" in
    "$PORT_A") next="$PORT_B" ;;
    "$PORT_B") next="$PORT_A" ;;
    # Unknown or unset (DNS failed at start-up, say) — take the primary.
    *)         next="$PORT_A" ;;
esac

log "no handshake for ${age}s on port ${current_port:-unknown} — trying $HOST:$next"
if wg set "$IFACE" peer "$peer" endpoint "$HOST:$next"; then
    log "endpoint set to $HOST:$next"
else
    # Almost always DNS: off-site the host may come up before name
    # resolution does. Failing loudly here is better than looking healthy.
    log "could not set endpoint to $HOST:$next (name resolution?)"
fi
