# OctoPrint Filament Sensor Universal

[OctoPrint](http://octoprint.org/) plugin that integrates with 1 or 2 filament sensors hooked up to a Linux GPIO pin and allows the filament spool to be changed during a print if the filament runs out or is jammed. GPIO access is performed using libgpiod, allowing many single-board computers to be supported.

Based on the [Octoprint-Filament-Revolutions](https://github.com/RomRider/Octoprint-Filament-Revolutions) plugin.

## Required sensor

Using this plugin requires a filament sensor and/or a jam sensor. The code is set to use internal pull-up resistors, so the switch(es) should be between your detection pin and a ground pin.

## Features

* Configurable GPIO pins.
* Debounce noisy sensors.
* Support normally open and normally closed sensors.
* Execution of custom GCODE when out of filament detected.
* Optionally pause print when out of filament.

An API is available to check the filament sensors status via a GET method:
* to `/plugin/filamentsensoruniversal/filament` for the filament sensor
* to `/plugin/filamentrevolutions/jammed` for the jam sensor

- `{status: "-1"}` if the sensor is not setup
- `{status: "0"}` if the sensor is OFF (filament not present/filament not jammed)
- `{status: "1"}` if the sensor is ON (filament present/filament jammed)

## Installation

* Install via the bundled [Plugin Manager](https://github.com/foosel/OctoPrint/wiki/Plugin:-Plugin-Manager).
* Manually using this URL: https://github.com/lopsided98/OctoPrint-Filament-Sensor-Universal/archive/master.zip

## Configuration

After installation, configure the plugin via OctoPrint Settings interface.
