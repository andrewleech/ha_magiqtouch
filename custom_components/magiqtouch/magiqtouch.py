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
from functools import partial
from itertools import chain
from pathlib import Path
from typing import Optional, Callable

from .structures import RemoteStatus, SystemDetails
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
        self._zone_coolers = dict()
        self._zone_heaters = dict()

        self._update_listener = None
        self._update_listener_override = None

        self.logged_in = False

        self.ws: aiohttp.ClientWebSocketResponse = None
        self.pending_setting: Optional[SettingJob] = None
        self.ws_handler_task = None

        self.verbose = True

    async def shutdown(self):
        _LOGGER.info("shutdown")
        if self.ws_handler_task:
            self.ws_handler_task.cancel()

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
        for _ in range(10):
            if self.ws:
                break
            await asyncio.sleep(1)
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

            # Cognito.authenticate() isn't fully Async. Boto3 is eventually used and has blocking IO
            await asyncio.to_thread(asyncio.run, self._cognito.authenticate(self._password))

        except Exception as ex:
            if "UserNotFoundException" in str(ex) or "NotAuthorizedException" in str(ex):
                _LOGGER.exception("Error with login email/password", ex)
                return False
            raise

        self._AccessToken = self._cognito.access_token
        self._RefreshToken = self._cognito.refresh_token
        self._IdToken = self._cognito.id_token

        self.logged_in = True
        return True

    async def ws_start(self):
        # if self.hass:
        #    self.ws_handler_task = self.hass.async_create_task(self.ws_handler())
        # else:
        self.ws_handler_task = asyncio.create_task(self.ws_handler())

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
            _LOGGER.info("previous job replaced")
        self.pending_setting = job

        if self.ws and not self.ws.closed:
            await self.ws.send_str(message)
        else:
            _LOGGER.info("ws not open yet")
        # if not open, the pending job will be
        # sent when it does open

        try:
            await asyncio.wait_for(job.event.wait(), timeout)
            if self.verbose:
                _LOGGER.info("ws sent and received: %s\n%s" % (message, self.current_state))
            return True
        except asyncio.TimeoutError:
            msg = ""
            if isinstance(job.status, str):
                msg = job.status
            elif job.status == 0:
                msg = "No response"
            else:
                msg = f"Unexpected state after {job.status} responses"
            _LOGGER.warning(f"set job timeout after {timeout}s: {msg}")
        # if self.ws:
        #    await self.ws.close()
        return False

    async def send_pending(self):
        if self.pending_setting:
            _LOGGER.info("ws pending message send")
            message = self.pending_setting.message
            await self.ws.send_str(message)

    async def ws_handler(self):
        while True:
            token = await self._get_token()
            headers = {"user-agent": "Dart/3.2 (dart:io)", "sec-websocket-protocol": "wasp"}
            # async with aiohttp.ClientSession(trust_env=True) as session:
            counter = 0
            timeout = int(SCAN_INTERVAL.total_seconds() * 1.25)

            try:
                async with self.httpsession.ws_connect(
                    WebsocketUrl + token,
                    headers=headers,
                    autoping=False,
                    autoclose=False,
                    timeout=timeout,
                    # ssl=False
                ) as ws:
                    self.ws = ws
                    _LOGGER.info("websocket connected")
                    if self.pending_setting:
                        asyncio.create_task(self.send_pending())
                    # json.dumps({"action": "status", "params": {"device": self._mac_address}})
                    # )

                    connected_time = time.time()
                    while msg := await asyncio.wait_for(ws.receive(), timeout):
                        counter += 1
                        if msg.type in (
                            aiohttp.WSMsgType.CLOSE,
                            aiohttp.WSMsgType.CLOSING,
                            aiohttp.WSMsgType.CLOSED,
                        ):
                            _LOGGER.info(
                                f"ws: received close request after "
                                f"{counter} {msg} {msg.type} {msg.data}"
                                f"{counter} {msg} {msg.type} {msg.data}"
                            )
                            break
                        elif msg.type == aiohttp.WSMsgType.TEXT:
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
                                    _LOGGER.info(f"received but no match: {status}")
                                    if isinstance(self.pending_setting.status, int):
                                        self.pending_setting.status += 1
                                    if time.time() > self.pending_setting.timeout:
                                        # timeout
                                        self.pending_setting = None

                            if not self.pending_setting:
                                try:
                                    self.process_new_state(status)
                                except:
                                    _LOGGER.exception("process_new_state failed")
                                else:
                                    _LOGGER.info("state processed")

                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            _LOGGER.warning(msg)
                            break
                        else:
                            _LOGGER.warning(f"ws unexpected: {msg}")

                        if (time.time() - connected_time) > (45 * 60):
                            # cognito auth token lasts (default) 1 hour.
                            # re-start websocket before we get too close to this.
                            _LOGGER.info("cognito refresh")
                            break

            except asyncio.CancelledError:
                # Shutting Down
                return
            except RuntimeError as ex:
                if "Session is closed" in str(ex):
                    # Shutting Down
                    return
                _LOGGER.exception("websocket")
            except asyncio.TimeoutError:
                _LOGGER.warning(f"websocket timeout after {counter} messages.")
            except:
                _LOGGER.exception("websocket")
            self.ws = None
            _LOGGER.info("websocket has closed")

    async def logout(self):
        # TODO does an actually logout help?
        await self.shutdown()

    async def get_system_details(self):
        ## Get system data & MACADDRESS
        try:
            headers = await self._get_auth(self._IdToken)
            redacted = content = None
            async with self.httpsession.get(
                ApiUrl + "devices/system",
                headers=headers,  # {"Authorization": self._cognito.id_token},
            ) as rsp:
                system_data = (await rsp.json())[0]
                if not isinstance(system_data, dict):
                    content = await rsp.text()
                    raise ValueError(f"Error reading System State: {content}")
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
        # Cognito isn't fully Async. Boto3 is eventually used and has blocking IO
        await asyncio.to_thread(asyncio.run, self._cognito.check_token(renew=True))
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
            checker = lambda state: (bool(state.runningMode) and state.timestamp != ts)
            if await self.ws_send_job(msg, checker, timeout=20 if initial else 8):
                # if await self.wait_for_new_state(checker, timeout=8):
                break

    def process_new_state(self, new_state):
        if self._update_listener_override:
            logger = _LOGGER.warning if self.verbose else _LOGGER.debug
            logger("State watching: %s" % new_state)
            return self._update_listener_override(new_state)

        if self.verbose and new_state != self.current_state:
            _LOGGER.warning(f"Current State: {new_state}")

        self.current_state.update(new_state)

        if self._update_listener:
            _LOGGER.debug("State updated: %s" % new_state)
            self._update_listener()

    def new_remote_props(self, state=None):
        state = state or self.current_state
        now = datetime.utcnow()
        timestamp = int(now.replace(tzinfo=timezone.utc).timestamp())
        state.timestamp = timestamp

        data = {
            "action": "command",
            "params": state.to_dict(),
        }
        return data

    @staticmethod
    def state_checker(state, units, zone, field, value):
        check = state.cooler if "c" in units else []
        if "h" in units:
            check.extend(state.heater)
        if not check:
            if getattr(state, field) != value:
                return False
        for u in check:
            if not MagiQtouch_Driver.zone_match(u, zone):
                continue
            if getattr(u, field) != value:
                return False
        return True

    async def send_current_state(self, checker, data=None):
        ts = self.current_state.timestamp
        data = data or self.new_remote_props()
        jdata = json.dumps(data)
        if not checker:
            checker = (lambda state: state.timestamp != ts,)

        _LOGGER.info("sending new settings")
        await self.ws_send(jdata, checker)

    def get_zone_name(self, zone):
        if not zone:
            return ""
        if isinstance(zone, ZoneType):
            return zone.label
        return zone

    @property
    def zone_list(self):
        if not self._zone_list:
            if self.current_system_state.NoOfZoneControls == 0:
                return [ZONE_TYPE_NONE]
            self._zone_list = []
            # Always createa common / master entity
            zones: set[str | ZoneType] = {ZONE_TYPE_COMMON}  # Use set to provide de-duplication
            for d in self.current_state.cooler + self.current_state.heater:
                if d.zoneType != ZONE_TYPE_COMMON.label:
                    zones.add(d.name)
            self._zone_list.extend(list(zones))
        return self._zone_list

    @staticmethod
    def zone_match(dev, zone):
        return (
            zone.label == dev.zoneType
            if isinstance(zone, ZoneType)
            else zone == dev.name
            if isinstance(zone, str)
            else True
        )

    def available_coolers(self, zone):
        if zone not in self._zone_coolers:
            self._zone_coolers[zone] = [
                d for d in self.current_state.cooler if self.zone_match(d, zone)
            ]
            _LOGGER.debug(f"self._zone_coolers: {self._zone_coolers}")

        return self._zone_coolers[zone]

    def available_heaters(self, zone):
        if zone not in self._zone_heaters:
            self._zone_heaters[zone] = [
                d for d in self.current_state.heater if self.zone_match(d, zone)
            ]
            _LOGGER.debug(f"self._zone_heaters: {self._zone_heaters}")

        return self._zone_heaters[zone]

    def active_device(self, zone=ZONE_TYPE_NONE, state=None):
        # if a zone has both heater and cooler, return the one
        # that matches system state.
        # Otherwise just return the device that's in zone.
        # devices = self.available_coolers(zone) + self.available_heaters(zone)
        # if not devices:
        #    raise ValueError(f"invalid zone: {state}")
        state = state or self.current_state
        if state.runningMode in (MODE_COOLER, MODE_COOLER_FAN):
            devices = (
                self.available_coolers(zone)
                or self.available_heaters(zone)
                or self.current_state.cooler
                or self.current_state.heater
            )
        elif state.runningMode in (MODE_HEATER, MODE_HEATER_FAN):
            devices = (
                self.available_heaters(zone)
                or self.available_coolers(zone)
                or self.current_state.heater
                or self.current_state.cooler
            )
        elif state.runningMode == "":
            raise ValueError(f"state not yet read: {state.runningMode}")
        else:
            raise ValueError(f"active device unknown mode: {state}")
        if devices:
            return devices[0]
        else:
            raise ValueError(f"active device unknown for '{zone}': {state}")

    async def set_off(self):
        self.current_state.systemOn = False
        checker = lambda state: (not state.systemOn)
        await self.send_current_state(checker)

    async def set_on(self):
        self.current_state.systemOn = True
        checker = lambda state: bool(state.systemOn)
        await self.send_current_state(checker)

    def get_zone_onoff(self, zone):
        """Returns specific zone on and off."""
        device = self.active_device(zone)
        return self.current_state.systemOn and device and device.zoneOn

    async def set_zone_onoff(self, zone, is_on):
        """Turns a specific zone on and off."""
        if zone and zone in (ZONE_TYPE_COMMON, ZONE_TYPE_NONE):
            on_state = None
            return
        on_state = bool(is_on)
        for device in chain(self.available_coolers(zone), self.available_heaters(zone)):
            device.zoneOn = on_state
        checker = partial(
            self.state_checker, units="hc", zone=zone, field="zoneOn", value=on_state
        )
        if is_on:
            # if any zone is on, system needs to be on
            self.current_state.systemOn = True
        else:
            # if all zones are off, turn off system
            all_dev = chain(self.current_state.cooler, self.current_state.heater)
            if not [d for d in all_dev if d.zoneOn]:
                _LOGGER.info("All zones off, turning system off")
                self.current_state.systemOn = False

        _LOGGER.info(f"set_zone_onoff {zone}={is_on} = {self.current_state}")
        await self.send_current_state(checker)

    async def set_fan_only(self, zone=ZONE_TYPE_NONE):
        runningMode = self.current_state.runningMode
        if runningMode in (MODE_COOLER, MODE_COOLER_FAN):
            await self.set_fan_only_evap(zone)
        elif runningMode in (MODE_HEATER, MODE_HEATER_FAN):
            await self.set_fan_only_heater(zone)
        else:
            _LOGGER.error(f"Don't know how to turn on fan from runningMode: {runningMode}")

    def _reset_device_state(self, zone):
        for device in chain(self.available_coolers(zone), self.available_heaters(zone)):
            device.runningState = "NOT_REQUIRED"
            device.zoneRunningState = "NOT_REQUIRED"

    async def set_fan_only_evap(self, zone=ZONE_TYPE_NONE):
        self.current_state.systemOn = True
        self.current_state.runningMode = MODE_COOLER_FAN
        self._reset_device_state(zone)
        checker = lambda state: (
            state.systemOn and self.current_state.runningMode == MODE_COOLER_FAN
        )
        await self.send_current_state(checker)

    async def set_fan_only_heater(self, zone=ZONE_TYPE_NONE):
        self.current_state.systemOn = True
        self.current_state.runningMode = MODE_HEATER_FAN
        self._reset_device_state(zone)
        checker = lambda state: (
            state.systemOn and self.current_state.runningMode == MODE_HEATER_FAN
        )
        await self.send_current_state(checker)

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

        await self.send_current_state(checker)

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

        await self.send_current_state(checker)

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

    #     await self.send_current_state(checker)

    async def set_current_speed(self, speed, zone=ZONE_TYPE_NONE):
        speed = int(speed)
        for unit in chain(self.current_state.cooler, self.current_state.heater):
            unit.fan_speed = speed
        # checker = lambda state: self.active_device(zone, state).fan_speed == speed
        checker = partial(
            self.state_checker, units="hc", zone=None, field="fan_speed", value=speed
        )
        await self.send_current_state(checker)

    async def set_temperature(self, new_temp, zone=ZONE_TYPE_NONE):
        new_temp = int(new_temp)
        if device := self.active_device(zone):
            device.set_temp = new_temp
            # checker = lambda state: self.active_device(state, zone).set_temp == new_temp
            units = "h"
            if self.current_state.runningMode in (MODE_COOLER, MODE_COOLER_FAN):
                units = "c"
            checker = partial(
                self.state_checker, units=units, zone=zone, field="set_temp", value=new_temp
            )
            await self.send_current_state(checker)

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
