import appdaemon.plugins.hass.hassapi as hass
from abc import ABC, abstractmethod


class AutoLight(hass.Hass):

    def initialize(self):
        self.log("============= Auto Light initializing ============= ")

        self.timer = None

        self.lights = self.args["lights"]
        self.delay_seconds = self.args["delay_seconds"]

        if "light_sensor" in self.args:
            self.global_illum_sensor_entityid = self.args["light_sensor"]["entity_id"]
            self.global_illum_threshold = self.args["light_sensor"]["threshold"]
        else:
            self.global_illum_sensor_entityid = None
            self.global_illum_threshold = 0

        # Initialize sensors
        self.sensors = []
        if "sensors" in self.args:
            for sensor_config in self.args["sensors"]:
                if sensor_config["type"].lower() == "motion":
                    self.sensors.append(MotionSensor(sensor_config, self.listen_state, self.log, self.get_state, self.get_global_illum_filter_value,
                                                     self.start_timer_callback, self.cancel_timer_callback, self.on_callback, self.evaluate_light_sensor, self.friendly_name))
                elif sensor_config["type"].lower() == "door":
                    self.sensors.append(DoorSensor(sensor_config, self.listen_state, self.log, self.get_state, self.get_global_illum_filter_value,
                                                   self.start_timer_callback, self.cancel_timer_callback, self.on_callback, self.evaluate_light_sensor, self.friendly_name))
                else:
                    self.log("Specified sensor type not supported: {}".format(sensor_config["type"]))

        # Call start timer routine to make sure any lights that were on during a HA/AppDaemon/app restart are eventually turned off.
        # This does account for motion sensors holding the light on because they'll eventually turn off and trigger the timer there.
        self.light_on = self.any_light_on()
        if self.light_on:
            self.start_timer_callback()

    def get_global_illum_filter_value(self):
        # Called by a sensor when it wants to check the global illumination filter value
        if self.global_illum_sensor_entityid != None:
            return self.evaluate_light_sensor(self.global_illum_sensor_entityid, self.global_illum_threshold)
        else:
            return LightSensorEvaluation.fake_result(True)

    def start_timer_callback(self):
        # Called by a sensor when it signals the timer to turn off the light should start
        # Check whether any other sensors want to hold the light on - if so, those sensors
        # promise they'll start the timer when the hold condition goes away (e.g. motion
        # no longer detected).
        if not self.hold_light_on():
            self.__set_light_timer()

    def cancel_timer_callback(self):
        self.__cancel_light_timer()

    def on_callback(self):
        self.light_switch("on")

    def __cancel_light_timer(self):
        if self.timer != None:
            self.cancel_timer(self.timer)

    def __set_light_timer(self):
        self.__cancel_light_timer()
        if self.delay_seconds > 0:
            self.timer = self.run_in(self.light_off, self.delay_seconds)
            self.log("Turn off timer started ({} seconds)".format(self.delay_seconds))
        else:
            self.light_off()

    def hold_light_on(self):
        for sensor in self.sensors:
            if sensor.hold_light_on():
                return True
        return False

    def any_light_on(self):
        for light in self.lights:
            if self.get_state(light["entity_id"]) == "on":
                return True
        return False

    def light_off(self, kwargs):
        self.light_switch("off")

    def light_switch(self, on):
        self.light_on = on
        for light in self.lights:
            if on == "on":
                self.turn_on(light["entity_id"])
                self.log("Turned ON {}".format(self.friendly_name(light["entity_id"])))
            else:
                self.turn_off(light["entity_id"])
                self.log("Turned OFF {}".format(self.friendly_name(light["entity_id"])))

    def evaluate_light_sensor(self, entity_id, threshold):
        # If the light is already on, don't evaluate the light sensors.
        if self.light_on:
            return LightSensorEvaluation.fake_result(True)

        # Try 5 times to get the sensor value
        sensor_state = ""
        tries = 0
        while tries <= 5 and not sensor_state.isdigit():
            sensor_state = self.get_state(entity_id)
            tries += 1

        if not sensor_state.isdigit():
            self.log("ERROR: Sensor {} returned state {} after {} tries to get a number. Assuming value 0 (full darkness).".format(self.friendly_name(entity_id), sensor_state, tries))
            sensor_state = "0"

        sensor_value = int(sensor_state)

        return LightSensorEvaluation.evaluate(self.friendly_name(entity_id), sensor_value, threshold)


class Sensor(ABC):
    def __init__(self, config, listen_state, log, get_state, global_illum_callback, start_timer_callback, cancel_timer_callback, on_callback, evaluate_light_sensor, friendly_name):
        self.listen_state = listen_state
        self.log = log
        self.global_illum_callback = global_illum_callback
        self.get_state = get_state
        self.start_timer_callback = start_timer_callback
        self.cancel_timer_callback = cancel_timer_callback
        self.on_callback = on_callback
        self.evaluate_light_sensor = evaluate_light_sensor
        self.friendly_name = friendly_name

        if "light_sensor" in config:
            self.light_sensor = config["light_sensor"]
            self.light_sensor_entity_id = self.light_sensor["entity_id"]
            self.light_sensor_threshold = self.light_sensor["threshold"]
        else:
            self.light_sensor = None

        self.sensor_entity_id = config["entity_id"]
        self.listen_state(self.__state_changed, self.sensor_entity_id)

        light_sensor_logmsg = self.light_sensor_entity_id if self.light_sensor != None else "NONE"
        self.log("-- Initialized {} sensor {} with light sensor {}".format(self.get_type_name(), self.friendly_name(self.sensor_entity_id), light_sensor_logmsg))

    def get_illum_filter_value(self):
        if self.light_sensor != None:
            return self.evaluate_light_sensor(self.light_sensor_entity_id, self.light_sensor_threshold)
        else:
            return self.global_illum_callback()

    @abstractmethod
    def hold_light_on(self):
        pass

    @abstractmethod
    def trigger_on(self):
        pass

    @abstractmethod
    def trigger_off(self):
        pass

    @abstractmethod
    def get_type_name(self):
        pass

    def __state_changed(self, entity, attribute, old, new, kwargs):
        # Always filter out bogus events, we're only looking for changes.
        # TODO: make this behavior (optionally) configurable
        if new == old:
            return

        self.log("-- {} sensor {} went from {} to {}".format(self.get_type_name(), self.friendly_name(self.sensor_entity_id), old, new))

        # TODO: make the "on" (and perhaps also "off") states configurable
        if new == "on":
            result = self.get_illum_filter_value()
            if result.dark_enough:
                self.log("-- {} sensor passed, light sensor {} value {} is on or below threshold {}".format(self.friendly_name(self.sensor_entity_id), result.sensor_friendly_name, result.value, result.threshold))
                self.trigger_on()
            else:
                self.log("-- {} sensor filtered, light sensor {} value {} is above threshold {}".format(self.friendly_name(self.sensor_entity_id), result.sensor_friendly_name, result.value, result.threshold))
        else:
            self.trigger_off()


class MotionSensor(Sensor):
    def hold_light_on(self):
        return self.get_illum_filter_value() and self.get_state(self.sensor_entity_id) == "on"

    def get_type_name(self):
        return "Motion"

    def trigger_on(self):
        # Turn the light on
        self.on_callback()
        # Cancel the timer if it's running
        self.cancel_timer_callback()

    def trigger_off(self):
        # Ask the main app to start the timer which eventually turns the light back off (if no other sensors hold the light on right now!).
        self.start_timer_callback()


class DoorSensor(Sensor):
    def hold_light_on(self):
        # Door never holds light on (TODO: make configurable)
        return False

    def get_type_name(self):
        return "Door"

    def trigger_on(self):
        # Turn the light on
        self.on_callback()
        # Start the timer to turn it back off
        self.start_timer_callback()

    def trigger_off(self):
        # Door sensors do nothing when closing the door
        # TODO make door sensor behavior more configurable?
        pass


class LightSensorEvaluation:
    def __init__(self, dark_enough, sensor_friendly_name, value, threshold):
        self.dark_enough = dark_enough
        self.sensor_friendly_name = sensor_friendly_name
        self.value = value
        self.threshold = threshold

    @classmethod
    def evaluate(cls, sensor_friendly_name, value, threshold):
        outcome = value <= threshold
        return cls(outcome, sensor_friendly_name, value, threshold)

    @classmethod
    def fake_result(cls, dark_enough):
        return cls(dark_enough, "(none)", None, None)
