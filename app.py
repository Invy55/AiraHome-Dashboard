from influxdb_client import InfluxDBClient, Point, WritePrecision, BucketRetentionRules
from datetime import datetime, timezone
from pyairahome import AiraHome
from pyairahome.utils import AuthenticationError
import dotenv, os, colorlog, time, schedule, atexit

# Load environment variables from .env file
dotenv.load_dotenv()

# Configure logging
handler = colorlog.StreamHandler()
handler.setFormatter(colorlog.ColoredFormatter(
    '%(asctime)s [%(log_color)s%(levelname)s%(reset)s]: %(message)s'))

logger = colorlog.getLogger('logger')
logger.addHandler(handler)
logger.setLevel(colorlog.DEBUG)

url = os.getenv("INFLUXDB_URL") or "http://localhost:8086"
token = os.getenv("TOKEN") or "airahome-dashboard-token"
org = os.getenv("ORG") or "airahome"

def create_bucket_if_not_exists(client, bucket_name):
    buckets_api = client.buckets_api()
    try:
        bucket = buckets_api.find_bucket_by_name(bucket_name)
        if not bucket:
            logger.debug(f"Creating bucket: {bucket_name}")
            retention_rules = BucketRetentionRules(type="expire", every_seconds=0)  # never expire, TODO handle downsampling separately
            buckets_api.create_bucket(bucket_name=bucket_name, retention_rules=retention_rules, org=org)
        else:
            logger.debug(f"Bucket '{bucket_name}' already exists")
    except Exception as e:
        logger.error(f"Error creating bucket: {e}")

def time_convert(time_str):
    return datetime.fromisoformat(time_str.replace("Z", "+00:00"))

def add_field_auto(point, fields, data):
    for item in fields:
        #logger.debug(f"{item}, {data.get(item)}")
        point = point.field(item, data.get(item))
    return point

def aira_login(username, password):
    aira = AiraHome()
    try:
        aira.login_with_credentials(username=username, password=password)
        logger.debug("Successfully logged in to AiraHome")
        return aira
    except AuthenticationError as e:
        logger.error(f"Authentication failed: {e}")
        return
    except Exception as e:
        logger.error(f"Error logging in to AiraHome: {e}")
        return

username = os.getenv("AIRAHOME_USERNAME")
password = os.getenv("AIRAHOME_PASSWORD")
if not username or not password:
    raise ValueError("AIRAHOME_USERNAME and AIRAHOME_PASSWORD must be set in the .env file")

aira = aira_login(username, password)

def task(write_api, states_bucket, devices_bucket):
    global aira
    logger.debug("Running scheduled task to fetch AiraHome data")
    if not aira:
        logger.error("AiraHome client is not initialized. Skipping task.")
        return
    try:
        devices = aira.get_devices()
    except:
        temp_aira = aira_login(username, password)
        devices = aira.get_devices()
        
    logger.debug(f"Found {len(devices)} device(s)")
    final_time = None
    for device in devices['devices']:
        points = []
        device_point = (
                        Point("heat_pump")
                        .tag("id", device['id']['value'])
                        .field("online", device['online']['online'])
                    )
        points.append((devices_bucket, device_point))
        if device['online']['online']:
            states = aira.get_states(device['id']['value'])['heat_pump_states'][0]

            # HEATPUMP
            heatpump_point = add_field_auto(
                                            Point("heat_pump").tag("id", device['id']['value']),
                                            ["current_outdoor_temperature",
                                            "led_pattern",
                                            "manual_mode_enabled",
                                            "operating_status",
                                            "allowed_pump_mode_state",
                                            "night_mode_enabled",
                                            "configured_pump_modes",
                                            "pump_active_state",
                                            "inline_heater_active", # TODO is this the resistor for the dhw or the external module?
                                            "away_mode_enabled",
                                            "power_preference"],
                                            states
                                            )                    
            heatpump_point = add_field_auto(heatpump_point,
                                            ["hp_has_some_alarm",
                                                "hp_has_stopping_alarms",
                                                "hp_has_acknowledgeable_alarms",
                                                "compressor_has_stopping_alarm"],
                                            states.get("error_metadata", {})
                                            )
            
            heatpump_point = heatpump_point.field("signature_element_enabled", states.get("signature_element", {}).get("enabled"))
            points.append((states_bucket, heatpump_point))

            # DHW
            water_heater_point = add_field_auto(
                                            Point("water_heater").tag("id", device['id']['value']),
                                            ["target_hot_water_temperature",
                                            "current_hot_water_temperature"],
                                            states
                                        )
            water_heater_point = water_heater_point.field("hot_water_heating_enabled", states.get("hot_water", {}).get("heating_enabled"))
            water_heater_point = water_heater_point.field("force_heating_enabled", states.get("force_heating", {}).get("enabled")) # TODO check if this is forced dhw or anything else
            points.append((states_bucket, water_heater_point))

            # VERSIONS
            version_point = add_field_auto(
                                        Point("version").tag("id", device['id']['value']),
                                        ["linux_build_id",
                                            "connectivity_manager",
                                            "cm_care",
                                            "silabs_firmware",
                                            "climate_control_villa",
                                            "outdoor_unit_application",
                                            "outdoor_unit_eeprom"],
                                            states
                                        )
            points.append((states_bucket, version_point))
            
            # ERRORS
            for error in states.get("errors", []):
                error_point = (
                                    Point("error").tag("id", device['id']['value'])
                                    .tag("severity", error.get("severity"))
                                    .tag("ccv", error.get("ccv"))
                                    .field("active", True)
                                    .time(datetime.now(timezone.utc), WritePrecision.MS)
                                    )
                points.append((states_bucket, error_point))
            
            # THERMOSTATS
            zone_points = {"zone_1": Point("thermostat").tag("id", device['id']['value']).tag("zone", 1),
                            "zone_2": Point("thermostat").tag("id", device['id']['value']).tag("zone", 2)}
            for zone, value in states.get("zone_setpoints_heating", {}).items():
                zone_points[zone] = zone_points[zone].field("zone_setpoint_heating", value)
            for zone, value in states.get("zone_temperatures", {}).items():
                zone_points[zone] = zone_points[zone].field("zone_temperature", value)
            for zone, value in states.get("zone_setpoints_cooling", {}).items():
                zone_points[zone] = zone_points[zone].field("zone_setpoint_cooling", value)
            for zone, value in states.get("current_pump_mode_state", {}).items():
                zone_points[zone] = zone_points[zone].field("current_pump_mode_state", value)

            for thermostat in states.get("thermostats", []):
                tid = thermostat.get("zone")
                if not isinstance(tid, str):
                    continue
                tid = tid.lower()
                zone_points[tid] = add_field_auto(zone_points[tid],
                                                    ["article_number",
                                                    "serial_number",
                                                    "rssi"],
                                                    thermostat)
                
                zone_points[tid] = add_field_auto(zone_points[tid],
                                                    ["warning_low_battery_level"],
                                                    thermostat.get("last_update", {}))

                zone_points[tid] = add_field_auto(zone_points[tid],
                                                    ["fw_version",
                                                    "bootloader_version",
                                                    "wakeup_count",
                                                    "reboot_count",
                                                    "setpoint_set_count",
                                                    "dhw_boost_count"],
                                                    thermostat.get("last_update", {}).get("info", {}))
                actual_temperature = thermostat.get("last_update", {}).get("actual_temperature")
                humidity = thermostat.get("last_update", {}).get("humidity")
                zone_points[tid] = zone_points[tid].field("actual_temperature", actual_temperature/10 if actual_temperature else None)
                zone_points[tid] = zone_points[tid].field("humidity", humidity/10 if humidity else None)

            for zone_point in zone_points.values():
                points.append((states_bucket, zone_point))

            # Write
            final_time = datetime.now(timezone.utc)
            for (bucket, point) in points:
                point = point.time(final_time, WritePrecision.S)
                write_api.write(bucket=bucket, org=org, record=point)
    if final_time:
        logger.info(f"Data written to InfluxDB for {len(devices['devices'])} device(s) at {final_time.isoformat()}")

def atexit_handler(client):
    if client:
        logger.debug("Closing InfluxDB client")
        client.close()

def main(username, password):
    global aira
    client = InfluxDBClient(url=url, token=token, org=org)
    logger.debug(f"Connecting to InfluxDB at {url} with token")
    if not client.ping():
        logger.error("Failed to connect to InfluxDB")
        return
    logger.debug("Successfully connected to InfluxDB")
    if not aira:
        return
    
    write_api = client.write_api()
    # Create buckets if they do not exist
    states_bucket = os.getenv("STATES_BUCKET", "states")
    devices_bucket = os.getenv("DEVICES_BUCKET", "devices")
    create_bucket_if_not_exists(client, states_bucket)
    create_bucket_if_not_exists(client, devices_bucket)

    # Schedule the task to run every minute
    schedule.every(1).minute.do(task, write_api, states_bucket, devices_bucket)

    # Register atexit handler to close the InfluxDB client
    atexit.register(atexit_handler, client)

    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    try:
        main(username, password)
    except KeyboardInterrupt:
        print()
        logger.debug("Process interrupted by user CTRL + C")