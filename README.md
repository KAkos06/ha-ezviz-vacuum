# EZVIZ Vacuum for Home Assistant

Monitor and control your EZVIZ robot vacuum from Home Assistant through the
EZVIZ cloud service. The integration uses API polling, not MQTT.

Supported device: **EZVIZ RE5 Plus** (`CS-RE5P-TWT`).

## Features

- Start, pause and resume cleaning.
- Stop cleaning and return to the dock with the square stop button.
- Adjust suction power, water quantity and the number of cleaning passes.
- Enable automatic carpet boost and adjust prompt volume.
- Monitor activity, battery, charging, connectivity and rest periods.
- Track accessory lifetime and body-cleaning maintenance counters.
- Reset maintenance counters after replacing accessories or cleaning the body.

## Requirements

- Home Assistant with an internet connection.
- An EZVIZ account with the robot vacuum assigned to it.
- [HACS](https://hacs.xyz/) for installation through a custom repository,
  or access to the Home Assistant configuration directory for manual installation.

## Installation with HACS

1. Open **HACS**, then the three-dot menu and **Custom repositories**.
2. Add `https://github.com/KAkos06/ha-ezviz-vacuum` with the type **Integration**.
3. Find **EZVIZ Vacuum** in HACS and download it.
4. Restart Home Assistant.
5. Follow the configuration steps below.

## Manual installation

1. Download the contents of this repository.
2. Copy `custom_components/ezviz_vacuum` into the `custom_components` directory
   inside your Home Assistant configuration directory.
3. Restart Home Assistant.
4. Follow the configuration steps below.

## Configuration

1. Open **Settings → Devices & services → Add integration**.
2. Search for **EZVIZ Vacuum**.
3. Enter the email address and password used in the EZVIZ mobile app.
4. Select the account region. Use `eu` for Hungary and European accounts.

The integration discovers supported robot vacuums in the account and adds each
as a separate Home Assistant device. Account region can be changed in the
integration's options.

## Controls

| Control | Values or behavior |
| --- | --- |
| Start | Starts cleaning; resumes a paused task. |
| Pause | Pauses the current cleaning task. |
| Stop | Ends cleaning and returns to the dock, using the square stop icon. |
| Suction power | Silent, normal, high power or super strong. |
| Water quantity | No mopping, low, medium or high. |
| Cleaning passes | 1× or 2×. |
| Automatic carpet boost | On or off. |
| Prompt volume | 0–100% in steps of 1%; 0 mutes prompts. |
| Area display unit | m², ft² or ping for the EZVIZ app's area display. |

After the device acknowledges a suction, water or cleaning-pass change, the
selected value appears immediately and is confirmed by subsequent cloud updates.
The cleaning-pass setting configures standard cleaning; its effect on a task
already in progress depends on the robot.

Pause and stop are temporarily disabled for five seconds after cleaning starts.
After a stop command, adjustable settings remain locked while the robot returns
to the dock. Automatic dust emptying follows the robot's settings.

## Status and sensors

The vacuum entity shows activity, availability, fan speed and reported errors.
Activity includes idle, cleaning, paused, stopping, returning and docked.

Additional sensors expose:

- Battery percentage.
- Task state and task phase, including relocation, pause and return to dock.
- Task duration in seconds, as reported for the current phase.
- Current suction power and water quantity.
- Rest-period start and end times.
- Remaining maintenance time for the HEPA filter, main brush, side brush and mop.
- Remaining body-cleaning time and time used since body cleaning.

Task duration can restart when the robot enters another phase, such as relocation.

Binary sensors show:

- Online and charging status.
- Whether the robot is on the base station or has been picked up.
- Automatic carpet boost enabled.
- Rest period enabled and whether the configured period is currently active.
- Device-reported do not disturb mode.

## Maintenance counters

Maintenance times are reported in **hours**. Counter attributes include used
time and `total_hours`, the sum of the reported used and remaining time.

Use the separate **Reset main brush lifetime**, **Reset HEPA lifetime**,
**Reset side brush lifetime** and **Reset mop lifetime** buttons after replacing
the corresponding accessory.

After manually cleaning the robot body and sensors, press **Body cleaned** to
restart that maintenance counter. The body-cleaning sensors show the elapsed
time since cleaning and the remaining maintenance time.

## Update intervals

The integration uses scheduled requests to the EZVIZ cloud API (**polling,
not MQTT**).

| Data | Refresh interval |
| --- | --- |
| Task state, task phase, task duration and standard cleaning settings while cleaning, paused, stopping or returning | 3 seconds |
| Task data and standard cleaning settings while idle or docked | 15 seconds |
| Battery, general device information, prompt volume, area display unit, carpet boost and maintenance counters | 30 seconds |

These are polling intervals. Cloud response time and additional requests can
lengthen the time between visible updates. Changes made in the EZVIZ app or
with the robot's physical controls appear through these cloud updates.
Polling also runs every three seconds while confirming a control change.

## Troubleshooting

If configuration fails, check that the account details work in the EZVIZ mobile
app, the robot is visible and online, and the selected account region is correct.
Restart Home Assistant after installation and add each EZVIZ account once.

To enable debug logging, add this to `configuration.yaml` and restart
Home Assistant:

```yaml
logger:
  default: info
  logs:
    custom_components.ezviz_vacuum: debug
```

When reporting an issue, include the Home Assistant and integration versions,
robot model and firmware version, account region, redacted integration
diagnostics and relevant debug log lines.

## Privacy

EZVIZ credentials are stored in the Home Assistant configuration entry.
Integration diagnostics redact credentials, tokens, session identifiers,
serial numbers, network addresses and secret keys. Share redacted diagnostics
and logs when reporting issues.

This is an unofficial community integration for EZVIZ devices.
