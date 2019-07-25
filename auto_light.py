import appdaemon.plugins.hass.hassapi as hass

class AutoLight(hass.Hass):

  def initialize(self):
    self.log("Auto Light initializing")

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
          self.sensors.append(MotionSensor(sensor_config, self.listen_state, self.log, self.get_state, self.get_global_illum_filter_value, self.start_timer_callback, self.cancel_timer_callback, self.on_callback, self.evaluate_light_sensor, self.friendly_name))
        elif sensor_config["type"].lower() == "door":
          self.sensors.append(DoorSensor(sensor_config, self.listen_state, self.log, self.get_state, self.get_global_illum_filter_value, self.start_timer_callback, self.cancel_timer_callback, self.on_callback, self.evaluate_light_sensor, self.friendly_name))
        else:
          self.log("Specified sensor type not supported: {}".format(sensor_config["type"]))

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

  def light_off(self, kwargs):
    self.light_switch("off")

  def light_switch(self, on):
    for light in self.lights:
      if on == "on":
        self.turn_on(light["entity_id"])
        self.log("Turned ON {}".format(self.friendly_name(light["entity_id"])))
      else:
        self.turn_off(light["entity_id"])
        self.log("Turned OFF {}".format(self.friendly_name(light["entity_id"])))
  
  def evaluate_light_sensor(self, entity_id, threshold):
    sensor_value = int(self.get_state(entity_id))
    return LightSensorEvaluation.evaluate(self.friendly_name(entity_id), sensor_value, threshold)

# TODO implement abc
class Sensor:
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
    self.listen_state(self.state_changed, self.sensor_entity_id)

    light_sensor_logmsg = self.light_sensor_entity_id if self.light_sensor != None else "NONE"
    self.log("-- Initialized {} sensor {} with light sensor {}".format(self.get_type_name(), self.friendly_name(self.sensor_entity_id), light_sensor_logmsg))

  def get_illum_filter_value(self):
    if self.light_sensor != None:
      return self.evaluate_light_sensor(self.light_sensor_entity_id, self.light_sensor_threshold)
    else:
      return self.global_illum_callback()

  def hold_light_on(self):
    pass

  def trigger_on(self):
    pass

  def trigger_off(self):
    pass

  def get_type_name(self):
    pass

  def state_changed(self, entity, attribute, old, new, kwargs):
    # Always filter out bogus events, we're only looking for changes.
    # TODO: make this behavior (optionally) configurable
    if new == old:
      return
    
    self.log("-- {} sensor {} went from {} to {}".format(self.get_type_name(), self.friendly_name(self.sensor_entity_id), old, new))

    # TODO: make the "on" (and perhaps also "off") states configurable
    if new == "on":
      result = self.get_illum_filter_value()
      if result.dark_enough:
        self.trigger_on()
      else:
        self.log("-- {} sensor ON trigger filtered, light sensor {} value {} is below threshold {}".format(self.friendly_name(self.sensor_entity_id), result.sensor_friendly_name, result.sensor_value, result.threshold))
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
  def evaluate(lse, sensor_friendly_name, value, threshold):
    return LightSensorEvaluation(value <= threshold, sensor_friendly_name, value, threshold)

  @classmethod
  def fake_result(LightSensorEvaluation, dark_enough):
    return LightSensorEvaluation(dark_enough, "none", 0, 0)