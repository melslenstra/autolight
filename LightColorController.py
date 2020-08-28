import appdaemon.plugins.hass.hassapi as hass
import math
import pysolar.solar as solar
from datetime import datetime

class LightColorController(hass.Hass):
    def initialize(self):
        self.log("============= Light Color Controller initializing ============= ")

        # Read settings
        # Read and check lights to control
        self.lights = self.args["lights"]
        for light in self.lights:
            self.check_entity_exists(light["entity_id"])

        # Light brightness control
        self.brightnessControl = False
        if ("brightness" in self.args):
            self.brightnessControl = True
            brightnessArgs = self.args["brightness"]
            self.brightnessCycleSettings = self.extract_cycle_settings(brightnessArgs)

            self.daytimeBrightnessLevel = brightnessArgs["daytime_level"]
            self.nighttimeBrightnessLevel = brightnessArgs["nighttime_level"]

            self.log("Brightness control initialized. Will control between {} (daytime) and {} (nighttime)".format(self.daytimeBrightnessLevel, self.nighttimeBrightnessLevel))

            self.brightnessCycleEngine = SolarCycleEngine(self.brightnessCycleSettings, self.brightness_log)

        if ("color_temperature" in self.args):
            self.colorTemperatureControl = True
            colorTemperatureArgs = self.args["color_temperature"]
            self.colorTemperatureCycleSettings = self.extract_cycle_settings(colorTemperatureArgs)

            self.daytimeColorTemperature = colorTemperatureArgs["daytime_level"]
            self.nighttimeColorTemperature = colorTemperatureArgs["nighttime_level"]

            self.log("Color temperature control initialized. Will control between {}K (daytime) and {}K (nighttime)".format(self.daytimeColorTemperature, self.nighttimeColorTemperature))

            self.colorTemperatureCycleEngine = SolarCycleEngine(self.colorTemperatureCycleSettings, self.color_temp_log)

        self.updateIntervalSeconds = self.args["update_rate"]

        self.latitude = self.config["latitude"]
        self.longitude = self.config["longitude"]

        # Set up schedule to update
        self.update()
        self.run_every(self.update, "now+5", self.updateIntervalSeconds)

        # Subscribe to light state changes
        for light in self.lights:
            self.listen_state(self.light_state_changed, light["entity_id"], attribute="all")

    def color_temp_log(self, message):
        self.log("Color temperature engine: {}".format(message))

    def brightness_log(self, message):
        self.log("Brightness engine: {}".format(message))

    def update(self, kwargs=None):
        currentDateTime = self.datetime(aware=True)        

        timestamp = datetime.timestamp(currentDateTime) + self.get_tz_offset() * 60
        timeOfDay = timestamp - (math.floor(timestamp / 86400) * 86400)

        sunElevation = solar.get_altitude(self.latitude, self.longitude, currentDateTime)

        sunRising = self.get_state("sun.sun", attribute="rising") or timeOfDay < 25000 #HACK

        if (self.brightnessControl):
            brightnessValue = self.brightnessCycleEngine.get_current_value(timeOfDay, sunElevation, sunRising)

            difference = self.daytimeBrightnessLevel - self.nighttimeBrightnessLevel

            self.brightness = int(self.nighttimeBrightnessLevel + (brightnessValue * difference))

            self.log("Brightness set to {}".format(self.brightness))


        if (self.colorTemperatureControl):
            colorTemperatureValue = self.colorTemperatureCycleEngine.get_current_value(timeOfDay, sunElevation, sunRising)

            difference = self.daytimeColorTemperature - self.nighttimeColorTemperature

            self.colorTemperature = int(self.nighttimeColorTemperature + (colorTemperatureValue * difference))

            self.log("Color temperature set to {}K".format(self.colorTemperature))

        self.update_active_lights()

    def update_active_lights(self):
        for light in self.lights:
            entityId = light["entity_id"]
            if(self.get_state(entityId) == "on"):
                self.set_light(entityId)

    def light_state_changed(self, entity, attribute, old, new, kwargs):
        if(new["state"] == "on"):
            self.log("Corrected values for: {}".format(entity))
            self.set_light(entity)

    def set_light(self, entityId):
        if(self.brightnessControl and not self.colorTemperatureControl):
            self.turn_on(entityId, brightness=self.brightness)
        elif (self.colorTemperatureControl and not self.brightnessControl):
            self.turn_on(entityId, kelvin=self.colorTemperature)
        elif (self.colorTemperatureControl and self.brightnessControl):
            self.turn_on(entityId, brightness=self.brightness, kelvin=self.colorTemperature)

    def extract_cycle_settings(self, settings):
        return type('', (object,), {
            'sunriseEarliestEndTime': float(self.timestamp_from_time_string(settings["sunriseEarliestEndTime"])),
            'sunriseLatestEndTime': float(self.timestamp_from_time_string(settings["sunriseLatestEndTime"])),
            'sunriseFadeTime': float(settings["sunriseFadeTime"]),
            'sunriseTargetElevation': float(settings["sunriseTargetElevation"]),
            'sunriseFadeAngle': float(settings["sunriseFadeAngle"]),
            'sunsetEarliestEndTime': float(self.timestamp_from_time_string(settings["sunsetEarliestEndTime"])),
            'sunsetLatestEndTime': float(self.timestamp_from_time_string(settings["sunsetLatestEndTime"])),
            'sunsetFadeTime': float(settings["sunsetFadeTime"]),
            'sunsetTargetElevation': float(settings["sunsetTargetElevation"]),
            'sunsetFadeAngle': float(settings["sunsetFadeAngle"])
        })()

    def timestamp_from_time_string(self, timeString):
        time_object = datetime.strptime(timeString, '%H:%M').time()
        return time_object.hour * 3600 + time_object.minute * 60

    def check_entity_exists(self, entity_id):
        state = self.get_state(entity_id)
        if state == None:
            self.log("ERROR: Entity {} missing or unavailable".format(entity_id))


class SolarCycleEngine():
    def __init__(self, settings, log):
        self.log = log

        self.sunriseEarliestEndTime = settings.sunriseEarliestEndTime
        self.sunriseLatestEndTime = settings.sunriseLatestEndTime
        self.sunriseFadeTime = settings.sunriseFadeTime

        self.sunriseEarliestFadeStartTime = self.sunriseEarliestEndTime - self.sunriseFadeTime
        self.sunriseLatestFadeStartTime = self.sunriseLatestEndTime - self.sunriseFadeTime

        self.sunriseEndElevation = settings.sunriseTargetElevation
        self.sunriseFadeAngle = settings.sunriseFadeAngle
        self.sunriseStartElevation = self.sunriseEndElevation - self.sunriseFadeAngle

        self.sunsetEarliestEndTime = settings.sunsetEarliestEndTime
        self.sunsetLatestEndTime = settings.sunsetLatestEndTime
        self.sunsetFadeTime = settings.sunsetFadeTime

        self.sunsetEarliestFadeStartTime = self.sunsetEarliestEndTime - self.sunsetFadeTime
        self.sunsetLatestFadeStartTime = self.sunsetLatestEndTime - self.sunsetFadeTime

        self.sunsetEndElevation = settings.sunsetTargetElevation
        self.sunsetFadeAngle = settings.sunsetFadeAngle
        self.sunsetStartElevation = self.sunsetEndElevation + self.sunsetFadeAngle

    def get_current_value(self, timeOfDay, sunElevation, sunRising):
        if(sunRising):
            sunValue = self.get_faded_value(sunElevation, self.sunriseStartElevation, self.sunriseEndElevation, False)
            earliestTimeValue = self.get_faded_value(timeOfDay, self.sunriseEarliestFadeStartTime, self.sunriseEarliestEndTime, False)
            latestTimeValue = self.get_faded_value(timeOfDay, self.sunriseLatestFadeStartTime, self.sunriseLatestEndTime, False)

            self.log("Rising sun, timeOfDay: {}, earliest: {}, sun: {}, latest: {}".format(int(timeOfDay), earliestTimeValue, sunValue, latestTimeValue))

            return float(min(earliestTimeValue, max(latestTimeValue, sunValue)))
        else:
            sunValue = self.get_faded_value(sunElevation, self.sunsetStartElevation, self.sunsetEndElevation, True)
            earliestTimeValue = self.get_faded_value(timeOfDay, self.sunsetEarliestFadeStartTime, self.sunsetEarliestEndTime, True)
            latestTimeValue = self.get_faded_value(timeOfDay, self.sunsetLatestFadeStartTime, self.sunsetLatestEndTime, True)

            self.log("Setting sun, timeOfDay: {}, earliest: {}, sun: {}, latest: {}".format(int(timeOfDay), earliestTimeValue, sunValue, latestTimeValue))

            return float(min(latestTimeValue, max(earliestTimeValue, sunValue)))

    def get_faded_value(self, currentInputValue, startFadeValue, endFadeValue, invert):
        fadeOffset = endFadeValue - startFadeValue
        idealFadeValue = (currentInputValue - startFadeValue) / fadeOffset
        cappedFadeValue = min(1, max(0, idealFadeValue))

        if (invert):
            cappedFadeValue = 1 - cappedFadeValue

        return cappedFadeValue
