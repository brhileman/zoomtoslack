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
from urllib.parse import urlparse
from tenacity import retry, wait_exponential, stop_after_attempt, retry_if_exception_type

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
    """
    Retrieves a valid Zoom access token, refreshing it if necessary.
    """
    global ZOOM_ACCESS_TOKEN, ZOOM_TOKEN_EXPIRY
    current_time = int(time.time())
    if not ZOOM_ACCESS_TOKEN or current_time >= ZOOM_TOKEN_EXPIRY:
        access_token, expires_in = obtain_zoom_access_token()
        if access_token:
            ZOOM_ACCESS_TOKEN = access_token
            ZOOM_TOKEN_EXPIRY = current_time + expires_in - 60  # Refresh 1 minute before expiry
    return ZOOM_ACCESS_TOKEN

def get_zoom_headers():
    """
    Constructs the headers required for Zoom API requests.
    
    Returns:
        dict: Headers with Authorization and Content-Type.
    """
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

def is_valid_download_url(download_url):
    """
    Validates the structure of the download URL.
    
    Parameters:
        download_url (str): The URL to validate.
    
    Returns:
        bool: True if the URL is valid, False otherwise.
    """
    try:
        parsed_url = urlparse(download_url)
        return all([parsed_url.scheme, parsed_url.netloc, parsed_url.path])
    except Exception as e:
        logger.exception(f"Error parsing download URL '{download_url}': {e}")
        return False

@retry(
    wait=wait_exponential(multiplier=1, min=4, max=10),
    stop=stop_after_attempt(3),
    retry=retry_if_exception_type(requests.exceptions.RequestException)
)
def download_recording(download_url, download_token):
    """
    Downloads a recording from the provided download URL using the download token.
    Implements retry logic for transient network issues.
    
    Parameters:
        download_url (str): The URL to download the recording from.
        download_token (str): The token required for authorization.
    
    Returns:
        str: The path to the downloaded recording file, or None if download fails.
    """
    if not is_valid_download_url(download_url):
        logger.error(f"Invalid download URL: {download_url}")
        return None

    try:
        headers = {
            "Authorization": f"Bearer {download_token}",
            "Content-Type": "application/json"
        }
        response = requests.get(download_url, headers=headers, stream=True, timeout=30)
        response.raise_for_status()
        
        # Safely determine the file extension from the URL
        parsed_url = urlparse(download_url)
        path = parsed_url.path  # e.g., /path/to/file.mp4
        _, file_extension = os.path.splitext(path)
        file_extension = file_extension.lstrip('.')  # Remove the leading dot
        
        # Fallback to a default extension if none found
        if not file_extension:
            file_extension = 'mp4'  # Default to mp4 or another appropriate format
        
        # Validate file extension against supported types
        supported_extensions = ['mp4', 'm4a', 'mov']
        if file_extension.lower() not in supported_extensions:
            logger.warning(f"Unsupported file extension: .{file_extension}. Supported extensions are: {supported_extensions}.")
            return None
        
        # Create a temporary file with the correct extension
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=f".{file_extension}")
        with open(temp_file.name, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:  # Filter out keep-alive chunks
                    f.write(chunk)
        
        logger.info(f"Downloaded recording to {temp_file.name}")
        return temp_file.name
    except requests.exceptions.RequestException as req_err:
        logger.error(f"Network error occurred while downloading recording: {req_err}")
        raise  # Trigger retry
    except Exception as e:
        logger.exception(f"Unexpected error downloading recording: {e}")
        return None
