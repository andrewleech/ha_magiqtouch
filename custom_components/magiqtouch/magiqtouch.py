import argparse
import json
import random
import string
import time
import ssl
import socket
import asyncio
import logging
import aiobotocore
import threading
import requests
from mandate import Cognito
from datetime import datetime
from botocore.errorfactory import BaseClientExceptions
from pathlib import Path

import aiohttp

try:
    from .structures import RemoteStatus, RemoteAccessRequest, SystemDetails
except ImportError:
    from structures import RemoteStatus, RemoteAccessRequest, SystemDetails

cognitoIdentityPoolID = "ap-southeast-2:0ed20c23-4af8-4408-86fc-b78689a5c7a7"

host = "ab7hzia9uew8g-ats.iot.ap-southeast-2.amazonaws.com"

AWS_REGION = "ap-southeast-2"
AWS_USER_POOL_ID = "ap-southeast-2_uw5VVNlib"
AWS_POOL_ID = "ap-southeast-2:0ed20c23-4af8-4408-86fc-b78689a5c7a7"
AWS_PROVIDER_NAME = "cognito-idp.ap-southeast-2.amazonaws.com/ap-southeast-2_uw5VVNlib"
appId = "4e662b6273004a6c9a0797efae6fbb73"
cognito_userpool_client_id = "6e1lu9fchv82uefiarsp0290v9"
AWS_CLIENT_ID = "6e1lu9fchv82uefiarsp0290v9"
AWS_POOL_NAME = "uw5VVNlib"
STATIC_WEBSITE_ENDPOINT = (
    "http://magiqtouch-iot-websites.s3-website-ap-southeast-2.amazonaws.com/"
)

WebServiceURL = "https://57uh36mbv1.execute-api.ap-southeast-2.amazonaws.com/api/"
ApiUrl = (
    "https://57uh36mbv1.execute-api.ap-southeast-2.amazonaws.com"
    + "/api/"
)

NewWebApiUrl = (
    "https://tgjgb3bcf3.execute-api.ap-southeast-2.amazonaws.com/prod"
    + "/v1/"
)

_LOGGER = logging.getLogger("magiqtouch")


class MagiQtouch_Driver:
    def __init__(self, user, password):
        self._password = password
        self._user = user

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

    async def login(self):
        _LOGGER.info("Logging in...")
        try:
            ## First, login to cognito with MagiqTouch user/pass
            cog = Cognito(
                user_pool_id=AWS_USER_POOL_ID,
                client_id=cognito_userpool_client_id,
                user_pool_region=AWS_REGION,
                username=self._user,
                # Dummy credentials to bypass EC2 IMDS
                access_key='AKIAIOSFODNN7EXAMPLE',
                secret_key='wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
            )

            await cog.authenticate(self._password)
        except Exception as ex:
            if "UserNotFoundException" in str(ex) or "NotAuthorizedException" in str(
                ex
            ):
                _LOGGER.exception("Error during auth", ex)
                return False
            raise

        self._AccessToken = cog.access_token
        self._RefreshToken = cog.refresh_token
        self._IdToken = cog.id_token

        session = aiobotocore.session.get_session()
        async with session.create_client(
            "cognito-identity", region_name=AWS_REGION,
            # Dummy credentials to bypass EC2 IMDS
            aws_secret_access_key='AKIAIOSFODNN7EXAMPLE',
            aws_access_key_id='wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY',
        ) as identity:
            creds = await identity.get_id(
                IdentityPoolId=AWS_POOL_ID, Logins={AWS_PROVIDER_NAME: self._IdToken}
            )
            self._IdentityId = creds["IdentityId"]

            ident = await identity.get_credentials_for_identity(
                IdentityId=self._IdentityId, Logins={AWS_PROVIDER_NAME: self._IdToken}
            )

            self._AccessKeyId = ident["Credentials"]["AccessKeyId"]
            self._SecretKey = ident["Credentials"]["SecretKey"]
            self._SessionToken = ident["Credentials"]["SessionToken"]

            _LOGGER.debug("Login Expiration:", ident["Credentials"]["Expiration"])

        ## Enable custom policy for user (copied from official app)
        credentials = dict(
            aws_access_key_id=self._AccessKeyId,
            aws_secret_access_key=self._SecretKey,
            aws_session_token=self._SessionToken,
        )
        async with session.create_client(
            "iot", region_name=AWS_REGION, **credentials
        ) as iot:
            _ = await iot.attach_policy(
                policyName="SeelyIoTPolicy", target=self._IdentityId
            )

        ## Get MACADDRESS
        async with aiohttp.ClientSession() as http:
            async with http.get(
                ApiUrl + "loadmobiledevice", headers={"Authorization": self._IdToken}
            ) as rsp:
                self._mac_address = (await rsp.json())[0]["MacAddressId"]
        _LOGGER.debug("MAC:", self._mac_address)

        self.logged_in = True
        return True

    async def logout(self):
        # TODO
        pass

    async def initial_refresh(self):
        if not self.logged_in:
            raise ValueError("Not logged in")

        await self.refresh_state(initial=True)

    def set_listener(self, listener):
        self._update_listener = listener

    async def refresh_state(self, initial=False):
        async with aiohttp.ClientSession() as http:
            await http.put(
                NewWebApiUrl + f"devices/{self._mac_address}", headers={"Authorization": f"Bearer {self._IdToken}"},
                data=json.dumps(
                    {
                        "SerialNo": self._mac_address,
                        "Status": 1,
                    }
                ),
            )

        if initial:
            # Get system details so we can see how many zones are in use.
            async with aiohttp.ClientSession() as http:
                async with http.get(
                    ApiUrl + f"loadsystemdetails?macAddressId={self._mac_address}", headers={"Authorization": self._IdToken}
                    ) as rsp:
                        data = await rsp.json()
                        new_system_state = SystemDetails.from_dict(data)
                        self.current_system_state = new_system_state

        async with aiohttp.ClientSession() as http:
            async with http.get(
                ApiUrl + f"loadsystemrunning?macAddressId={self._mac_address}", headers={"Authorization": self._IdToken}
                ) as rsp:
                    data = await rsp.json()
                    new_state = RemoteStatus()
                    new_state.__update__(data)
                    if self._update_listener_override:
                        _LOGGER.debug("State watching: %s" % new_state)
                        self._update_listener_override()
                    elif self._update_listener:
                        _LOGGER.debug("State updated: %s" % new_state)
                        self._update_listener()
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

    def _send_remote_props(self, data=None, checker=None):
        data = data or self.new_remote_props()
        json = data.__json__(indent=0).replace("\n", "")
        try:
            update_lock = threading.Lock()
            if checker:
                update_lock.acquire()
                def override_listener():
                    if checker(self.current_state):
                        update_lock.release()


                self._update_listener_override = override_listener

            with requests.put(
                NewWebApiUrl + f"devices/{self._mac_address}", headers={"Authorization": f"Bearer {self._IdToken}"},
                data=json,
                ) as rsp:
                _LOGGER.debug(f"Update response received: {rsp.json()}")
            _LOGGER.warn("Sent: %s" % json)

            if checker:
                # Wait for expected response
                update_lock.acquire(timeout=6)

        except Exception as ex:
            _LOGGER.exception("Failed to publish", ex)
            raise
        finally:
            self._update_listener_override = None

    def set_off(self):
        self.current_state.SystemOn = 0
        checker = lambda state: state.SystemOn == 0
        self._send_remote_props(checker=checker)

    def set_zone_state(self, zone_index, is_on):
        """ Turns a specific zone on and off. """
        on_state = 1 if is_on else 0
        setattr(self.current_state, self.get_on_off_zone_name(zone_index), on_state)
        checker = lambda state: getattr(state, self.get_on_off_zone_name(zone_index)) == on_state
        self._send_remote_props(checker=checker)

    def set_fan_only(self):
        self.current_state.SystemOn = 1
        self.current_state.CFanOnlyOrCool = 1
        self.current_state.HFanOnly = 1
        checker = lambda state: state.CFanOnlyOrCool == 1 and state.SystemOn == 1 and state.HFanOnly == 1
        self._send_remote_props(checker=checker)

    def set_heating(self, temp_mode):
        # TODO: check is temp mode necessary? Might only be for cooling.
        temp_mode = 1 if temp_mode else 0
        self.current_state.FanOrTempControl = temp_mode
        self.current_state.SystemOn = 1
        self.current_state.HFanOnly = 0
        self.current_state.HRunning = 1  # TODO: see whether this is necessary or not
        def checker(state):
            return state.HFanOnly == 0 and \
                   state.FanOrTempControl == temp_mode and \
                   state.SystemOn == 1 and \
                   state.HRunning == 1
        self._send_remote_props(checker=checker)

    def set_cooling_by_temperature(self):
        self.set_cooling(temp_mode=1)

    def set_cooling_by_speed(self):
        self.set_cooling(temp_mode=0)

    def set_cooling(self, temp_mode):
        temp_mode = 1 if temp_mode else 0
        self.current_state.FanOrTempControl = temp_mode
        self.current_state.SystemOn = 1
        self.current_state.CFanOnlyOrCool = 0
        def checker(state):
            return state.CFanOnlyOrCool == 0 and \
                   state.FanOrTempControl == temp_mode and \
                   state.SystemOn == 1
        self._send_remote_props(checker=checker)

    def set_current_speed(self, speed):
        self.current_state.CFanSpeed = speed
        expected = 0 if self.current_state.CFanSpeed == 0 else speed
        checker = lambda state: state.CFanSpeed == expected
        self._send_remote_props(checker=checker)

    def set_temperature(self, new_temp):
        self.current_state.CTemp = new_temp
        self.current_state.HTemp = new_temp
        self.current_state.FAOCTemp = new_temp
        self.current_state.IAOCSetTemp = new_temp
        self.current_state.SetTempZone1 = new_temp
        checker = lambda state: state.CTemp == new_temp
        self._send_remote_props(checker=checker)

    def get_on_off_zone_name(self, zone_index):
        return f"OnOffZone{zone_index + 1}"

    def get_zone_name(self, zone_index):
        return getattr(self.current_system_state, f"ZoneName{zone_index + 1}")

    def get_installed_device_config(self):
        device = None
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
    print(m.current_state)


if __name__ == "__main__":
    main()
