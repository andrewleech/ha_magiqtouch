import boto3
from AWSIoTPythonSDK.MQTTLib import AWSIoTMQTTClient
import json
import time
import random
import string
import argparse
from pycognito.aws_srp import AWSSRP

# Read in command-line parameters
parser = argparse.ArgumentParser()
parser.add_argument("-e", "--email", action="store", required=True, dest="email", help="Your Magiqtouch login email")
parser.add_argument("-p", "--password", action="store", required=True, dest="password",
                    help="Your Magiqtouch login password")
parser.add_argument("-m", "--mac", action="store", required=True, dest="mac", help="MAC address of controller")

args = parser.parse_args()
user = args.email
password = args.password
MACADDRESS = args.mac

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

PUBLISH_TOPIC = "SeeleyIoT/{0}/MobileRequest".format(MACADDRESS)
REFRESH_MESSAGE_CONTENT = "\"SerialNo\":\"{0}\",\"Status\":1"
SUBSCRIBE_TOPIC = "SeeleyIoT/{0}/MobileRealTime".format(MACADDRESS)
FIRMWARE_SUBSCRIBE_TOPIC = "SeeleyIoT/{0}/FirmwareUpdate"

print('SUBSCRIBE_TOPIC:', SUBSCRIBE_TOPIC)

# # Configure debug logging
# logger = logging.getLogger("AWSIoTPythonSDK.core")
# logger.setLevel(logging.DEBUG)
# streamHandler = logging.StreamHandler()
# formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
# streamHandler.setFormatter(formatter)
# logger.addHandler(streamHandler)

## First, login to cognito with MagiqTouch user/pass
client = boto3.client('cognito-idp', region_name=AWS_REGION)
aws = AWSSRP(username=user, password=password, pool_id=AWS_USER_POOL_ID,
             client_id=cognito_userpool_client_id, client=client)
tokens = aws.authenticate_user()
AccessToken = tokens['AuthenticationResult']['AccessToken']
RefreshToken = tokens['AuthenticationResult']['RefreshToken']
IdToken = tokens['AuthenticationResult']['IdToken']

## Get IdentityId for the user
cognito = boto3.client('cognito-identity', region_name=AWS_REGION)
account_id = AWS_POOL_NAME
creds = cognito.get_id(
    # AccountId=account_id,
    IdentityPoolId=AWS_POOL_ID,
    Logins={AWS_PROVIDER_NAME: IdToken}
)

## Get temporary credentials for the IdentityId
identity = cognito.get_credentials_for_identity(
    IdentityId=creds['IdentityId'],
    Logins={AWS_PROVIDER_NAME: IdToken}
)

AccessKeyId = identity["Credentials"]["AccessKeyId"]
SecretKey = identity["Credentials"]["SecretKey"]
SessionToken = identity["Credentials"]["SessionToken"]

credentials = dict(aws_access_key_id=AccessKeyId, aws_secret_access_key=SecretKey, aws_session_token=SessionToken)

print("AccessKeyId:", AccessKeyId)
print("SecretKey:", SecretKey)
print("SessionToken:", SessionToken)
print("IdentityId:", identity['IdentityId'])
print("Expiration:", identity["Credentials"]['Expiration'])

## Enable custom policy for user (copied from official app)
iot = boto3.client('iot', region_name=AWS_REGION, **credentials)
response = iot.attach_policy(
    policyName='SeelyIoTPolicy',
    target=creds['IdentityId']
)

## Create random mqtt client id (copied from the official app)
clientId = "MagIQ0" + ''.join(random.choices(string.digits, k=16))

# from https://docs.aws.amazon.com/iot/latest/developerguide/server-authentication.html
rootCAPath = 'SFSRootCAG2.pem'

# Init AWSIoTMQTTClient
myAWSIoTMQTTClient = AWSIoTMQTTClient(clientId, useWebsocket=True)

# AWSIoTMQTTClient configuration
myAWSIoTMQTTClient.configureEndpoint(host, 443)
myAWSIoTMQTTClient.configureCredentials(rootCAPath)
myAWSIoTMQTTClient.configureIAMCredentials(AccessKeyId, SecretKey, SessionToken)
myAWSIoTMQTTClient.configureAutoReconnectBackoffTime(1, 32, 20)
myAWSIoTMQTTClient.configureOfflinePublishQueueing(-1)  # Infinite offline Publish queueing
myAWSIoTMQTTClient.configureDrainingFrequency(2)  # Draining: 2 Hz
myAWSIoTMQTTClient.configureConnectDisconnectTimeout(20)  # 10 sec
myAWSIoTMQTTClient.configureMQTTOperationTimeout(10)  # 5 sec

def myOnMessageCallback(message):
    print("myOnMessageCallback:", message)

myAWSIoTMQTTClient.onMessage = myOnMessageCallback

# Connect and subscribe to AWS IoT
myAWSIoTMQTTClient.connect()
print("MQTT Connected")


# Custom MQTT message callback
def customCallback(client, userdata, message):
    print("Received a new message: ")
    print(message.payload)
    print("from topic: ")
    print(message.topic)
    print("--------------\n\n")


myAWSIoTMQTTClient.subscribe(SUBSCRIBE_TOPIC, 0, customCallback)
time.sleep(2)

myAWSIoTMQTTClient.publish(PUBLISH_TOPIC, json.dumps({
    "SerialNo": MACADDRESS, "Status": 1,
}), 0)
print("Done")
time.sleep(30)
