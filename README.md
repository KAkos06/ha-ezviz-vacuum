# EZVIZ Vacuum for Home Assistant

This integration lets you monitor and control verified functions of a supported
EZVIZ robot vacuum in Home Assistant.

After installation, you can see:

- the current activity of the robot vacuum;
- battery level;
- charging and online status;
- the current cleaning task;
- the configured fan speed and water level;
- controls for fan speed, water level, cleaning passes, and automatic carpet boost;
- controls to start, pause, resume, and stop cleaning;
- remaining values reported for the brushes, HEPA filter, mop, and sensors;

## Supported device

The first targeted model is:

- **EZVIZ RE5 Plus**
- device type: `CS-RE5P-TWT`
- device category: `SweepingRobot`
- device subcategory: `RE5P`

Other EZVIZ robot vacuums may appear if they use the same data structure, but
their compatibility has not yet been confirmed.

## Requirements

- a working Home Assistant installation;
- [HACS](https://hacs.xyz/) installed in Home Assistant;
- an internet connection;
- the EZVIZ account to which the robot vacuum is assigned.

This integration uses the EZVIZ cloud service. It cannot update the vacuum
status without an internet connection.

## Installation with HACS

The integration is currently available as a HACS custom repository.

1. Open **HACS** in Home Assistant.
2. Select **Integrations**.
3. Open the three-dot menu in the top-right corner.
4. Select **Custom repositories**.
5. Enter the following repository URL:

   ```text
   https://github.com/KAkos06/ha-ezviz-vacuum
   ```

6. Select **Integration** as the repository type.
7. Click **Add**.
8. Find **EZVIZ Vacuum** in HACS and install it.
9. Restart Home Assistant after the installation.

## Configuration

After restarting Home Assistant:

1. Open **Settings → Devices & services**.
2. Click **Add integration**.
3. Search for **EZVIZ Vacuum**.
4. Enter your EZVIZ account details:

   - **Email address:** the account used in the EZVIZ mobile app;
   - **Password:** your EZVIZ account password;
   - **Region:** use `eu` for Hungary and most European accounts.

5. After a successful login, the integration automatically searches the
   account for supported robot vacuums.

Each discovered robot vacuum is added to Home Assistant as a separate device.

## Entities

Depending on the data reported by your vacuum, the integration creates the
following entities.

### Robot vacuum

- current activity, such as idle, cleaning, paused, returning, or docked;
- availability;
- current fan speed and fan-speed control;
- start, pause and resume controls;
- one stop-icon control that ends cleaning and returns to the dock;
- reported error state.

### Controls

- suction power: silent, normal, high power, or super strong;
- water quantity: no mopping, low, medium, or high;
- cleaning passes: 1× or 2×;
- automatic carpet boost: on or off.

Suction power, water quantity, and cleaning passes use the mobile app's dedicated
actions for the map currently in use. Each action changes only its own setting.

### Sensors

- battery level;
- current task state;
- fan speed;
- water level;
- live task phase (including relocation and pause);
- current task duration in seconds;
- HEPA filter remaining value;
- main brush remaining value;
- side brush remaining value;
- mop remaining value;
- sensor cleaning remaining value;

### Binary sensors

- charging;
- online status;
- carpet turbo mode;
- rest mode.
- on base station;
- picked up;
- device-reported do not disturb mode.

> [!NOTE]
> The captured device API schema documents accessory and sensor-cleaning
> counters in hours. Remaining values use `rest`; `used` and `total_hours`
> attributes provide the used time and the sum of the reported counters.

### Volume, area units and accessory resets

- Prompt volume is a 0–100% slider with integer steps, including mute at 0.
- The area display preference supports `m2`, `sq.ft`, and `ping`.
- Separate reset buttons are provided for the main brush, HEPA filter, side
  brush and mop. A reset changes the robot's lifetime counter; use it after
  replacing the corresponding accessory.
- The "Body cleaned" button acknowledges manual body/sensor cleaning and
  resets its maintenance counter using the device schema's `sensor` type.
  It does not run a physical cleaning operation. Used and remaining sensor
  cleaning time are exposed as separate sensors in hours.

These controls match captured mobile-app requests. A successful command
invalidates the settings cache and triggers readback. The area display
preference changes the EZVIZ app's preference; this integration does not
display cleaning area, maps, room locations or robot paths.

## How quickly are states updated?

The integration queries `SweeperTaskMgr/QueryCurrentTask` and the current
standard cleaning settings on a 3-second polling interval while cleaning,
paused, or returning. At other times the interval is 15 seconds. Network latency
adds to these intervals; this is cloud polling, not instantaneous push updates.
Battery, general device metadata, volume, area preference, carpet boost and
accessory counters are refreshed every 30 seconds. The extra cloud requests
can add latency to a refresh, and commands share the same authenticated session.

After a successful suction, water or cleaning-pass command, its acknowledged
value appears immediately. Stale readbacks are suppressed for up to 15 seconds
while polling every 3 seconds for confirmation. Confirmation, a map change,
device unavailability or an error ends this grace period; if it expires, the
observed cloud value takes precedence. Failed commands never publish a new value.

The live response's nested task status distinguishes pause from cleaning and
returning from charging. Successful Home Assistant commands appear immediately,
but can override the observed state for at most a 6-second transition period.
The stopping label is retained while the live response confirms a return to the
dock. A failed live query makes that vacuum unavailable instead of presenting
cached online data as current.

Changing the configured 1×/2× cleaning-pass setting during cleaning does not
necessarily change the current task. Task duration is the robot's reported
phase duration, which can reset after relocation.

The standard vacuum controls expose one stop-icon button for returning to the
dock. It invokes the same command as the previous return-home control. Automatic
dust emptying remains device-controlled; this integration does not send an
additional emptying command.

Map names, cleaned area and running-pass counters are not exposed or included
in integration diagnostics. Their old entity registry entries are removed on
upgrade. The active map identifier is retained internally only to target settings
correctly; the integration does not request map images or robot paths.

Pause and stop remain visible but disabled for 5 seconds after starting. While the robot is
stopping, all adjustable controls remain locked until it docks. Changes made in
the EZVIZ app or with the robot's physical controls are still detected by the
active 3-second polling and update the available Home Assistant controls.

The RE5 Plus did not send usable EZVIZ cloud MQTT notifications during
controlled testing, so the integration intentionally uses polling only. You do
not need an MQTT broker or a Mosquitto installation.

## Manual installation

1. Download the contents of this repository.
2. Copy the `custom_components/ezviz_vacuum` directory into the
   `custom_components` directory inside your Home Assistant configuration.
3. Restart Home Assistant.
4. Add **EZVIZ Vacuum** from **Settings → Devices & services**.

The resulting directory structure should look like this:

```text
config/
└── custom_components/
    └── ezviz_vacuum/
        ├── __init__.py
        ├── manifest.json
        └── ...
```

## Troubleshooting

Check the following if configuration fails:

- verify that the same email address and password work in the EZVIZ mobile app;
- make sure the robot vacuum is visible and online in the EZVIZ app;
- use `eu` as the region for a European account;
- restart Home Assistant after installing the integration through HACS;
- make sure the same EZVIZ account has not already been added.

To enable detailed logging, add the following to your Home Assistant
`configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.ezviz_vacuum: debug
```

Restart Home Assistant after changing the logging configuration.

When reporting a problem, include:

- Home Assistant version;
- integration version;
- exact robot vacuum model and firmware version;
- selected region;
- downloaded and redacted integration diagnostics;
- relevant debug log lines.

Never publish your password, token file, full serial number, authentication
code, or a complete raw API response.

## Current limitations

- An internet connection is required.
- The integration relies on a private, undocumented EZVIZ cloud API.
- A future EZVIZ API change may temporarily break the integration.
- EZVIZ may temporarily limit an account after too many requests.
- Login flows requiring multi-factor authentication are not currently
  supported.

## Privacy

Your EZVIZ credentials are stored in the Home Assistant configuration entry.
Protect your Home Assistant configuration directory and backups accordingly.

Integration diagnostics redact credentials, tokens, session identifiers,
serial numbers, network addresses, and secret keys.

## Legal notice

This project is an unofficial community integration and is not affiliated with,
endorsed by, or supported by EZVIZ.
