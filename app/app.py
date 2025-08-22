import time
from datetime import datetime, timezone
import colorlog
import schedule
from influxdb_client import InfluxDBClient, Point, WritePrecision, BucketRetentionRules
from pyairahome import AiraHome
from pyairahome.utils import AuthenticationError

class AiraHomeClient():
    def __init__(self, env: bool = True, url: str | None = None, token: str | None = None, 
                 org: str | None = None, devices_bucket: str | None = None,
                 states_bucket: str | None = None, username: str | None = None,
                 password: str | None = None):
        """
        Initialize the AiraHomeClient. Pass `env=True` to load environment variables from a .env file, any added parameter will override the environment ones.
        If `env=False`, you must provide all parameters: url, token, org, username, and password.
        """
        self.url, self.org, self.token, self.devices_bucket, self.states_bucket, self.username, \
        self.password = [None] * 7  # Initialize all attributes to None
        if not env and not all([url, token, org, devices_bucket, states_bucket, username, password]):
            raise ValueError("If env is False, all parameters must be provided.")
        if env:
            self._load_dotenv()
        self.url = url if not self.url else self.url
        self.token = token if not self.token else self.token
        self.org = org if not self.org else self.org
        self.devices_bucket = devices_bucket if not self.devices_bucket else self.devices_bucket
        self.states_bucket = states_bucket if not self.states_bucket else self.states_bucket
        self.username = username if not self.username else self.username
        self.password = password if not self.password else self.password

        # Do boot stuff
        self._logger()
        self._connect_influxdb()
        self._check_initiated()
        self.logger.info("Pre-modules initialized successfully.")

        # Initialize AiraHome
        self.aira = None
        self.authenticated = False
        self.last_auth_time = None
        self.aira_auth()
        if not self.authenticated:
            raise AuthenticationError("AiraHome authentication failed. Please check your credentials.")

    def _load_dotenv(self):
        """
        Load environment variables from a .env file.
        If the file is not found, it will use default values.
        """
        from dotenv import load_dotenv # type: ignore
        import os
        # Load environment variables from .env file
        load_dotenv()
        self.url = os.getenv("INFLUXDB_URL") or "http://localhost:8086"
        self.token = os.getenv("TOKEN") or "airahome-dashboard-token"
        self.org = os.getenv("ORG") or "airahome"
        self.devices_bucket = os.getenv("DEVICES_BUCKET") or "devices"
        self.states_bucket = os.getenv("STATES_BUCKET") or "states"
        self.username = os.getenv("AIRAHOME_USERNAME") or None
        self.password = os.getenv("AIRAHOME_PASSWORD") or None
    
    def _check_initiated(self):
        try:
            if not all([self.url, self.token, self.org, self.username, self.password,
                        self.client, self.write_api, self.buckets_api, self.logger]):
                raise ValueError("Client not properly initialized. Please check your parameters.")
        except AttributeError as e:
            raise ValueError("Client not properly initialized. Please check your parameters.") from e

    def _create_bucket(self, bucket_name):
        """
        Create necessary buckets in InfluxDB if they do not exist.
        """
        self._check_initiated()
        try:
            bucket = self.buckets_api.find_bucket_by_name(bucket_name)
            if not bucket:
                self.logger.debug(f"Creating bucket: {bucket_name}")
                retention_rules = BucketRetentionRules(type="expire", every_seconds=0)  # never expire, TODO handle downsampling separately
                self.buckets_api.create_bucket(bucket_name=bucket_name, retention_rules=retention_rules, org=self.org)
            else:
                self.logger.debug(f"Bucket '{bucket_name}' already exists")
        except Exception as e:
            self.logger.error(f"Error creating bucket: {e}")
            raise e

    def _connect_influxdb(self):
        """
        Connect to InfluxDB using the provided parameters.
        """
        if not all([self.url, self.token, self.org]):
            raise ValueError("InfluxDB connection parameters are not fully provided.")
        self.logger.debug("Connecting to InfluxDB...")
        self.client = InfluxDBClient(url=self.url, token=self.token, org=self.org) # type: ignore
        self.write_api = self.client.write_api()
        self.buckets_api = self.client.buckets_api()
        self.logger.debug("Connected to InfluxDB successfully. Checking buckets...")
        self._create_bucket(self.devices_bucket)
        self._create_bucket(self.states_bucket)

    def _logger(self):
        """
        Configure the logger for the client.
        """
        handler = colorlog.StreamHandler()
        handler.setFormatter(colorlog.ColoredFormatter(
            '%(asctime)s [%(log_color)s%(levelname)s%(reset)s]: %(message)s'))
        
        logger = colorlog.getLogger('AiraHomeClient')
        logger.addHandler(handler)
        logger.setLevel(colorlog.DEBUG)
        self.logger = logger
        logger.debug("Logger initialized successfully.")

    @staticmethod
    def _time_convert(time_str):
        return datetime.fromisoformat(time_str.replace("Z", "+00:00"))

    @staticmethod
    def add_field_auto(point, fields, data):
        for item in fields:
            #logger.debug(f"{item}, {data.get(item)}")
            point = point.field(item, data.get(item))
        return point

    def _should_retry(self):
        if time.time() - self.last_auth_time > 60*5: # type: ignore # 5 minutes
            return True
        return False

    def aira_auth(self):
        """
        Authenticate with AiraHome using the provided username and password.
        """
        if not all([self.username, self.password]):
            raise ValueError("Username and password must be provided for authentication.")
        self.last_auth_time = time.time()
        try:
            self.logger.debug("Authenticating with AiraHome...")
            self.aira = AiraHome()
            self.aira.login_with_credentials(self.username, self.password) # type: ignore
            self.logger.info("AiraHome authenticated successfully.")
            self.authenticated = True
        except AuthenticationError as e:
            self.logger.error(f"Authentication failed: {e}")

    def close(self):
        """
        Close the InfluxDB client connection and any other resources.
        """
        if hasattr(self, 'client'):
            self.client.close()
            self.logger.info("InfluxDB client connection closed.")
        else:
            self.logger.warning("InfluxDB client was not initialized, nothing to close.")
        self.logger.info("AiraHomeClient closed successfully.")

    def aira_task(self):
        if not self.authenticated:
            if self._should_retry():
                self.logger.info("Re-authenticating with AiraHome...")
                self.aira_auth()
                if not self.authenticated:
                    self.logger.info("AiraHome authentication failed. Retrying in 5 minutes...")
                    return
            else:
                self.logger.debug("Waiting before trying to relog...")
                return

        try:
            devices = self.aira.get_devices() # type: ignore
        except Exception as e:
            self.logger.error(f"Error fetching devices: '{e}'. Assuming authentication failed.")
            self.authenticated = False
            self.last_auth_time = time.time()  # Reset last auth time
            return
        final_time = None
        for device in devices['devices']:
            points = []
            device_point = (
                            Point("heat_pump")
                            .tag("id", device['id']['value'])
                            .field("online", device['online']['online'])
                        )
            points.append((self.devices_bucket, device_point))
            if device['online']['online']:
                states = self.aira.get_states(device['id']['value'])['heat_pump_states'][0] # type: ignore

                # HEATPUMP
                heatpump_point = self.add_field_auto(
                                                Point("heat_pump").tag("id", device['id']['value']),
                                                ["current_outdoor_temperature",
                                                "led_pattern",
                                                "manual_mode_enabled",
                                                "operating_status",
                                                "allowed_pump_mode_state",
                                                "night_mode_enabled",
                                                "configured_pump_modes",
                                                "pump_active_state",
                                                "inline_heater_active",
                                                "away_mode_enabled",
                                                "power_preference"],
                                                states
                                                )                    
                heatpump_point = self.add_field_auto(heatpump_point,
                                                ["hp_has_some_alarm",
                                                    "hp_has_stopping_alarms",
                                                    "hp_has_acknowledgeable_alarms",
                                                    "compressor_has_stopping_alarm"],
                                                states.get("error_metadata", {})
                                                )
                
                heatpump_point = heatpump_point.field("signature_element_enabled", states.get("signature_element", {}).get("enabled"))
                points.append((self.states_bucket, heatpump_point))

                # DHW
                water_heater_point = self.add_field_auto(
                                                Point("water_heater").tag("id", device['id']['value']),
                                                ["target_hot_water_temperature",
                                                "current_hot_water_temperature"],
                                                states
                                            )
                water_heater_point = water_heater_point.field("hot_water_heating_enabled", states.get("hot_water", {}).get("heating_enabled"))
                water_heater_point = water_heater_point.field("force_heating_enabled", states.get("force_heating", {}).get("enabled"))
                points.append((self.states_bucket, water_heater_point))

                # VERSIONS
                version_point = self.add_field_auto(
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
                points.append((self.states_bucket, version_point))
                
                # ERRORS
                for error in states.get("errors", []):
                    if not error.get("ccv"):
                        continue
                    error_point = (
                                        Point("error").tag("id", device['id']['value'])
                                        .tag("severity", error.get("severity"))
                                        .tag("ccv", error.get("ccv"))
                                        .field("active", True)
                                        )
                    points.append((self.states_bucket, error_point))
                
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
                    zone_points[tid] = self.add_field_auto(zone_points[tid],
                                                        ["article_number",
                                                        "serial_number",
                                                        "rssi"],
                                                        thermostat)
                    
                    zone_points[tid] = self.add_field_auto(zone_points[tid],
                                                        ["warning_low_battery_level"],
                                                        thermostat.get("last_update", {}))

                    zone_points[tid] = self.add_field_auto(zone_points[tid],
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
                    points.append((self.states_bucket, zone_point))

                # Write
                final_time = datetime.now(timezone.utc)
                for (bucket, point) in points:
                    point = point.time(final_time, WritePrecision.S)
                    self.write_api.write(bucket=bucket, org=self.org, record=point)
        if final_time:
            self.logger.info(f"Data written to InfluxDB for {len(devices['devices'])} device(s) at {final_time.isoformat()}")

def main():
    """
    Main function to run the AiraHomeClient.
    """
    client = AiraHomeClient()
    client.logger.info("Adding AiraHomeClient task schedule...")
    schedule.every().minute.at(":00").do(client.aira_task)
    while True:
        try:
            schedule.run_pending()
            time.sleep(1)
        except KeyboardInterrupt:
            client.logger.info("Shutting down (CTRL+C detected)...")
            client.close()
            break

if __name__ == "__main__":
    main()
