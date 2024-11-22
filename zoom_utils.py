# zoom_utils.py

import os
import logging
import requests
import tempfile
import urllib.parse
import base64
import time

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
        headers = {
            "Authorization": f"Basic {base64.b64encode(f'{ZOOM_CLIENT_ID}:{ZOOM_CLIENT_SECRET}'.encode()).decode()}",
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

def get_meeting_recordings(meeting_id):
    """
    Fetches recordings for a specific meeting.
    """
    try:
        user_id = "me"  # 'me' refers to the authenticated user
        url = f"{ZOOM_API_BASE_URL}/users/{user_id}/recordings"
        params = {
            "meeting_id": meeting_id
        }
        response = requests.get(url, headers=get_zoom_headers(), params=params)
        response.raise_for_status()
        data = response.json()
        recordings = data.get('recording_files', [])
        play_passcode = data.get('play_passcode', '')
        logger.info(f"Fetched {len(recordings)} recordings for Meeting ID: {meeting_id}")
        return recordings, play_passcode
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error occurred: {http_err} - {response.text}")
        return None, None
    except Exception as e:
        logger.exception(f"Unexpected error fetching recordings: {e}")
        return None, None

def get_meeting_participants(meeting_id):
    """
    Fetches participants for a specific past meeting.
    """
    try:
        # Double encode the UUID if necessary
        if meeting_id.startswith("/") or "//" in meeting_id:
            meeting_id = urllib.parse.quote(urllib.parse.quote(meeting_id, safe=''), safe='')

        url = f"{ZOOM_API_BASE_URL}/past_meetings/{meeting_id}/participants"
        params = {
            "page_size": 30  # Adjust as needed
        }
        response = requests.get(url, headers=get_zoom_headers(), params=params)
        response.raise_for_status()
        data = response.json()
        participants = data.get('participants', [])
        logger.info(f"Fetched {len(participants)} participants for Meeting ID: {meeting_id}")
        return participants
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"HTTP error occurred: {http_err} - {response.text}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error fetching participants: {e}")
        return None

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
        # Save to a temporary file
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
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
