import json
import requests
import pyotp
from urllib import parse
import sys
import hashlib
from pathlib import Path



# Client Info (ENTER YOUR OWN INFO HERE!! Data varies from users and app types)
FY_ID = "XS08919"  # Your fyers ID
APP_ID_TYPE = "2"  # Keep default as 2, It denotes web login
TOTP_KEY = "KNUZ2YOG52VB6453RPLWZOYA66DPN7ZN"  # TOTP secret is generated when we enable 2Factor TOTP from myaccount portal
PIN = "1014"  # User pin for fyers account
APP_ID = "8YH8F4MDK4"#"7ZZHXHVNKN"  # App ID from myapi dashboard is in the form appId-appType. Example - EGNI8CE27Q-100, In this code EGNI8CE27Q will be APP_ID and 100 will be the APP_TYPE
REDIRECT_URI = "https://www.google.com/"  # Redirect url from the app.
APP_TYPE = "100"
#APP_ID_HASH = "217c9b9e506820e731a58284bf09f994bf9b58243e5f100755483fdefb11dabc"  # SHA-256 hash of appId-appType:appSecret
a_string = '8YH8F4MDK4-100:YKV45I0A5A' # NEW
APP_ID_HASH = hashlib.sha256(a_string.encode('utf-8')).hexdigest()
print(APP_ID_HASH)

# API endpoints
BASE_URL = "https://api-t2.fyers.in/vagator/v2"
BASE_URL_2 = "https://api-t1.fyers.in/api/v3"
URL_SEND_LOGIN_OTP = BASE_URL + "/send_login_otp"
URL_VERIFY_TOTP = BASE_URL + "/verify_otp"
URL_VERIFY_PIN = BASE_URL + "/verify_pin"
URL_TOKEN = BASE_URL_2 + "/token"
URL_VALIDATE_AUTH_CODE = BASE_URL_2 + "/validate-authcode"

SUCCESS = 1
ERROR = -1

def send_login_otp(fy_id, app_id):
    try:
        payload = {
            "fy_id": fy_id,
            "app_id": app_id
        }

        result_string = requests.post(url=URL_SEND_LOGIN_OTP, json=payload)
        if result_string.status_code != 200:
            return [ERROR, result_string.text]

        result = json.loads(result_string.text)
        request_key = result["request_key"]

        return [SUCCESS, request_key]
    
    except Exception as e:
        return [ERROR, e]
    

def generate_totp(secret):
    try:
        generated_totp = pyotp.TOTP(secret).now()
        return [SUCCESS, generated_totp]
    
    except Exception as e:
        return [ERROR, e]


def verify_totp(request_key, totp):
    try:
        payload = {
            "request_key": request_key,
            "otp": totp
        }

        result_string = requests.post(url=URL_VERIFY_TOTP, json=payload)
        if result_string.status_code != 200:
            return [ERROR, result_string.text]

        result = json.loads(result_string.text)
        request_key = result["request_key"]

        return [SUCCESS, request_key]
    
    except Exception as e:
        return [ERROR, e]


def verify_PIN(request_key, pin):
    try:
        payload = {
            "request_key": request_key,
            "identity_type": "pin",
            "identifier": pin
        }

        result_string = requests.post(url=URL_VERIFY_PIN, json=payload)
        if result_string.status_code != 200:
            return [ERROR, result_string.text]
    
        result = json.loads(result_string.text)
        access_token = result["data"]["access_token"]

        return [SUCCESS, access_token]
    
    except Exception as e:
        return [ERROR, e]


def token(fy_id, app_id, redirect_uri, app_type, access_token):
    try:
        payload = {
            "fyers_id": fy_id,
            "app_id": app_id,
            "redirect_uri": redirect_uri,
            "appType": app_type,
            "code_challenge": "",
            "state": "sample_state",
            "scope": "",
            "nonce": "",
            "response_type": "code",
            "create_cookie": True
        }
        headers={'Authorization': f'Bearer {access_token}'}

        result_string = requests.post(
            url=URL_TOKEN, json=payload, headers=headers
        )

        if result_string.status_code != 308:
            return [ERROR, result_string.text]

        result = json.loads(result_string.text)
        url = result["Url"]
        auth_code = parse.parse_qs(parse.urlparse(url).query)['auth_code'][0]

        return [SUCCESS, auth_code]
    
    except Exception as e:
        return [ERROR, e]


def validate_authcode(app_id_hash, auth_code):
    try:
        payload = {
            "grant_type": "authorization_code",
            "appIdHash": app_id_hash,
            "code": auth_code,
        }

        result_string = requests.post(url=URL_VALIDATE_AUTH_CODE, json=payload)
        if result_string.status_code != 200:
            return [ERROR, result_string.text]

        result = json.loads(result_string.text)
        access_token = result["access_token"]

        return [SUCCESS, access_token]
    
    except Exception as e:
        return [ERROR, e]


def main():
    # Step 1 - Retrieve request_key from send_login_otp API
    send_otp_result = send_login_otp(fy_id=FY_ID, app_id=APP_ID_TYPE)
    if send_otp_result[0] != SUCCESS:
        print(f"send_login_otp failure - {send_otp_result[1]}")
        sys.exit()
    else:
        print("send_login_otp success")

    # Step 2 - Generate totp
    generate_totp_result = generate_totp(secret=TOTP_KEY)
    if generate_totp_result[0] != SUCCESS:
        print(f"generate_totp failure - {generate_totp_result[1]}")
        sys.exit()
    else:
        print("generate_totp success")

    # Step 3 - Verify totp and get request key from verify_otp API
    request_key = send_otp_result[1]
    totp = generate_totp_result[1]
    verify_totp_result = verify_totp(request_key=request_key, totp=totp)
    if verify_totp_result[0] != SUCCESS:
        print(f"verify_totp_result failure - {verify_totp_result[1]}")
        sys.exit()
    else:
        print("verify_totp_result success")
    
    # Step 4 - Verify pin and send back access token
    request_key_2 = verify_totp_result[1]
    verify_pin_result = verify_PIN(request_key=request_key_2, pin=PIN)
    if verify_pin_result[0] != SUCCESS:
        print(f"verify_pin_result failure - {verify_pin_result[1]}")
        sys.exit()
    else:
        print("verify_pin_result success")
    
    # Step 5 - Get auth code for API V2 App from trade access token
    token_result = token(
        fy_id=FY_ID, app_id=APP_ID, redirect_uri=REDIRECT_URI, app_type=APP_TYPE,
        access_token=verify_pin_result[1]
    )
    if token_result[0] != SUCCESS:
        print(f"token_result failure - {token_result[1]}")
        sys.exit()
    else:
        print("token_result success")

    # Step 6 - Get API V2 access token from validating auth code
    auth_code = token_result[1]
    validate_authcode_result = validate_authcode(
        app_id_hash=APP_ID_HASH, auth_code=auth_code
    )
    if validate_authcode_result[0] != SUCCESS:
        print(f"validate_authcode failure - {validate_authcode_result[1]}")
        sys.exit()
    else:
        print("validate_authcode success")
    
    access_token = APP_ID + "-" + APP_TYPE + ":" + validate_authcode_result[1]
    appid1 = APP_ID + "-" + APP_TYPE
    token1 = "" + validate_authcode_result[1]
    print(f"access_token - {access_token}")

    # Determine the script's directory to save files correctly
    script_dir = Path(__file__).resolve().parent

    #save client id and access token to file
    with open(script_dir / "fyers_appid.txt", 'w') as file:
        file.write(appid1)
        print('Appid has been saved in the backend folder -> fyers_appid.txt')
    with open(script_dir / "fyers_token.txt", 'w') as file:
        print('Token has been saved in the backend folder -> fyers_token.txt')
        file.write(token1)

#n - GKZ044XWZG-100:eyJ0eXAiOiJKV1Qzczcx.eyJpc3MiOiJhcGkuZnllcnMuaW4iLCJpYXQiOjE3MDM3NjcyMDMsImV4cCI6MTcwMzzxcxzcxNzAzNzY3MjAzLCJhdWQiOlsieDowIiwieDoxIiwzxcz3d3dxcDowIl0sInN1YiI6ImFjY2xv4324d3d3dc23190b2tlbiIsImF0X2hhc2giOiJnQUFBQUFCbGpXeWpKTmtmT09rU2YtekY1MURGRzAzQU9oZ29FTEN6S29qMG96eTE1aC1LQU5zbXVLcC1GN3FMZWFEQl9PMlYxWlF6MzhGQVRIMk1Nc3dmOEJwdTRvSWxrRUxYMGVhd3pwcTg3QnZfX2h4VGhRRT0iLCJkaXNwbGF5X25hbWUiOiJCSEFOVSBLQVNIWUFQIiwib21zIjoiSzEiLCJoc21fa2V5IjoiMTQzY2E5M2IwNTgxODQzMDI1YjY0MGU4NGQwM2JkOTNkNDA4NzU4ZjY1NjYzMmM4ZjM0NDRmYTQiLCJmeV9pZCI6IlhCMTgwMTIiLCJhcHBUeXBlIjoxMDAsInBvYV9mbGFnIjoiTiJ9.wZqq0yiRpc8KFXeVLt8JMGRDgV1EoJl_Yse6ebmSO5I
if __name__ == "__main__":
    main()