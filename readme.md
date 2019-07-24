# AutoLight
When you're automating your home or office, you'll often find you want to automate on/off control of light(s) based on one or more sensors, like motion sensors or door contacts.

With just one sensor, it's easy to write a native Home assistant automation to turn the light on and off. But when you want to use multiple door and motion sensors to control the state of one light, the automations start to become quite complex and repetetive. This AppDaemon app implements a configurable state machine that allows you to automate any number of lights based on the inputs from any number of different sensors.

## Current features
* Control any number of lights or other binary controllable entities
* Use any combination of sensors to control the light:
  * Door sensors turn on the light when the door is opened, and immediately start a timer to turn off the light after a configured time period. This behavior works well with doors that are often left open for long periods of time, where you just want the door to serve as an instant trigger when you open it.
  * Motion sensors turn on the light when motion is detected. When motion is no longer detected on _any_ of the connected sensors, the timer to turn off the light is started.
  * All sensors can be configured with a specific light sensor entity that gates the triggering of that sensor based on the local ambient light level. This can be useful if one light illuminates a large area and you want the sensor in a specific section to only trigger the light when that section is dark enough to need extra light.
* Global light sensor: if you don't need specific light sensor configuration for each sensor, you can configure a global light sensor that is used to filter the triggers from all sensors.

## Settings reference
### Main app configuration
<table>
    <thead>
        <tr>
            <th>
                Parameter
            </th>
            <th>
                Required
            </th>
            <th>
                Description
            </th>
        </tr>
    </thead>
    <tbody>
      <tr>
        <td>
          module
        </td>
        <td>
          required
        </td>
        <td>
          Mandatory for AppDaemon. Set to "auto_light".
        </td>
      </tr>
      <tr>
        <td>
          class
        </td>
        <td>
          required
        </td>
        <td>
          Mandatory for AppDaemon. Set to "AutoLight".
        </td>
      </tr>
      <tr>
        <td>
          delay_seconds
        </td>
        <td>
          required
        </td>
        <td>
          The number of seconds to delay turning off the light after no more motion is detected on any sensor.
        </td>
      </tr>
      <tr>
        <td>
          light_sensor
        </td>
        <td>
          optional
        </td>
        <td>
          Global light sensor configuration, see light sensor configuration section below. If omitted and also no sensor-specific light sensor is configured, the light will always trigger regardless of ambient light levels.
        </td>
      </tr>
      <tr>
        <td>
          lights
        </td>
        <td>
          required
        </td>
        <td>
          List of light entities to control from this instance
        </td>
      </tr>
      <tr>
        <td>
          sensors
        </td>
        <td>
          required
        </td>
        <td>
          List of sensors to connect to this instance. See sensor configuration section below
        </td>
      </tr>
    </tbody>
</table>

### Sensor configuration
<table>
    <thead>
        <tr>
            <th>
                Parameter
            </th>
            <th>
                Required
            </th>
            <th>
                Description
            </th>
        </tr>
    </thead>
    <tbody>
      <tr>
        <td>
          entity_id
        </td>
        <td>
          required
        </td>
        <td>
          The entity ID of the sensor to use
        </td>
      </tr>
      <tr>
        <td>
          type
        </td>
        <td>
          required
        </td>
        <td>
          The type of sensor (allowed values: "door" or "motion")
        </td>
      </tr>
      <tr>
        <td>
          light_sensor
        </td>
        <td>
          optional
        </td>
        <td>
          The light sensor configuration to apply to this specific sensor. If omitted, global (app-level) light sensor configuration will be used.
        </td>
      </tr>
    </tbody>
</table>

### Light sensor configuration
<table>
    <thead>
        <tr>
            <th>
                Parameter
            </th>
            <th>
                Required
            </th>
            <th>
                Description
            </th>
        </tr>
    </thead>
    <tbody>
      <tr>
        <td>
          entity_id
        </td>
        <td>
          required
        </td>
        <td>
          The entity ID of the light sensor to use
        </td>
      </tr>
      <tr>
        <td>
          threshold
        </td>
        <td>
          required
        </td>
        <td>
          The light value threshold. The light will not trigger if the sensor reports a value above this threshold.
        </td>
      </tr>
    </tbody>
</table>

## Configuration examples
Adjust these examples with your own preferences and add them to your AppDaemon `apps.yaml` configuration.

### Simplest working instance
This is the minimum configuration. It controls a single light from a single motion sensor.
```yaml
bathroom_light:
  module: auto_light
  class: AutoLight
  delay_seconds: 600
  lights:
    - entity_id: light.bathroom
  sensors: 
    - entity_id: binary_sensor.motion_sensor_bathroom
      type: motion
```

### Multiple sensors
This example uses a motion sensor to trigger when someone walks into the bathroom (e.g. when the door was already open). When the door is opened, the door sensor triggers the light instantly.
```yaml
bathroom_light:
  module: auto_light
  class: AutoLight
  delay_seconds: 600
  lights:
    - entity_id: light.bathroom
  sensors: 
    - entity_id: binary_sensor.motion_sensor_bathroom
      type: motion
    - entity_id: binary_sensor.door_window_sensor_bathroom_door
      type: door
```

### Global light sensor threshold
This example uses a single global light sensor to control when the light can turn on. Only when the light level at the light sensor is lower than 10, will the light turn on.
```yaml
bathroom_light:
  module: auto_light
  class: AutoLight
  delay_seconds: 600
  lights:
    - entity_id: light.bathroom
  light_sensor: 
    entity_id: sensor.illumination_bathroom
    threshold: 10
  sensors: 
    - entity_id: binary_sensor.motion_sensor_bathroom
      type: motion
    - entity_id: binary_sensor.door_window_sensor_bathroom_door
      type: door
```

### Different light sensors for different sensors
In this example, a patio light is controlled by two motion sensors that each have their own corresponding light sensor with different thresholds. The porch motion sensor will only trigger when it's dark at the porch.

Note that the door sensor for the patio door has no configured light sensor. If a light sensor were configured on the global level, it would use that. Since that is not the case, the light will _always_ turn on when the patio door is opened.
```yaml
patio_light:
  module: auto_light
  class: AutoLight
  delay_seconds: 600
  lights:
    - entity_id: light.patio
  sensors: 
    - entity_id: binary_sensor.motion_sensor_porch
      type: motion
      light_sensor: 
        entity_id: sensor.illumination_porch
        threshold: 30
    - entity_id: binary_sensor.motion_sensor_patio_door
      type: motion
      light_sensor: 
        entity_id: sensor.illumination_patio_door
        threshold: 25
    - entity_id: binary_sensor.door_window_sensor_patio_door
      type: door
```
