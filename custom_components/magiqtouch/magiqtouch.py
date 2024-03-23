if __name__ == "__main__":
    import sys
    from pathlib import Path

    __vendor__ = str(Path(__file__).parent / "vendor")
    sys.path.append(__vendor__)

import argparse
import copy
import json
import time
import asyncio
import logging
import aiohttp
from mandate import Cognito
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Callable

from .structures import RemoteStatus, SystemDetails, UnitDetails
from .const import (
    SCAN_INTERVAL,
    MODE_COOLER,
    MODE_COOLER_FAN,
    MODE_HEATER,
    MODE_HEATER_FAN,
    CONTROL_MODE_FAN,
    CONTROL_MODE_TEMP,
    ZoneType,
    ZONE_TYPE_NONE,
    ZONE_TYPE_COMMON,
)

AWS_REGION = "ap-southeast-2"
AWS_USER_POOL_ID = "ap-southeast-2_uw5VVNlib"
# cognito_userpool_client_id = "6e1lu9fchv82uefiarsp0290v9"
cognito_userpool_client_id = "afh7fftbb0fg2rnagdbgd9b7b"
ObsoleteApiUrl = "https://57uh36mbv1.execute-api.ap-southeast-2.amazonaws.com/api/"

# Sniffed from iOS app, used to replace older mqtt interface.
ApiUrl = "https://tgjgb3bcf3.execute-api.ap-southeast-2.amazonaws.com/prod" + "/v1/"

WebsocketUrl = "https://xs5z2412cf.execute-api.ap-southeast-2.amazonaws.com/prod?token="

_LOGGER = logging.getLogger("magiqtouch")


class MagiQtouch_Driver:
    def __init__(self, user, password):
        self._password = password
        self._user = user

        self._httpsession = None
        self.httpsession_created = False

        self._AccessToken = None
        self._RefreshToken = None
        self._IdToken = None

        self._IdentityId = None

        self._AccessKeyId = None
        self._SecretKey = None
        self._SessionToken = None

        self.current_state: RemoteStatus = RemoteStatus()
        self.current_system_state: SystemDetails = SystemDetails()
        self._zone_list = []

        self._update_listener = None
        self._update_listener_override = None

        self.logged_in = False

        self.ws: aiohttp.ClientWebSocketResponse = None
        self.pending_setting: Optional[SettingJob] = None

        self.verbose = True

    async def shutdown(self):
        if self.ws:
            _LOGGER.info("Closing Websocket")
            await self.ws.close()

        if self._httpsession and self.httpsession_created:
            _LOGGER.info("Closing http session")
            await self._httpsession.close()
            self._httpsession = None
            self.httpsession_created = False

    def set_verbose(self, verbose, initial=False):
        _LOGGER.setLevel(logging.INFO)
        self.verbose = verbose
        if verbose and not initial:
            _LOGGER.warning(f"Current System State: {self.current_system_state}")
            _LOGGER.warning(f"Current State: {self.current_state}")

    @property
    def httpsession(self):
        if self.hass:
            from homeassistant.helpers import aiohttp_client

            return aiohttp_client.async_get_clientsession(self.hass)
        else:
            if not self._httpsession:
                self._httpsession = aiohttp.ClientSession(trust_env=True)
                self.httpsession_created = True
            return self._httpsession

    async def startup(self, hass):
        await self.login(hass)
        await self.get_system_details()
        await self.ws_start()
        await self.full_refresh(initial=True)

    async def login(self, hass=None):
        self.hass = hass

        _LOGGER.info("Logging in...")

        # if httpsession:
        #   if self.httpsession is not httpsession and self.httpsession_created:
        #       await self.httpsession.close()
        #       self.httpsession = None
        #       self.httpsession_created = False
        #   self.httpsession = httpsession
        # elif not self.httpsession:
        #     self.httpsession = aiohttp.ClientSession(trust_env=True)
        #     self.httpsession_created = True
        try:
            # can also try
            # https://stackoverflow.com/questions/70503800/how-can-i-test-aws-cognito-protected-apis-in-python

            ## First, login to cognito with MagiqTouch user/pass
            self._cognito = Cognito(
                user_pool_id=AWS_USER_POOL_ID,
                client_id=cognito_userpool_client_id,
                user_pool_region=AWS_REGION,
                username=self._user,
                # Dummy credentials to bypass EC2 IMDS
                access_key="AKIAIOSFODNN7EXAMPLE",
                secret_key="wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            )

            await self._cognito.authenticate(self._password)
        except Exception as ex:
            if "UserNotFoundException" in str(ex) or "NotAuthorizedException" in str(ex):
                _LOGGER.exception("Error with login email/password", ex)
                return False
            raise

        self._AccessToken = self._cognito.access_token
        self._RefreshToken = self._cognito.refresh_token
        self._IdToken = self._cognito.id_token

        self.logged_in = True
        _LOGGER.warning("Logged in")
        return True

    async def ws_start(self):
        if self.hass:
            self.hass.async_create_task(self.ws_handler())
        else:
            asyncio.create_task(self.ws_handler())

    async def ws_send(self, message, checker):
        if self.hass:
            self.hass.async_create_task(self.ws_send_job(message, checker))
        else:
            asyncio.create_task(self.ws_send_job(message, checker))

    async def ws_send_job(self, message, checker, timeout=8):
        job = SettingJob(
            message=message,
            checker=checker,
            status=0,
            event=asyncio.Event(),
            timeout=time.time() + timeout,
        )
        if self.pending_setting:
            self.pending_setting.status = "replaced"
            self.pending_setting.event.set()
        self.pending_setting = job

        if self.ws and not self.ws.closed:
            # _LOGGER.info("restart websocket")
            await self.ws.send_str(message)
        # if not open, the pending job will be
        # sent when it does ope

        try:
            await asyncio.wait_for(job.event.wait(), timeout)
            if self.verbose:
                _LOGGER.warning("Sent and checked: %s\n%s" % (message, self.current_state))
            return True
        except asyncio.TimeoutError:
            msg = ""
            if isinstance(job.status, str):
                msg = job.status
            elif job.status == 0:
                msg = "No response"
            else:
                msg = f"Unexpected state after {job.status} responses"
            _LOGGER.warning(f"setting job timeout: {msg}")
        if self.ws:
            await self.ws.close()
        return False

    async def ws_handler(self):
        _LOGGER.warning("websocket start")
        while True:
            token = await self._get_token()
            headers = {"user-agent": "Dart/3.2 (dart:io)", "sec-websocket-protocol": "wasp"}
            # async with aiohttp.ClientSession(trust_env=True) as session:
            counter = 0

            try:
                async with self.httpsession.ws_connect(
                    WebsocketUrl + token,
                    headers=headers,
                    heartbeat=10,
                    # ssl=False
                ) as ws:
                    self.ws = ws
                    _LOGGER.info("websocket connected")
                    if self.pending_setting:
                        _LOGGER.warning("sending pending message")
                        message = self.pending_setting.message
                        await ws.send_str(message)
                    # json.dumps({"action": "status", "params": {"device": self._mac_address}})
                    # )
                    timeout = SCAN_INTERVAL.total_seconds()
                    connected_time = time.time()
                    while msg := await asyncio.wait_for(ws.receive(), timeout):
                        counter += 1
                        if msg.type in (
                            aiohttp.WSMsgType.CLOSE,
                            aiohttp.WSMsgType.CLOSING,
                            aiohttp.WSMsgType.CLOSED,
                        ):
                            _LOGGER.warning("ws: received close request")
                            break
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            data = json.loads(msg.data)
                            # _LOGGER.info(f"ws: {msg.data}")
                            status = RemoteStatus.from_dict(data)
                            # _LOGGER.info(f"ws: {str(status)}")
                            if self.pending_setting:
                                if self.pending_setting.checker(status):
                                    self.pending_setting.status = "confirmed"
                                    self.pending_setting.event.set()
                                    self.pending_setting = None
                                else:
                                    _LOGGER.warning(f"received but no match: {status}")
                                    if isinstance(self.pending_setting.status, int):
                                        self.pending_setting.status += 1
                                    if time.time() > self.pending_setting.timeout:
                                        # timeout
                                        self.pending_setting = None

                            if not self.pending_setting:
                                _LOGGER.info("state processed")
                                self.process_new_state(status)
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            break
                        if (time.time() - connected_time) > (45 * 60):
                            # cognito auth token lasts (default) 1 hour.
                            # re-start websocket before we get too close to this.
                            break
            except asyncio.TimeoutError:
                _LOGGER.info(f"websocket timeout after {counter} messages.")
            except:
                _LOGGER.exception("websocket")
            self.ws = None
            _LOGGER.info("websocket has closed")

    async def logout(self):
        # TODO does an actually logout help?
        await self.shutdown()
        # todo is this called by HA

    async def get_system_details(self):
        ## Get system data & MACADDRESS
        try:
            headers = await self._get_auth(self._IdToken)
            redacted = None
            async with self.httpsession.get(
                ApiUrl + "devices/system",
                headers=headers,  # {"Authorization": self._cognito.id_token},
            ) as rsp:
                system_data = (await rsp.json())[0]
                redacted = copy.deepcopy(system_data)
                redacted["System"]["Address"] = "<redacted>"
                redacted["Wifi_Module"]["MacAddressId"] = "<redacted>"
                if self.verbose:
                    _LOGGER.warning(f"Current System State: {json.dumps(redacted)}")
                # parse the json into dataclass after its logged in case of errors
                self.current_system_state = SystemDetails.from_dict(system_data)
                self._mac_address = self.current_system_state.Wifi_Module.MacAddressId

        except Exception:
            _LOGGER.exception("failed to query devices/system")
            if redacted:
                _LOGGER.error(f"Current System State: {json.dumps(redacted)}")
            raise

    async def _get_token(self):
        await self._cognito.check_token(renew=True)
        return self._cognito.id_token

    async def _get_auth(self, token=None):
        token = token or await self._get_token()
        return {"Authorization": f"Bearer {token}"}

    def set_listener(self, listener):
        self._update_listener = listener

    async def refresh_state(self, force=False):
        if force or not self.ws or self.ws.closed:
            await self.full_refresh()

    async def full_refresh(self, initial=False):
        if not self.logged_in:
            raise ValueError("Not logged in")

        ts = 0 if initial else self.current_state.timestamp
        msg = json.dumps({"action": "status", "params": {"device": self._mac_address}})
        for _retry in range(3):
            checker = lambda state: (state.runningMode and state.timestamp != ts)
            if await self.ws_send_job(msg, checker):
                # if await self.wait_for_new_state(checker, timeout=8):
                break
            # no confirmation, retry
            if self.ws:
                await self.ws.close()

    def process_new_state(self, new_state):
        # _LOGGER.warning(f"process_new_state: {new_state}")
        if self._update_listener_override:
            logger = _LOGGER.warning if self.verbose else _LOGGER.debug
            logger("State watching: %s" % new_state)
            return self._update_listener_override(new_state)
        elif self._update_listener:
            _LOGGER.debug("State updated: %s" % new_state)
            self._update_listener()
        if self.verbose and new_state != self.current_state:
            _LOGGER.warning(f"Current State: {new_state}")
        self.current_state = new_state

    def new_remote_props(self, state=None):
        state = state or self.current_state
        now = datetime.utcnow()
        timestamp = int(now.replace(tzinfo=timezone.utc).timestamp())
        state.timestamp = timestamp

        data = {
            "action": "command",
            "params": state.to_dict(),
        }
        # todo zone support
        # data["params"]["selectedZone"] = 0

        # for zone in range(10):
        #     setattr(
        #         data, f"OnOffZone{zone + 1}", getattr(state, f"OnOffZone{zone + 1}")
        #     )
        #     setattr(
        #         data, f"TempZone{zone + 1}", getattr(state, f"SetTempZone{zone + 1}")
        #     )
        #     setattr(
        #         data,
        #         f"Override{zone + 1}",
        #         getattr(state, f"ProgramModeOverriddenZone{zone + 1}"),
        #     )

        return data

    async def _send_remote_props(self, data=None, checker=None):
        ts = self.current_state.timestamp
        data = data or self.new_remote_props()
        jdata = json.dumps(data)
        # update_lock = asyncio.Event()
        # if checker:
        #      async def override_listener(new_state):
        #         nonlocal checker, update_lock, self
        #         _LOGGER.warning(f"listen: {new_state}")
        #         if checker(new_state):
        #             _LOGGER.warning("true")
        #             self.current_state = new_state
        #             update_lock.set()
        #         else:
        #             _LOGGER.warning("false")
        #             asyncio.create_task(self.refresh_state())

        #     self._update_listener_override = override_listener

        if not checker:
            checker = lambda state: state.timestamp != ts

        # headers = await self._get_auth()
        # async with self.httpsession.put(
        #     ApiUrl + f"devices/{self._mac_address}",
        #     headers=headers,
        #     data=jdata,
        # ) as rsp:
        #     _LOGGER.debug(f"Update response received: {rsp.json()}")
        _LOGGER.warning("sending new settings")
        await self.ws_send(jdata, checker)

    def get_zone_name(self, zone):
        if not zone:
            return ""
        if isinstance(zone, ZoneType):
            return zone.name
        return zone

    @property
    def zone_list(self):
        if not self._zone_list:
            if self.current_system_state.NoOfZoneControls == 0:
                return [ZONE_TYPE_NONE]
            self._zone_list = []
            zones = set()  # Use set to provide de-duplication
            for d in self.current_state.cooler + self.current_state.heater:
                if d.zoneType == ZONE_TYPE_COMMON:
                    self._zone_list = [ZONE_TYPE_COMMON]
                else:
                    zones.add(d.name)
            self._zone_list.extend(list(zones))
        return self._zone_list

    @staticmethod
    def zone_match(dev, zone):
        return (
            dev.zoneType == zone
            if isinstance(zone, ZoneType)
            else dev.name == zone
            if isinstance(zone, str)
            else True
        )

    def available_coolers(self, zone):
        return [d for d in self.current_state.cooler if self.zone_match(d, zone)]

    def available_heaters(self, zone):
        return [d for d in self.current_state.heater if self.zone_match(d, zone)]

    def active_device(self, state, zone=ZONE_TYPE_NONE):
        # if a zone has both heater and cooler, return the one
        # that matches system state.
        # Otherwise just return the device that's in zone.
        devices = self.available_coolers(zone) + self.available_heaters(zone)
        if not devices:
            raise ValueError(f"invalid zone: {state}")

        if state.runningMode in (MODE_COOLER, MODE_COOLER_FAN):
            return devices[0]
        elif state.runningMode in (MODE_HEATER, MODE_HEATER_FAN):
            return devices[-1]
        else:
            _LOGGER.error(f"active device unknown mode: {state.runningMode}")
            raise ValueError(f"active device unknown mode: {state}")
        raise ValueError(f"No active devices found for zone '{zone}' in state: {state}")
        return UnitDetails()

    def current_device_state(self, zone=ZONE_TYPE_NONE):
        return self.active_device(self.current_state, zone)

    async def set_off(self):
        self.current_state.systemOn = False
        checker = lambda state: (not state.systemOn)
        await self._send_remote_props(checker=checker)

    async def set_on(self):
        self.current_state.systemOn = True
        checker = lambda state: bool(state.systemOn)
        await self._send_remote_props(checker=checker)

    def get_zone_state(self, zone):
        """Returns specific zone on and off."""
        device = self.current_device_state(zone)
        return self.current_state.systemOn and device.zoneOn

    async def set_zone_state(self, zone, is_on):
        """Turns a specific zone on and off."""
        device = self.current_device_state(zone)
        on_state = bool(is_on)
        device.zoneOn = on_state
        checker = lambda state: self.active_device(state, zone).zoneOn == on_state
        if is_on:
            # if any zone is on, system needs to be on
            self.current_state.systemOn = True
        else:
            # if all zones are off, turn off system
            all_dev = self.current_state.cooler + self.current_state.heater
            if not [d for d in all_dev if d.zoneOn]:
                _LOGGER.warning("All zones off, turning system off")
                self.current_state.systemOn = False

        _LOGGER.warning(f"set_zone_state {zone}={is_on} = {self.current_state}")
        await self._send_remote_props(checker=checker)

    async def set_fan_only(self, zone=ZONE_TYPE_NONE):
        runningMode = self.current_state.runningMode
        if runningMode in (MODE_COOLER, MODE_COOLER_FAN):
            await self.set_fan_only_evap(zone)
        elif runningMode in (MODE_HEATER, MODE_HEATER_FAN):
            await self.set_fan_only_heater(zone)
        else:
            _LOGGER.error(f"Don't know how to turn on fan from runningMode: {runningMode}")

    def _reset_device_state(self, zone):
        for device in self.available_coolers(zone) + self.available_heaters(zone):
            device.runningState = "NOT_REQUIRED"
            device.zoneRunningState = "NOT_REQUIRED"

    async def set_fan_only_evap(self, zone=ZONE_TYPE_NONE):
        self.current_state.systemOn = True
        self.current_state.runningMode = MODE_COOLER_FAN
        self._reset_device_state(zone)
        checker = lambda state: (
            state.systemOn and self.current_state.runningMode == MODE_COOLER_FAN
        )
        await self._send_remote_props(checker=checker)

    async def set_fan_only_heater(self, zone=ZONE_TYPE_NONE):
        self.current_state.systemOn = True
        self.current_state.runningMode = MODE_HEATER_FAN
        self._reset_device_state(zone)
        checker = lambda state: (
            state.systemOn and self.current_state.runningMode == MODE_HEATER_FAN
        )
        await self._send_remote_props(checker=checker)

    async def set_heating_by_temperature(self, zone=ZONE_TYPE_NONE):
        for heater in self.available_heaters(zone):
            heater.control_mode = CONTROL_MODE_TEMP
        await self.set_heating()

    async def set_heating_by_speed(self, zone=ZONE_TYPE_NONE):
        for heater in self.available_heaters(zone):
            heater.control_mode = CONTROL_MODE_FAN
        await self.set_heating()

    async def set_heating(self, zone=ZONE_TYPE_NONE):
        self.current_state.systemOn = True
        self.current_state.runningMode = MODE_HEATER
        self._reset_device_state(zone)
        for heater in self.available_heaters(zone):
            heater.runningState = "REQUIRED_RUNNING"
            heater.zoneRunningState = "REQUIRED_RUNNING"

        def checker(state):
            return state.systemOn and state.runningMode == MODE_HEATER

        await self._send_remote_props(checker=checker)

    async def set_cooling_by_temperature(self, zone=ZONE_TYPE_NONE):
        for cooler in self.available_coolers(zone):
            cooler.control_mode = CONTROL_MODE_TEMP
        await self.set_cooling()

    async def set_cooling_by_speed(self, zone=ZONE_TYPE_NONE):
        for cooler in self.available_coolers(zone):
            cooler.control_mode = CONTROL_MODE_FAN
        await self.set_cooling()

    async def set_cooling(self, zone=ZONE_TYPE_NONE):
        self.current_state.systemOn = True
        self.current_state.runningMode = MODE_COOLER
        self._reset_device_state(zone)
        for cooler in self.available_coolers(zone):
            cooler.runningState = "REQUIRED_RUNNING"
            cooler.zoneRunningState = "REQUIRED_RUNNING"

        def checker(state):
            return state.systemOn and state.runningMode == MODE_COOLER

        await self._send_remote_props(checker=checker)

    # async def set_aoc_by_temperature(self, zone=ZONE_TYPE_NONE):
    #     for cooler in self.available_coolers(zone):
    #         cooler.control_mode = CONTROL_MODE_TEMP
    #     await self.set_add_on_cooler()

    # async def set_aoc_by_speed(self, zone=ZONE_TYPE_NONE):
    #     for cooler in self.available_coolers(zone):
    #         cooler.control_mode = CONTROL_MODE_FAN
    #     await self.set_add_on_cooler()

    # async def set_add_on_cooler(self):
    #     # todo don't know if this works, just a guess so far
    #     self.current_state.systemOn = True
    #     # if sys_state.AOCFixed.InSystem or sys_state.AOCInverter.InSystem:
    #     self.current_state.runningMode = MODE_COOLER_AOC
    #     change = [
    #         ("systemOn", True),
    #         ("runningMode", MODE_COOLER_AOC),
    #     ]

    #     def checker(state):
    #         nonlocal change
    #         return all((getattr(state, f) == v for f, v in change))

    #     await self._send_remote_props(checker=checker)

    async def set_current_speed(self, speed, zone=ZONE_TYPE_NONE):
        speed = int(speed)
        self.current_device_state(zone).fan_speed = speed
        checker = lambda state: self.active_device(state, zone).fan_speed == speed
        await self._send_remote_props(checker=checker)

    async def set_temperature(self, new_temp, zone=ZONE_TYPE_NONE):
        new_temp = int(new_temp)
        self.current_device_state(zone).set_temp = new_temp
        checker = lambda state: self.active_device(state, zone).set_temp == new_temp
        await self._send_remote_props(checker=checker)

    # def get_installed_device_config(self):
    #     # todo update attrs or delete function
    #     device = {}
    #     if self.current_system_state.HeaterInSystem:
    #         device = self.current_system_state.Heater
    #     elif self.current_system_state.AOCFixedInSystem:
    #         device = self.current_system_state.AOCFixed
    #     elif self.current_system_state.AOCInverterInSystem:
    #         device = self.current_system_state.AOCInverter
    #     elif self.current_system_state.NoOfEVAPInSystem > 0:
    #         device = self.current_system_state.EVAPCooler

    #     return device


@dataclass
class SettingJob:
    message: str
    checker: Callable
    status: int | str
    event: asyncio.Event
    timeout: float


def main():
    logging.basicConfig(level=logging.INFO)
    # Read in command-line parameters
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-e",
        "--email",
        required=True,
        help="Your Magiqtouch login email",
    )
    parser.add_argument(
        "-p",
        "--password",
        required=True,
        help="Your Magiqtouch login password",
    )

    import sys

    print(sys.argv)
    args = parser.parse_args()
    user = args.email
    password = args.password

    m = MagiQtouch_Driver(user=user, password=password)
    m.set_verbose(True, initial=True)

    loop = asyncio.get_event_loop()

    async def atest():
        try:
            await m.login()
            await m.refresh_state()
            while not m.current_state.timestamp:
                await asyncio.sleep(1)
                print(".", end="")
        finally:
            await m.shutdown()

    loop.run_until_complete(atest())

    # loop.run_until_complete(m.refresh_state())
    # time.sleep(2)

    print("")
    print("Current State:")
    print(str(m.current_state))
    print("")


if __name__ == "__main__":
    main()
