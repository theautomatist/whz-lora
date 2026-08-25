# CAD — printed parts for the field-test rig

3D-printable mounts used to build the portable measurement rig for the
LoRaWAN field test (Studien-Phase 4). They are what makes the physical setup
reproducible: without them a repeat campaign cannot recreate the same antenna
height, orientation and gateway placement.

| File | Part | Used for |
|---|---|---|
| `Antenna ARCA Swiss Mount.STL` | Antenna holder with an ARCA-Swiss dovetail | Clamps the LoRa antenna onto any ARCA-Swiss tripod head, so antenna height and orientation are repeatable between measurement points. |
| `Gateway TriPod Mount.STL` | Cradle for the Kerlink iFemtoCell Evolution | Mounts the gateway on the tripod next to the antenna, keeping the RF cable run short and constant. |
| `PI5 TriPod Mount.STL` | Cradle for the Raspberry Pi 5 | Carries the host running the ChirpStack stack on the same tripod, so the whole rig moves as one unit.

Print notes: PLA is sufficient — the parts are not load-bearing beyond the
weight of the device itself and are used indoors. Print the tripod mounts with
the mounting plate flat on the bed so the screw boss is not a bridged overhang.

The rig these parts belong to is described in
`docs/developer/analysis/test-concept.typ` (and its rendered PDF).
