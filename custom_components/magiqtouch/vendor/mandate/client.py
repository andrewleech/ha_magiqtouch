import datetime
import json
import aiohttp

from jose import jwt, JWTError

from .aws_srp import AWSSRP
from .exceptions import TokenVerificationException, ForceChangePasswordException


COGNITO_URL = 'https://cognito-idp.{}.amazonaws.com/'
COGNITO_HEADERS = {
    'Content-Type': 'application/x-amz-json-1.1',
}


class CognitoError(Exception):
    """Raised when Cognito returns an error response."""

    def __init__(self, error_type, message):
        self.error_type = error_type
        super().__init__(f'{error_type}: {message}')


class Cognito(object):
    def __init__(self, user_pool_id, client_id, user_pool_region=None,
                 username=None, id_token=None, access_token=None,
                 refresh_token=None, client_secret=None,
                 aiohttp_session=None,
                 # Legacy kwargs accepted but ignored (removed boto3 dependency)
                 access_key=None, secret_key=None, client_callback=None):
        self.user_pool_id = user_pool_id
        self.client_id = client_id
        self.user_pool_region = user_pool_region or user_pool_id.split('_')[0]
        self.username = username
        self.id_token = id_token
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.client_secret = client_secret
        self.token_type = None
        self._aiohttp_session = aiohttp_session

    async def _cognito_post(self, session, target, payload):
        """Make a direct HTTPS POST to the Cognito service.

        InitiateAuth and RespondToAuthChallenge are unauthenticated
        API calls that don't require SigV4 signing.
        """
        url = COGNITO_URL.format(self.user_pool_region)
        headers = {
            **COGNITO_HEADERS,
            'X-Amz-Target': f'AWSCognitoIdentityProviderService.{target}',
        }
        async with session.post(url, json=payload, headers=headers) as resp:
            data = await resp.json(content_type=None)
            if '__type' in data:
                error_type = data['__type'].rsplit('#', 1)[-1]
                raise CognitoError(error_type, data.get('message', ''))
            return data

    def _get_session(self):
        """Return the aiohttp session, or create a temporary one."""
        if self._aiohttp_session:
            return _NoCloseSession(self._aiohttp_session)
        return aiohttp.ClientSession()

    async def get_keys(self):
        try:
            return self.pool_jwk
        except AttributeError:
            async with self._get_session() as session:
                resp = await session.get(
                    'https://cognito-idp.{}.amazonaws.com/{}/.well-known/jwks.json'.format(
                        self.user_pool_region, self.user_pool_id
                    ))
                self.pool_jwk = await resp.json()
                return self.pool_jwk

    async def get_key(self, kid):
        keys = (await self.get_keys()).get('keys')
        key = list(filter(lambda x: x.get('kid') == kid, keys))
        return key[0]

    async def verify_token(self, token, id_name, token_use):
        kid = jwt.get_unverified_header(token).get('kid')
        unverified_claims = jwt.get_unverified_claims(token)
        token_use_verified = unverified_claims.get('token_use') == token_use
        if not token_use_verified:
            raise TokenVerificationException(
                'Your {} token use could not be verified.')
        hmac_key = await self.get_key(kid)
        try:
            verified = jwt.decode(token, hmac_key, algorithms=['RS256'],
                                  audience=unverified_claims.get('aud'),
                                  issuer=unverified_claims.get('iss'))
        except JWTError:
            raise TokenVerificationException(
                'Your {} token could not be verified.')
        setattr(self, id_name, token)
        return verified

    async def check_token(self, renew=True):
        """
        Checks the exp attribute of the access_token and either refreshes
        the tokens by calling the renew_access_tokens method or does nothing
        :param renew: bool indicating whether to refresh on expiration
        :return: bool indicating whether access_token has expired
        """
        if not self.access_token:
            raise AttributeError('Access Token Required to Check Token')
        now = datetime.datetime.now()
        dec_access_token = jwt.get_unverified_claims(self.access_token)

        if now > datetime.datetime.fromtimestamp(dec_access_token['exp']):
            expired = True
            if renew:
                await self.renew_access_token()
        else:
            expired = False
        return expired

    async def authenticate(self, password):
        """
        Authenticate the user using the SRP protocol
        :param password: The user's password
        """
        aws = AWSSRP(username=self.username, password=password,
                     pool_id=self.user_pool_id,
                     client_id=self.client_id,
                     client_secret=self.client_secret)
        auth_params = aws.get_auth_params()

        async with self._get_session() as session:
            response = await self._cognito_post(session, 'InitiateAuth', {
                'AuthFlow': 'USER_SRP_AUTH',
                'ClientId': self.client_id,
                'AuthParameters': auth_params,
            })

            if response.get('ChallengeName') != aws.PASSWORD_VERIFIER_CHALLENGE:
                raise NotImplementedError(
                    'The %s challenge is not supported' % response.get('ChallengeName'))

            challenge_response = aws.process_challenge(
                response['ChallengeParameters'])

            tokens = await self._cognito_post(session, 'RespondToAuthChallenge', {
                'ClientId': self.client_id,
                'ChallengeName': aws.PASSWORD_VERIFIER_CHALLENGE,
                'ChallengeResponses': challenge_response,
            })

        if tokens.get('ChallengeName') == aws.NEW_PASSWORD_REQUIRED_CHALLENGE:
            raise ForceChangePasswordException(
                'Change password before authenticating')

        await self.verify_token(tokens['AuthenticationResult']['IdToken'],
                                'id_token', 'id')
        self.refresh_token = tokens['AuthenticationResult']['RefreshToken']
        await self.verify_token(tokens['AuthenticationResult']['AccessToken'],
                                'access_token', 'access')
        self.token_type = tokens['AuthenticationResult']['TokenType']

    async def renew_access_token(self):
        """
        Sets a new access token on the User using the refresh token.
        """
        auth_params = {'REFRESH_TOKEN': self.refresh_token}
        self._add_secret_hash(auth_params, 'SECRET_HASH')

        async with self._get_session() as session:
            refresh_response = await self._cognito_post(session, 'InitiateAuth', {
                'ClientId': self.client_id,
                'AuthFlow': 'REFRESH_TOKEN',
                'AuthParameters': auth_params,
            })

        self.access_token = refresh_response['AuthenticationResult']['AccessToken']
        self.id_token = refresh_response['AuthenticationResult']['IdToken']
        self.token_type = refresh_response['AuthenticationResult']['TokenType']

    def _add_secret_hash(self, parameters, key):
        """
        Helper function that computes SecretHash and adds it
        to a parameters dictionary at a specified key
        """
        if self.client_secret is not None:
            secret_hash = AWSSRP.get_secret_hash(self.username, self.client_id,
                                                 self.client_secret)
            parameters[key] = secret_hash


class _NoCloseSession:
    """Wraps an aiohttp.ClientSession to prevent closing a shared session."""

    def __init__(self, session):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, *args):
        pass
