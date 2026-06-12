# FAQ

## My gateway shows "offline" although it is powered and forwarding

Almost always the gateway's **stats interval** is misconfigured. ChirpStack marks a
gateway offline when it has not received a stats message within the configured
interval. If that interval is set very low (e.g. 1 s) but the gateway only reports
every 30 s, the gateway shows offline permanently even though it works perfectly.

**Fix:** ChirpStack UI → *Gateways* → your gateway → *Configuration* → set
**Stats interval (secs)** to match the gateway (typically **30**) → *Update gateway*.

## A device does not show up / the log says "Unknown device"

The DevEUI the device actually transmits does not match any registered device.
DevEUIs are long hex strings and easy to mistype. A device broadcasts its DevEUI in
the clear, so the ChirpStack log shows the **real** value — register exactly that.

## A device sends a join but fails with "Invalid MIC"

The **AppKey is wrong** — even if the DevEUI is correct. The join's integrity check
(MIC) is computed with the AppKey; a mismatch means ChirpStack cannot validate the
join. There is no bypass: the AppKey stored in ChirpStack must be **identical** to
the one in the device. The AppKey is a secret — it is **never** printed on the label
or encoded in the QR code (LoRa Alliance TR005); it is delivered separately by the
vendor (CSV / e-mail) or written via the device's own configuration tool.

## A device stays ⚪ "Provisioned" on the dashboard

It is registered but has not joined yet. A device only joins when it is powered, in
range of an **online** gateway, and its keys match. Trigger a join by power-cycling
the device or pressing its reset / join button. Battery (Class A) devices join
within seconds (🟡 Joined) and send their first data uplink at their next reporting
interval — often minutes later (🟢 Online).

## An MQTT subscriber is refused

Anonymous connections are disabled. Connect with the credentials from
`mosquitto/passwd`, generated from the `MQTT_TEST_*` / `CHIRPSTACK_MQTT_*` values in
`.env`. To rotate them, change `.env` and restart the mosquitto container.

## How do I enrol many devices at once?

Use the provisioning app's CSV bulk import — one row per device. See
[Provisioning actuators](provisioning-actuators.md).
