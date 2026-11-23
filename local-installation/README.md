# Installed Crestron component

This directory preserves the installed local variant of the legacy Crestron
component, captured on 23 November 2026. Its source is in
`custom_components/crestron/`. The files are copied unchanged from the active
installation in commit `7f97bfd`; `source-sha256.json` records those original
SHA-256 hashes. The current branch also includes the reliability update below.

The repository's root component remains unchanged. The current upstream revision
contains newer transport and shutdown fixes that are not all present in this
local variant. Keeping both versions makes the installation reproducible without
silently replacing those fixes. This is a source snapshot, not a merged release
or a recommendation to downgrade an existing installation.

## Connection and shutdown reliability update

The local variant now incorporates the root component's tested transport
lifecycle implementation from `f977b9b`. Only `crestron.py` and `__init__.py`
change in the installed component:

- A retired connection cannot mark a replacement connection unavailable.
- Subscriber exceptions are logged independently so other subscribers still run.
- Shutdown closes accepted clients, cancels their handlers and closes the listener.
- Writer closure has a five-second timeout followed by transport abort.
- Template and button listeners are detached at most once, and transport shutdown
  still runs if either listener cleanup raises.

The local guarded-write implementation and command encodings remain intact, as
do all custom entity platforms, join mappings and entity identities. This update
does not migrate to `crestron-ha` or claim to resolve the individual bathroom
entity's loading problem. Serial decoding follows upstream: invalid UTF-8 closes
the connection rather than silently discarding invalid bytes.

Validation: 25 tests passed against the root transport plus local hub cleanup;
another 18 transport tests passed against this updated local variant, including
a real localhost connection. Run the latter with:

```sh
CRESTRON_COMPONENT_ROOT="$PWD/local-installation" python3 -m unittest discover -s tests -p test_xsig.py -v
```

The original installed files remain recoverable from commit `7f97bfd`. The source
hash manifest describes that original snapshot, not the updated files. A Home
Assistant restart is required to load changed Python source; offline tests do not
verify the real Crestron processor's wiring or behavior.

Deployment verification on 23 November 2026: the two original modules were backed
up under `custom_components/crestron/backups/before-reliability-20261123-130218/`
before replacement. `ha core check` passed, Core restarted successfully, and an
established TCP connection was observed on the configured XSIG port 16384. The
reviewed startup logs showed no Crestron-specific errors beyond Home Assistant's
standard custom-integration warning. No physical device commands were issued.

## Differences from the root component

| Area | Installed behavior |
| --- | --- |
| Setup and join synchronization | YAML platforms load through Home Assistant. Template synchronization supports digital, analog and serial joins; configured `input_button` service calls pulse digital joins for 200 ms. Incoming digital falling edges are ignored for configured actions. |
| Lights | `type: brightness` uses analog `join`; `type: onoff` pulses a digital `join` for 50 ms. Brightness commands update the displayed state immediately and schedule a transition, defaulting to two seconds. Feedback refreshes the cached state. |
| Light identity | IDs are generated as `light-<join>` or `toggle-light-<join>`. YAML `unique_id` and `dimmer_join` are accepted as extra fields but are not read. The root component's `brightness_join` configuration is not interchangeable with this variant's `join`. |
| Buttons | New `button.py` platform uses `button_join` and sends a 200 ms digital pulse. |
| Covers | Supports `analog_shade`, `digital_shade`, `digital_curtain`, and `elevator`, with type-specific required join checks. The root component's `type: shade` is not accepted here. |
| Binary sensors | Supports optional `inverted` logic and validates device classes. |
| Sensors | Uses `SensorEntity`, native values and units, and an optional validated device class. |
| Switches | Pulsed switches send a 500 ms pulse only when feedback differs from the requested state. |
| Climate | Uses modern climate entities and enums with join-derived identity. |
| Media players | Provides pulsed power, mute and volume-step commands. `source_number_join` is used as a digital power-on pulse; there is no source-selection feature in this variant. It requires `off_join`, `volume_up_join` and `volume_down_join`, unlike the root configuration. |
| Transport | Combines the public reconnect, callback-isolation and shutdown fixes with local guarded socket writes. |

Most platforms filter feedback callbacks to the joins they use, plus changes in
connection availability. Join-derived unique IDs must remain distinct within each
platform. The installed manifest still reports version `0.2.3`; that value is
preserved as evidence and does not describe the current upstream release.

## Configuration examples for this variant

These use illustrative joins, not household configuration.

```yaml
crestron:
  port: 16384

light:
  - platform: crestron
    name: "Example dimmer"
    join: 50
    type: brightness
  - platform: crestron
    name: "Example toggle light"
    join: 51
    type: onoff

button:
  - platform: crestron
    name: "Example scene"
    button_join: 100
```

Use the schemas in each snapshot module for the remaining platform options.
Changing variants may change configuration requirements and entity identities.
The snapshot does not include the root's service-description file, because the
installed component does not register those services.

## Investigation and authorship

The earlier bathroom-light investigation inspected configuration, the entity
registry, component source and logs. It made no changes to the running
configuration or source and did not resolve the unavailable entity. In this
variant, availability comes from the shared hub; missing analog feedback defaults
to zero rather than independently making a single light unavailable.

The code differences above describe the installed files. Their individual authors
and modification dates were not established. The work performed for this import
was comparison, preservation, documentation and static validation; it does not
claim authorship of the pre-existing installed changes.

## Validation and limits

- Parsed every snapshot Python module and its JSON manifest successfully.
- Checked snapshot bytes against the captured source hashes and the mounted files.
- Checked relative constant imports against the snapshot's `const.py`.
- The 21 existing root-component tests passed. They exercise the root component,
  not this snapshot; they do not establish runtime compatibility of the variant.
- The original import performed no live restart or hardware commands. The later
  reliability update is covered by the transport and cleanup tests above.

Only active component source and the component manifest are included. Home
Assistant credentials, configuration, entity registries, databases, logs, cached
bytecode, ZIP archives and alternate backup modules are excluded.
