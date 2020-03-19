import threading
import time
from typing import Any, Dict, List, Optional

import gpiod  # type: ignore
import octoprint.plugin  # type: ignore
from flask import jsonify
from octoprint.events import Events  # type: ignore


class Debouncer:

    def __init__(self, line: gpiod.Line, interval: float):
        """
        Create a new debouncer for the specified GPIO line.

        :param line: GPIO line
        :param interval: debounce interval in seconds
        """

        self.line = line
        self.interval = interval
        self.value = self.raw
        self.rising = False
        self.falling = False

        self._last_value = self.value
        self._last_change_time = time.time()

    @property
    def raw(self) -> bool:
        """
        Get the raw sensor state.

        :return: the raw sensor value
        """
        return bool(self.line.get_value())

    def update(self):
        now = time.time()
        raw = self.raw
        if raw != self._last_value:
            self._last_value = raw
            self._last_change_time = now

        old_value = self.value
        if now - self._last_change_time > self.interval:
            self.value = raw

        self.rising = self.value and not old_value
        self.falling = not self.value and old_value


class FilamentSensorUniversal(octoprint.plugin.EventHandlerPlugin,
                              octoprint.plugin.TemplatePlugin,
                              octoprint.plugin.SettingsPlugin,
                              octoprint.plugin.BlueprintPlugin):

    def __init__(self):
        super().__init__()
        self._gpio_lock = threading.Lock()

        self._runout_debouncer: Optional[Debouncer] = None
        self._jam_debouncer: Optional[Debouncer] = None

        self._print_running = False

    def initialize(self):
        self._logger.info("Filament Sensor Universal started")
        self._setup_sensor()
        # Start the sensor polling thread
        threading.Thread(target=self._sensor_thread, daemon=True).start()

    @octoprint.plugin.BlueprintPlugin.route("/filament", methods=["GET"])
    def api_get_filament(self) -> str:
        status = "-1"
        if self.runout_sensor_enabled:
            status = "0" if self.runout_sensor else "1"
        return jsonify(status=status)

    @octoprint.plugin.BlueprintPlugin.route("/jammed", methods=["GET"])
    def api_get_jammed(self) -> str:
        status = "-1"
        if self.jam_sensor_enabled:
            status = "1" if self.jam_sensor else "0"
        return jsonify(status=status)

    @property
    def runout_chip(self) -> str:
        return str(self._settings.get(["runout_chip"]))

    @property
    def jam_chip(self) -> str:
        return str(self._settings.get(["jam_chip"]))

    @property
    def runout_pin(self) -> int:
        return int(self._settings.get(["runout_pin"]))

    @property
    def jam_pin(self) -> int:
        return int(self._settings.get(["jam_pin"]))

    @property
    def runout_bounce(self) -> int:
        return int(self._settings.get(["runout_bounce"]))

    @property
    def jam_bounce(self) -> int:
        return int(self._settings.get(["jam_bounce"]))

    @property
    def runout_switch(self) -> int:
        return int(self._settings.get(["runout_switch"]))

    @property
    def jam_switch(self) -> int:
        return int(self._settings.get(["jam_switch"]))

    @property
    def runout_gcode(self) -> List[str]:
        return str(self._settings.get(["runout_gcode"])).splitlines()

    @property
    def jammed_gcode(self) -> List[str]:
        return str(self._settings.get(["jammed_gcode"])).splitlines()

    @property
    def runout_pause_print(self) -> bool:
        return self._settings.get_boolean(["runout_pause_print"])

    @property
    def jammed_pause_print(self) -> bool:
        return self._settings.get_boolean(["jammed_pause_print"])

    def _sensor_thread(self):
        while True:
            runout_triggered = False
            jam_triggered = False

            # We have to use polling because a lot of hardware does not support
            # gpio chardev events
            with self._gpio_lock:
                if self._runout_debouncer is not None:
                    self._runout_debouncer.update()
                    # Filament runs out when sensor goes inactive
                    runout_triggered = self._runout_debouncer.falling
                if self._jam_debouncer is not None:
                    self._jam_debouncer.update()
                    jam_triggered = self._jam_debouncer.rising

            if runout_triggered:
                self.runout_handler()
            if jam_triggered:
                self.jam_handler()

            time.sleep(0.2)

    def _setup_sensor(self):
        with self._gpio_lock:
            # We are either disabling the sensors or reopening them, so close the
            # existing chips
            if self._runout_debouncer is not None:
                self._runout_debouncer.line.owner().close()
                self._runout_debouncer = None
            if self._jam_debouncer is not None:
                self._jam_debouncer.line.owner().close()
                self._jam_debouncer = None

            if self.runout_sensor_enabled:
                try:
                    runout_chip = gpiod.Chip(self.runout_chip)
                    runout_line = runout_chip.get_line(self.runout_pin)
                    runout_line.request(
                        consumer="OctoPrint filament runout sensor")
                    runout_line.set_direction_input()
                    runout_line.set_flags(gpiod.LINE_REQ_FLAG_BIAS_PULL_UP |
                                          (gpiod.LINE_REQ_FLAG_ACTIVE_LOW if self.runout_switch == 0 else 0))
                    self._runout_debouncer = Debouncer(
                        runout_line, self.runout_bounce)
                    self._logger.info("Filament runout sensor active on GPIO chip: %s, line: %d",
                                      self.runout_chip, self.runout_pin)
                except OSError as e:
                    self._logger.error(
                        "Invalid filament runout sensor configuration", exc_info=e)
            else:
                self._logger.info("Filament runout sensor not configured")

            if self.jam_sensor_enabled:
                try:
                    jam_chip = gpiod.Chip(self.jam_chip)
                    jam_line = jam_chip.get_line(self.jam_pin)
                    jam_line.request(consumer="OctoPrint filament jam sensor")
                    jam_line.set_direction_input()
                    jam_line.set_flags(gpiod.LINE_REQ_FLAG_BIAS_PULL_UP |
                                       (gpiod.LINE_REQ_FLAG_ACTIVE_LOW if self.jam_switch == 0 else 0))
                    self._jam_debouncer = Debouncer(jam_line, self.jam_bounce)
                    self._logger.info("Filament jam sensor active on GPIO chip: %s, line: %d",
                                      self.jam_chip, self.jam_pin)
                except OSError as e:
                    self._logger.error(
                        "Invalid filament jam sensor configuration", exc_info=e)
            else:
                self._logger.info("Filament jam sensor not configured")

    def get_settings_defaults(self):
        return dict(
            runout_chip="",  # Default is disabled
            runout_pin=0,
            runout_bounce=1000,  # Debounce 1000 ms
            runout_switch=0,    # Normally Open
            runout_gcode='',
            runout_pause_print=True,

            jam_chip="",  # Default is disabled
            jam_pin=0,
            jam_bounce=1000,  # Debounce 1000 ms
            jam_switch=1,  # Normally Closed
            jammed_gcode='',
            jammed_pause_print=True
        )

    def on_settings_save(self, data):
        octoprint.plugin.SettingsPlugin.on_settings_save(self, data)
        self._setup_sensor()

    @property
    def runout_sensor_enabled(self) -> bool:
        return self.runout_chip != ""

    @property
    def jam_sensor_enabled(self) -> bool:
        return self.jam_chip != ""

    @property
    def runout_sensor(self) -> bool:
        with self._gpio_lock:
            if self._runout_debouncer is None:
                return False
            return not self._runout_debouncer.value

    @property
    def jam_sensor(self) -> bool:
        with self._gpio_lock:
            if self._jam_debouncer is None:
                return False
            return self._jam_debouncer.value

    def get_template_configs(self) -> List[Dict[str, Any]]:
        return [{"type": "settings", "custom_bindings": False}]

    def get_template_vars(self):
        chips = []
        chip: gpiod.Chip
        for chip in gpiod.ChipIter():
            chips.append({
                'name': chip.name(),
                'label': chip.label()
            })
            chip.close()
        return {'chips': chips}

    def on_event(self, event, payload):
        # Early abort in case of out of filament when start printing, as we
        # can't change with a cold nozzle
        if event is Events.PRINT_STARTED:
            if self.runout_sensor:
                self._logger.info("Printing aborted: no filament detected!")
                self._printer.cancel_print()
            if self.jam_sensor:
                self._logger.info("Printing aborted: filament jammed!")
                self._printer.cancel_print()

        # Enable sensor
        if event in (
            Events.PRINT_STARTED,
            Events.PRINT_RESUMED
        ):
            self._print_running = True

        # Disable sensor
        elif event in (
            Events.PRINT_DONE,
            Events.PRINT_FAILED,
            Events.PRINT_PAUSED,
            Events.PRINT_CANCELLED,
            Events.ERROR
        ):
            self._print_running = False

    def runout_handler(self):
        self._logger.info("Out of filament!")
        # Don't do anything when a print is not currently in progress
        if self._print_running:
            if self.runout_pause_print:
                self._logger.info("Pausing print.")
                self._printer.pause_print()
                self._print_running = False
            if self.runout_gcode:
                self._logger.info("Sending out of filament GCODE")
                self._printer.commands(self.runout_gcode)

    def jam_handler(self):
        self._logger.info("Filament jammed!")
        # Don't do anything when a print is not currently in progress
        if self._print_running:
            if self.jammed_pause_print:
                self._logger.info("Pausing print.")
                self._printer.pause_print()
                self._print_running = False
            if self.jammed_gcode:
                self._logger.info("Sending jammed GCODE")
                self._printer.commands(self.jammed_gcode)

    def get_update_information(self):
        return dict(
            filamentrevolutions=dict(
                displayName="Filament Sensor Universal",
                displayVersion=self._plugin_version,

                # version check: github repository
                type="github_release",
                user="lopsided98",
                repo="OctoPrint-Filament-Sensor-Universal",
                current=self._plugin_version,

                # update method: pip
                pip="https://github.com/lopsided98/OctoPrint-Filament-Sensor-Universal/archive/{target_version}.zip"
            )
        )


__plugin_name__ = "Filament Sensor Universal"
__plugin_pythoncompat__ = ">=3,<4"


def __plugin_load__():
    global __plugin_implementation__
    __plugin_implementation__ = FilamentSensorUniversal()

    global __plugin_hooks__
    __plugin_hooks__ = {
        "octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
    }


def __plugin_check__():
    try:
        import gpiod
    except ImportError:
        return False

    return True
