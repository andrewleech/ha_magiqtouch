import argparse
import json
import random
import string
import time

import boto3
import requests
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient
from pycognito.aws_srp import AWSSRP

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
STATIC_WEBSITE_ENDPOINT = "http://magiqtouch-iot-websites.s3-website-ap-southeast-2.amazonaws.com/"

WebServiceURL = "https://57uh36mbv1.execute-api.ap-southeast-2.amazonaws.com/api/"
ApiUrl = "https://57uh36mbv1.execute-api.ap-southeast-2.amazonaws.com" + "/api/loadmobiledevice"

# from https://docs.aws.amazon.com/iot/latest/developerguide/server-authentication.html
rootCAPath = 'SFSRootCAG2.pem'


# # MQTT logging
# logger = logging.getLogger("AWSIoTPythonSDK.core")
# logger.setLevel(logging.DEBUG)
# streamHandler = logging.StreamHandler()
# formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# streamHandler.setFormatter(formatter)
# logger.addHandler(streamHandler)


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

        self._mqtt_client_id = None

        self.current_state = None

    def login(self):
        ## First, login to cognito with MagiqTouch user/pass
        client = boto3.client('cognito-idp', region_name=AWS_REGION)
        aws = AWSSRP(username=self._user, password=self._password, pool_id=AWS_USER_POOL_ID,
                     client_id=cognito_userpool_client_id, client=client)
        tokens = aws.authenticate_user()
        self._AccessToken = tokens['AuthenticationResult']['AccessToken']
        self._RefreshToken = tokens['AuthenticationResult']['RefreshToken']
        self._IdToken = tokens['AuthenticationResult']['IdToken']

        ## Get IdentityId for the user
        cognito = boto3.client('cognito-identity', region_name=AWS_REGION)
        # account_id = AWS_POOL_NAME
        creds = cognito.get_id(
            IdentityPoolId=AWS_POOL_ID,
            Logins={AWS_PROVIDER_NAME: self._IdToken}
        )
        self._IdentityId = creds['IdentityId']

        ## Get temporary credentials for the IdentityId
        identity = cognito.get_credentials_for_identity(
            IdentityId=self._IdentityId,
            Logins={AWS_PROVIDER_NAME: self._IdToken}
        )

        self._AccessKeyId = identity["Credentials"]["AccessKeyId"]
        self._SecretKey = identity["Credentials"]["SecretKey"]
        self._SessionToken = identity["Credentials"]["SessionToken"]

        # print("AccessKeyId:", AccessKeyId)
        # print("SecretKey:", SecretKey)
        # print("SessionToken:", SessionToken)
        # print("IdentityId:", identity['IdentityId'])
        print("Login Expiration:", identity["Credentials"]['Expiration'])

        ## Enable custom policy for user (copied from official app)
        credentials = dict(
            aws_access_key_id=self._AccessKeyId,
            aws_secret_access_key=self._SecretKey,
            aws_session_token=self._SessionToken
        )
        iot = boto3.client('iot', region_name=AWS_REGION, **credentials)
        _ = iot.attach_policy(
            policyName='SeelyIoTPolicy',
            target=self._IdentityId
        )

        ## Get MACADDRESS
        rsp = requests.get(ApiUrl, headers={
            "Authorization": self._IdToken
        })
        self._mac_address = rsp.json()[0]['MacAddressId']
        print('MAC:', self._mac_address)

    ## MQTT

    @property
    def mqtt_publish_topic(self):
        return "SeeleyIoT/{0}/MobileRequest".format(self._mac_address)

    @property
    def mqtt_subscribe_topic(self):
        return "SeeleyIoT/{0}/MobileRealTime".format(self._mac_address)

    @property
    def mqtt_subscribe_fw_topic(self):
        return "SeeleyIoT/{0}/FirmwareUpdate".format(self._mac_address)

    @property
    def mqtt_client_id(self):
        if not self._mqtt_client_id:
            ## Create random mqtt client id (copied from the official app)
            self._mqtt_client_id = "MagIQ0" + ''.join(random.choices(string.digits, k=16))
        return self._mqtt_client_id

    def mqtt_connect(self):
        # Init AWSIoTMQTTClient
        self._mqtt_client = AWSIoTMQTTClient(self.mqtt_client_id, useWebsocket=True)

        # AWSIoTMQTTClient configuration
        self._mqtt_client.configureEndpoint(host, 443)
        self._mqtt_client.configureCredentials(rootCAPath)
        self._mqtt_client.configureIAMCredentials(self._AccessKeyId, self._SecretKey, self._SessionToken)
        self._mqtt_client.configureAutoReconnectBackoffTime(1, 32, 20)
        self._mqtt_client.configureOfflinePublishQueueing(-1)  # Infinite offline Publish queueing
        self._mqtt_client.configureDrainingFrequency(2)  # Draining: 2 Hz
        self._mqtt_client.configureConnectDisconnectTimeout(20)  # 10 sec
        self._mqtt_client.configureMQTTOperationTimeout(10)  # 5 sec

        # def myOnMessageCallback(message):
        #     print("myOnMessageCallback:", message)
        #
        # self._mqtt_client.onMessage = myOnMessageCallback

        # Connect and subscribe to AWS IoT
        self._mqtt_client.connect()
        print("MQTT Connected")

        self._mqtt_client.subscribe(self.mqtt_subscribe_topic, 1, self._mqtt_response_handler)

    def _mqtt_response_handler(self, client, userdata, message):
        if message.topic == self.mqtt_subscribe_topic:
            try:
                self.current_state = json.loads(message.payload)
            except ValueError:
                print("Failed to parse current state")
        else:
            print("Received a new message: ")
            print(message.payload)
            print("from topic: ")
            print(message.topic)
            print("--------------\n\n")

    def refresh_state(self):
        self._mqtt_client.publish(self.mqtt_publish_topic, json.dumps({
            "SerialNo": self._mac_address, "Status": 1,
        }), 1)




def main():
    # Read in command-line parameters
    parser = argparse.ArgumentParser()
    parser.add_argument("-e", "--email", action="store", required=True, dest="email",
                        help="Your Magiqtouch login email")
    parser.add_argument("-p", "--password", action="store", required=True, dest="password",
                        help="Your Magiqtouch login password")

    args = parser.parse_args()
    user = args.email
    password = args.password

    m = MagiQtouch(user=user, password=password)
    m.login()
    m.mqtt_connect()
    m.refresh_state()

    while not m.current_state:
        time.sleep(1)
    print(m.current_state)


if __name__ == "__main__":
    main()
