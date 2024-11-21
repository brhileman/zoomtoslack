# zoom_utils.py

import os
import time
import json
import hmac
import hashlib
import base64
import requests
import logging
from dotenv import load_dotenv
import tempfile

# Load environment variables from .env file only if not on Heroku
if os.getenv('DYNO') is None:
    load_dotenv()

# Configure logging to stdout
import sys

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s %(levelname)s %(name)s %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

ZOOM_CLIENT_ID = os.getenv('ZOOM_CLIENT_ID')
ZOOM_CLIENT_SECRET = os.getenv('ZOOM_CLIENT_SECRET')
ZOOM_ACCOUNT_ID = os.getenv('ZOOM_ACCOUNT_ID')

missing_vars = []
for var_name, var in [('ZOOM_CLIENT_ID', ZOOM_CLIENT_ID),
                      ('ZOOM_CLIENT_SECRET', ZOOM_CLIENT_SECRET),
                      ('ZOOM_ACCOUNT_ID', ZOOM_ACCOUNT_ID)]:
    if not var:
        missing_vars.append(var_name)

if missing_vars:
    logger.error(f"Missing environment variables: {', '.join(missing_vars)}")
    raise EnvironmentError(f"Missing required environment variables: {', '.join(missing_vars)}")

def validate_zoom_request(secret_token, zoom_signature, zoom_timestamp, data):
    """
    Validates the incoming Zoom webhook request.
    """
    try:
        # Check timestamp to prevent replay attacks
        if abs(time.time() - int(zoom_timestamp)) > 300:
            logger.warning("Unauthorized request: Timestamp is too old.")
            return False

        # Create the message string
        message = f'v0:{zoom_timestamp}:{json.dumps(data, separators=(",", ":"))}'

        # Compute HMAC SHA256 hash
        hash_for_verify = hmac.new(secret_token.encode(), message.encode(), hashlib.sha256).hexdigest()
        expected_signature = f'v0={hash_for_verify}'

        # Securely compare signatures to prevent timing attacks
        if not hmac.compare_digest(expected_signature, zoom_signature):
            logger.warning("Unauthorized request: Signature does not match.")
            return False

        return True
    except Exception as e:
        logger.exception(f"Error validating Zoom request: {e}")
        return False

def get_access_token():
    """
    Retrieves an OAuth access token from Zoom.
    """
    try:
        url = "https://zoom.us/oauth/token"
        params = {
            "grant_type": "account_credentials",
            "account_id": ZOOM_ACCOUNT_ID
        }
        credentials = f"{ZOOM_CLIENT_ID}:{ZOOM_CLIENT_SECRET}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        response = requests.post(url, headers=headers, params=params)
        if response.status_code == 200:
            access_token = response.json().get('access_token')
            logger.info("Successfully obtained Zoom access token.")
            return access_token
        else:
            logger.error(f"Error fetching access token: {response.status_code} {response.text}")
            return None
    except Exception as e:
        logger.exception(f"Error fetching access token: {e}")
        return None

def get_meeting_recordings(meeting_id):
    """
    Retrieves recordings for a given meeting ID.
    Returns a tuple of (recording_files, recording_play_passcode).
    """
    try:
        access_token = get_access_token()
        if not access_token:
            logger.error("Cannot fetch recordings without access token.")
            return [], None

        url = f"https://api.zoom.us/v2/meetings/{meeting_id}/recordings"
        headers = {
            "Authorization": f"Bearer {access_token}"
        }
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            recordings_data = response.json()
            recording_files = recordings_data.get('recording_files', [])
            recording_play_passcode = recordings_data.get('recording_play_passcode', "")
            logger.info(f"Fetched {len(recording_files)} recordings for Meeting ID: {meeting_id}")
            return recording_files, recording_play_passcode
        else:
            logger.error(f"Error fetching recordings: {response.status_code} {response.text}")
            return [], None
    except Exception as e:
        logger.exception(f"Error fetching recordings: {e}")
        return [], None

def download_recording(recording_url, download_token):
    """
    Downloads the recording from Zoom and saves it locally.
    Returns the file path if successful, else None.
    """
    try:
        headers = {
            "Authorization": f"Bearer {download_token}"
        }
        response = requests.get(recording_url, headers=headers, stream=True)
        if response.status_code == 200:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp4") as temp_file:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        temp_file.write(chunk)
                temp_file_path = temp_file.name
            logger.info(f"Recording downloaded successfully: {temp_file_path}")
            return temp_file_path
        else:
            logger.error(f"Error downloading recording: {response.status_code} {response.text}")
            return None
    except Exception as e:
        logger.exception(f"Error downloading recording: {e}")
        return None

def get_meeting_participants(meeting_id):
    """
    Retrieves participants for a given meeting ID.
    Returns a list of participant emails.
    """
    try:
        access_token = get_access_token()
        if not access_token:
            logger.error("Cannot fetch participants without access token.")
            return []

        url = f"https://api.zoom.us/v2/meetings/{meeting_id}/participants"
        headers = {
            "Authorization": f"Bearer {access_token}"
        }
        params = {
            "page_size": 300  # Adjust as needed based on expected participant count
        }
        response = requests.get(url, headers=headers, params=params)
        if response.status_code == 200:
            participants_data = response.json()
            participants = [participant.get('email', 'Unknown Email') for participant in participants.get('participants', [])]
            logger.info(f"Fetched {len(participants)} participants for Meeting ID: {meeting_id}")
            return participants
        else:
            logger.error(f"Error fetching participants: {response.status_code} {response.text}")
            return []
    except Exception as e:
        logger.exception(f"Error fetching participants: {e}")
        return []
