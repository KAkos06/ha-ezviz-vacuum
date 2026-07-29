# EZVIZ Vacuum for Home Assistant

This integration lets you monitor and control verified functions of a supported
EZVIZ robot vacuum in Home Assistant.

After installation, you can see:

- the current activity of the robot vacuum;
- battery level;
- charging and online status;
- the current cleaning task;
- the configured fan speed and water level;
- controls for fan speed, water level, and automatic carpet boost;
- a return-to-dock command;
- the name of the active map;
- remaining values reported for the brushes, HEPA filter, mop, and sensors;

> [!IMPORTANT]
> Starting, pausing, and resuming a cleaning task are not yet supported because
> their cloud commands have not been verified for the targeted model.

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
- return-to-dock control;
- reported error state.

### Controls

- water quantity: no mopping, low, medium, or high;
- automatic carpet boost: on or off.

### Sensors

- battery level;
- current task state;
- fan speed;
- water level;
- map name;
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

> [!NOTE]
> EZVIZ does not clearly document the unit used for the consumable `rest`
> values. The integration therefore displays them as raw values without a unit.

## How quickly are states updated?

The integration requests the current state from the EZVIZ cloud every 15
seconds. A state change made with the EZVIZ app or the robot's physical buttons
may therefore take up to approximately 15 seconds to appear in Home Assistant.

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

- Starting, pausing, and resuming cleaning are not yet supported.
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
