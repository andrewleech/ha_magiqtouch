if __name__ == "__main__":
    import sys
    from pathlib import Path
    __vendor__ = str(Path(__file__).parent / "vendor")
    sys.path.append(__vendor__)

import argparse
import json
import time
import asyncio
import logging
import threading
import aiohttp
from pprint import pp
from mandate import Cognito
from datetime import datetime
from pathlib import Path

try:
    from .structures import RemoteStatus, RemoteAccessRequest, SystemDetails
    from .exceptions import UnauthorisedTokenException
except ImportError:
    from structures import RemoteStatus, RemoteAccessRequest, SystemDetails
    from exceptions import UnauthorisedTokenException


AWS_REGION = "ap-southeast-2"
AWS_USER_POOL_ID = "ap-southeast-2_uw5VVNlib"
cognito_userpool_client_id = "6e1lu9fchv82uefiarsp0290v9"

ApiUrl = (
    "https://57uh36mbv1.execute-api.ap-southeast-2.amazonaws.com/api/"
)

# Sniffed from iOS app, used to replace older mqtt interface.
NewWebApiUrl = (
    "https://tgjgb3bcf3.execute-api.ap-southeast-2.amazonaws.com/prod"
    + "/v1/"
)

_LOGGER = logging.getLogger("magiqtouch")


class MagiQtouch_Driver:
    def __init__(self, user, password):
        self._password = password
        self._user = user

        self._httpsession = None

        self._AccessToken = None
        self._RefreshToken = None
        self._IdToken = None

        self._IdentityId = None

        self._AccessKeyId = None
        self._SecretKey = None
        self._SessionToken = None

        self.current_state: RemoteStatus = RemoteStatus()
        self.current_system_state: SystemDetails = SystemDetails()
        self._update_listener = None
        self._update_listener_override = None

        self.logged_in = False

        self.verbose = False

    def set_verbose(self, verbose, initial=False):
        self.verbose = verbose
        if verbose and not initial:
            _LOGGER.warn(f"Current System State: {json.dumps(self.current_system_state.__dict__)}")
            _LOGGER.warn(f"Current State: {self.current_state}")
    
    async def login(self, httpsession=None):
        _LOGGER.info("Logging in...")
        self._httpsession = httpsession or aiohttp.ClientSession()
        try:
            ## First, login to cognito with MagiqTouch user/pass
            self._cognito = Cognito(
                user_pool_id=AWS_USER_POOL_ID,
                client_id=cognito_userpool_client_id,
                user_pool_region=AWS_REGION,
                username=self._user,
                # Dummy credentials to bypass EC2 IMDS
                access_key='AKIAIOSFODNN7EXAMPLE',
                secret_key='wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
            )

            await self._cognito.authenticate(self._password)
        except Exception as ex:
            if "UserNotFoundException" in str(ex) or "NotAuthorizedException" in str(
                ex
            ):
                _LOGGER.exception("Error during auth", ex)
                return False
            raise

        self._AccessToken = self._cognito.access_token
        self._RefreshToken = self._cognito.refresh_token
        self._IdToken = self._cognito.id_token

        ## Get MACADDRESS
        headers = await self._get_auth()
        async with self._httpsession.get(
            ApiUrl + "loadmobiledevice", headers={"Authorization": self._cognito.id_token}
        ) as rsp:
            self._mac_address = (await rsp.json())[0]["MacAddressId"]
        _LOGGER.debug("MAC:", self._mac_address)
        
        self.logged_in = True
        return True

    async def logout(self):
        # TODO
        pass

    async def _get_auth(self):
        await self._cognito.check_token(renew=True)
        return {"Authorization": f"Bearer {self._cognito.id_token}"}

    async def initial_refresh(self):
        if not self.logged_in:
            raise ValueError("Not logged in")

        await self.refresh_state(initial=True)

    def set_listener(self, listener):
        self._update_listener = listener

    async def refresh_state(self, initial=False):
        headers = await self._get_auth()
        async with self._httpsession.put(
            NewWebApiUrl + f"devices/{self._mac_address}", headers=headers,
            data=json.dumps(
                {
                    "SerialNo": self._mac_address,
                    "Status": 1,
                }
            ),
        ) as rsp:
            if rsp.status == 401:
                raise UnauthorisedTokenException

        if initial:
            # Get system details so we can see how many zones are in use.
            async with self._httpsession.get(
                ApiUrl + f"loadsystemdetails?macAddressId={self._mac_address}", headers=headers
                ) as rsp:
                    if rsp.status == 401:
                        raise UnauthorisedTokenException
                    data = await rsp.json()
                    new_system_state = SystemDetails.from_dict(data)
                    self.current_system_state = new_system_state
                    if self.verbose:
                        _LOGGER.warn(f"Current System State: {json.dumps(self.current_system_state.__dict__)}")

        async with self._httpsession.get(
            ApiUrl + f"loadsystemrunning?macAddressId={self._mac_address}", headers=headers 
            ) as rsp:
                if rsp.status == 401:
                    raise UnauthorisedTokenException
                data = await rsp.json()
                new_state = RemoteStatus.from_dict(data)
                if self._update_listener_override:
                    _LOGGER.debug("State watching: %s" % new_state)
                    self._update_listener_override()
                elif self._update_listener:
                    _LOGGER.debug("State updated: %s" % new_state)
                    self._update_listener()
                if self.verbose and str(new_state) != str(self.current_state):
                    _LOGGER.warn(f"Current State: {new_state}")
                self.current_state = new_state

    def new_remote_props(self, state=None):
        state = state or self.current_state
        data = RemoteAccessRequest()
        data.SerialNo = state.MacAddressId
        data.TimeRequest = datetime.now().astimezone().isoformat()
        data.StandBy = 0 if state.SystemOn else 1
        data.EvapCRunning = state.EvapCRunning
        data.CTemp = state.CTemp
        data.CFanSpeed = state.CFanSpeed
        data.CFanOnly = state.CFanOnlyOrCool
        data.CThermosOrFan = 0 if state.CFanOnlyOrCool else state.FanOrTempControl
        data.HRunning = state.HRunning
        data.HTemp = state.HTemp
        data.HFanSpeed = state.HFanSpeed
        data.HFanOnly = state.HFanOnly
        data.FAOCRunning = state.FAOCRunning
        data.FAOCTemp = state.FAOCTemp
        data.IAOCRunning = state.IAOCRunning
        data.IAOCTemp = state.IAOCSetTemp
        for zone in range(10):
            setattr(data, f"OnOffZone{zone + 1}", getattr(state, f"OnOffZone{zone + 1}"))
            setattr(data, f"TempZone{zone + 1}", getattr(state, f"SetTempZone{zone + 1}"))
            setattr(data, f"Override{zone + 1}", getattr(state, f"ProgramModeOverriddenZone{zone + 1}"))

        # Could/should do a get fw version pub/sub to have values to fill these with
        # CC3200FW_Major = state.CC3200FW_Major
        # CC3200FW_Minor = state.CC3200FW_Minor
        # STM32FW_Major = state.STM32FW_Major
        # STM32FW_Minor = state.STM32FW_Minor

        return data

    async def _send_remote_props(self, data=None, checker=None):
        data = data or self.new_remote_props()
        jdata = json.dumps(data.__dict__)
        try:
            update_lock = threading.Lock()
            if checker:
                update_lock.acquire()
                def override_listener():
                    if checker(self.current_state):
                        update_lock.release()

                self._update_listener_override = override_listener

            headers = await self._get_auth()
            async with self._httpsession.put(
                NewWebApiUrl + f"devices/{self._mac_address}", headers=headers,
                data=jdata,
                ) as rsp:
                _LOGGER.debug(f"Update response received: {rsp.json()}")
            if self.verbose:
                _LOGGER.warn("Sent: %s" % jdata)

            if checker:
                # Wait for expected response
                update_lock.acquire(timeout=6)

        except Exception as ex:
            _LOGGER.exception("Failed to publish", ex)
            raise
        finally:
            self._update_listener_override = None

    async def set_off(self):
        self.current_state.SystemOn = 0
        checker = lambda state: state.SystemOn == 0
        await self._send_remote_props(checker=checker)

    async def set_zone_state(self, zone_index, is_on):
        """ Turns a specific zone on and off. """
        on_state = 1 if is_on else 0
        setattr(self.current_state, self.get_on_off_zone_name(zone_index), on_state)
        checker = lambda state: getattr(state, self.get_on_off_zone_name(zone_index)) == on_state
        await self._send_remote_props(checker=checker)

    async def set_fan_only(self):
        self.current_state.SystemOn = 1
        self.current_state.CFanOnlyOrCool = 1
        self.current_state.HFanOnly = 1
        checker = lambda state: state.CFanOnlyOrCool == 1 and state.SystemOn == 1 and state.HFanOnly == 1
        await self._send_remote_props(checker=checker)

    async def set_heating(self):
        self.current_state.SystemOn = 1
        self.current_state.HFanOnly = 0
        self.current_state.HRunning = 1
        def checker(state):
            return state.HFanOnly == 0 and \
                   state.SystemOn == 1 and \
                   state.HRunning == 1
        await self._send_remote_props(checker=checker)

    async def set_cooling_by_temperature(self):
        self.current_state.FanOrTempControl = 1
        await self.set_cooling()

    async def set_cooling_by_speed(self):
        self.current_state.FanOrTempControl = 0
        await self.set_cooling()

    async def set_cooling(self):
        self.current_state.SystemOn = 1
        self.current_state.CFanOnlyOrCool = 0
        def checker(state):
            return state.CFanOnlyOrCool == 0 and \
                   state.SystemOn == 1
        await self._send_remote_props(checker=checker)

    async def set_current_speed(self, speed):
        if speed == 0:
            # Control to temperature, not fan speed
            self.current_state.FanOrTempControl = 1
            checker = lambda state: state.FanOrTempControl == 0
            await self._send_remote_props(checker=checker)
        else:
            self.current_state.CFanSpeed = speed
            checker = lambda state: state.CFanSpeed == speed
            await self._send_remote_props(checker=checker)

    async def set_temperature(self, new_temp):
        self.current_state.CTemp = new_temp
        self.current_state.HTemp = new_temp
        self.current_state.FAOCTemp = new_temp
        self.current_state.IAOCSetTemp = new_temp
        self.current_state.SetTempZone1 = new_temp
        checker = lambda state: state.CTemp == new_temp
        await self._send_remote_props(checker=checker)

    def get_on_off_zone_name(self, zone_index):
        return f"OnOffZone{zone_index + 1}"

    def get_zone_name(self, zone_index):
        return getattr(self.current_system_state, f"ZoneName{zone_index + 1}")

    def get_installed_device_config(self):
        device = {}
        if self.current_system_state.HeaterInSystem:
            device = self.current_system_state.Heater
        elif self.current_system_state.AOCFixedInSystem:
            device = self.current_system_state.AOCFixed
        elif self.current_system_state.AOCInverterInSystem:
            device = self.current_system_state.AOCInverter
        elif self.current_system_state.NoOfEVAPInSystem > 0:
            device = self.current_system_state.EVAPCooler

        return device


def main():
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

    loop = asyncio.get_event_loop()
    loop.run_until_complete(m.login())

    loop.run_until_complete(m.refresh_state())

    while not m.current_state:
        time.sleep(1)
    print("")
    print("Current State:")
    print(str(m.current_state))
    print("")

if __name__ == "__main__":
    main()
