# zoom_utils.py

import os
import logging
import requests
import tempfile
import urllib.parse

logger = logging.getLogger(__name__)

ZOOM_API_BASE_URL = "https://api.zoom.us/v2"

# Server-to-Server OAuth Access Token
ZOOM_OAUTH_ACCESS_TOKEN = os.getenv('ZOOM_OAUTH_ACCESS_TOKEN')  # Ensure this is set and valid

if not ZOOM_OAUTH_ACCESS_TOKEN:
    logger.error("ZOOM_OAUTH_ACCESS_TOKEN is not set in environment variables.")
    raise EnvironmentError("ZOOM_OAUTH_ACCESS_TOKEN is required.")

def get_zoom_headers():
    return {
        "Authorization": f"Bearer {ZOOM_OAUTH_ACCESS_TOKEN}",
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
