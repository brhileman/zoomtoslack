import os
import time
import json
import hmac
import hashlib
import base64
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

ZOOM_CLIENT_ID = os.getenv('ZOOM_CLIENT_ID')
ZOOM_CLIENT_SECRET = os.getenv('ZOOM_CLIENT_SECRET')
ZOOM_ACCOUNT_ID = os.getenv('ZOOM_ACCOUNT_ID')

def validate_zoom_request(secret_token, zoom_signature, zoom_timestamp, data):
    if abs(time.time() - int(zoom_timestamp)) > 300:
        print("Unauthorized request: Timestamp is too old.")
        return False

    message = f'v0:{zoom_timestamp}:{json.dumps(data, separators=(",", ":"))}'
    hash_for_verify = hmac.new(secret_token.encode(), message.encode(), hashlib.sha256).hexdigest()
    expected_signature = f'v0={hash_for_verify}'

    if zoom_signature != expected_signature:
        print("Unauthorized request: Signature does not match.")
        return False

    return True

def get_access_token():
    try:
        url = f"https://zoom.us/oauth/token?grant_type=account_credentials&account_id={ZOOM_ACCOUNT_ID}"
        credentials = f"{ZOOM_CLIENT_ID}:{ZOOM_CLIENT_SECRET}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        response = requests.post(url, headers=headers)
        if response.status_code == 200:
            return response.json().get('access_token')
        else:
            print(f"Error fetching access token: {response.status_code} {response.text}")
            return None
    except Exception as e:
        print(f"Error fetching access token: {e}")
        return None

def get_meeting_summary(meeting_id):
    try:
        access_token = get_access_token()
        if not access_token:
            return {}

        if '/' in meeting_id:
            meeting_id = requests.utils.quote(requests.utils.quote(meeting_id, safe=''), safe='')

        url = f"https://api.zoom.us/v2/meetings/{meeting_id}/meeting_summary"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            summary_data = response.json()
            return {
                "summary_overview": summary_data.get('summary_overview', 'No overview available.'),
                "next_steps": summary_data.get('next_steps', []),
                "summary_details": summary_data.get('summary_details', 'No detailed summary available.')
            }
        else:
            print(f"Error fetching meeting summary: {response.status_code} {response.text}")
            return {}
    except Exception as e:
        print(f"Error fetching meeting summary: {e}")
        return {}
