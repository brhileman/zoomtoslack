# zoom_utils.py

import os
import logging
import requests
import tempfile
import base64
import time
import hmac
import hashlib
import json

logger = logging.getLogger(__name__)

ZOOM_API_BASE_URL = "https://api.zoom.us/v2"

# Server-to-Server OAuth Credentials
ZOOM_CLIENT_ID = os.getenv('ZOOM_CLIENT_ID')
ZOOM_CLIENT_SECRET = os.getenv('ZOOM_CLIENT_SECRET')

if not ZOOM_CLIENT_ID or not ZOOM_CLIENT_SECRET:
    logger.error("ZOOM_CLIENT_ID and ZOOM_CLIENT_SECRET must be set in environment variables.")
    raise EnvironmentError("ZOOM_CLIENT_ID and ZOOM_CLIENT_SECRET are required.")

def obtain_zoom_access_token():
    """
    Obtains a new OAuth access token using Client Credentials Grant.
    """
    try:
        url = "https://zoom.us/oauth/token"
        credentials = f"{ZOOM_CLIENT_ID}:{ZOOM_CLIENT_SECRET}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "grant_type": "client_credentials"
        }
        response = requests.post(url, headers=headers, data=data)
        response.raise_for_status()
        token_info = response.json()
        access_token = token_info.get('access_token')
        expires_in = token_info.get('expires_in')  # seconds
        logger.info("Obtained new Zoom OAuth access token.")
        return access_token, expires_in
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error occurred while obtaining access token: {http_err} - {response.text}")
        return None, None
    except Exception as e:
        logger.exception(f"Unexpected error obtaining access token: {e}")
        return None, None

# Token Management
ZOOM_ACCESS_TOKEN = None
ZOOM_TOKEN_EXPIRY = 0  # Unix timestamp

def get_valid_zoom_access_token():
    global ZOOM_ACCESS_TOKEN, ZOOM_TOKEN_EXPIRY
    current_time = int(time.time())
    if not ZOOM_ACCESS_TOKEN or current_time >= ZOOM_TOKEN_EXPIRY:
        access_token, expires_in = obtain_zoom_access_token()
        if access_token:
            ZOOM_ACCESS_TOKEN = access_token
            ZOOM_TOKEN_EXPIRY = current_time + expires_in - 60  # Refresh 1 minute before expiry
    return ZOOM_ACCESS_TOKEN

def get_zoom_headers():
    access_token = get_valid_zoom_access_token()
    if not access_token:
        logger.error("Unable to obtain valid Zoom access token.")
        raise EnvironmentError("Zoom access token is required.")
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

def validate_zoom_webhook(signing_secret, signature, timestamp, payload):
    """
    Validates Zoom webhook signatures to ensure authenticity.
    
    Parameters:
        signing_secret (str): The webhook secret token from Zoom.
        signature (str): The signature from the 'x-zm-signature' header.
        timestamp (str): The timestamp from the 'x-zm-request-timestamp' header.
        payload (str): The raw request body as a JSON string.
    
    Returns:
        bool: True if the signature is valid, False otherwise.
    """
    try:
        # Construct the message as per Zoom's specifications
        message = f"v0:{timestamp}:{payload}"
        # Create HMAC SHA256 hash using the signing secret
        hash_digest = hmac.new(
            signing_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        # Prepend 'v0=' to the hash to form the expected signature
        expected_signature = f"v0={hash_digest}"
        # Compare the expected signature with the received signature
        is_valid = hmac.compare_digest(expected_signature, signature)
        if is_valid:
            logger.info("Zoom webhook signature validated successfully.")
        else:
            logger.warning("Zoom webhook signature validation failed.")
        return is_valid
    except Exception as e:
        logger.exception(f"Error during Zoom webhook validation: {e}")
        return False

def download_recording(download_url, download_token):
    """
    Downloads a recording from the provided download URL using the download token.
    """
    try:
        headers = {
            "Authorization": f"Bearer {download_token}",
            "Content-Type": "application/json"
        }
        response = requests.get(download_url, headers=headers, stream=True)
        response.raise_for_status()
        # Determine the file extension from the URL
        file_extension = download_url.split('.')[-1].split('?')[0]  # Handles URLs with query params
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_extension}")
        with open(temp_file.name, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        logger.info(f"Downloaded recording to {temp_file.name}")
        return temp_file.name
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error occurred while downloading recording: {http_err} - {response.text}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error downloading recording: {e}")
        return None
