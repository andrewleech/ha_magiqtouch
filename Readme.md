[![GitHub Release][releases-shield]][releases]
[![License][license-shield]][license]

[![hacs][hacsbadge]][hacs]
[![Project Maintenance][maintenance-shield]][user_profile]

_Component to integrate with [MagIQtouch heating/cooling controllers][ha_magiqtouch]._

**This component will set up the following platforms.**

Platform | Description
-- | --
`climate` | Heating / Cooling control.
`sensor` | Temperature readings.

Evaporative coolers can use thermostat-driven temperature control or manual fan speeds when
those capabilities are reported by the controller. If no valid room temperature is reported,
the climate entity remains available with manual fan control and does not advertise thermostat
modes.

### Evaporative coolers

For an evaporative-only installation, Home Assistant exposes:

| Home Assistant control | MagIQtouch operation |
| --- | --- |
| Cool + target temperature | Evaporative cooling to the selected temperature |
| Cool + fan speed 1-10 | Evaporative cooling at a fixed fan speed |
| Fan only + fan speed 1-10 | Outside-air ventilation without evaporative cooling |
| Off | System off |

Heating is only shown when heater equipment is reported by the controller.

### HACS

Install HACS: https://www.hacs.xyz/docs/use/

Add `https://github.com/andrewleech/ha_magiqtouch` as a [custom repository in hacs](https://www.hacs.xyz/docs/faq/custom_repositories/) of type: 'Integration'

Back on the main HACS page you should now be able to find and install the MagIQtouch integration.


## Configuration
In the HA devices section you should now be able to add a MagIQtouch device, it will then ask for a username/password which will be 
the same ones used in the official Seeley phone app.


### Disclaimer
This package is in no way related to Seeley and they bear no responsibility over its use or maintenance. It has been developed completly 
independantly. Please use the github issue tracker to discuss any issues.

<!---->

***

[ha_magiqtouch]: https://github.com/andrewleech/ha_magiqtouch
[hacs]: https://hacs.xyz
[hacsbadge]: https://img.shields.io/badge/HACS-Custom-orange.svg?style=for-the-badge
[license]: https://github.com/andrewleech/ha_magiqtouch/blob/hacs/LICENSE
[license-shield]: https://img.shields.io/github/license/andrewleech/ha_magiqtouch.svg?style=for-the-badge
[maintenance-shield]: https://img.shields.io/badge/maintainer-Andrew%20Leech%20%40alelec-blue.svg?style=for-the-badge
[releases-shield]: https://img.shields.io/github/release/andrewleech/ha_magiqtouch.svg?style=for-the-badge
[releases]: https://github.com/andrewleech/ha_magiqtouch/releases
[user_profile]: https://github.com/andrewleech
