import os
import time
import json
import hmac
import hashlib
import base64
import requests
import logging
from dotenv import load_dotenv

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

def get_meeting_summary(meeting_id):
    try:
        access_token = get_access_token()
        if not access_token:
            logger.error("Cannot fetch meeting summary without access token.")
            return {}

        # Encode meeting_id if necessary
        if '/' in str(meeting_id):
            meeting_id = requests.utils.quote(requests.utils.quote(str(meeting_id), safe=''), safe='')

        url = f"https://api.zoom.us/v2/meetings/{meeting_id}/meeting_summary"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            summary_data = response.json()
            logger.info(f"Fetched meeting summary for Meeting ID: {meeting_id}")
            return {
                "summary_overview": summary_data.get('summary_overview', 'No overview available.'),
                "next_steps": summary_data.get('next_steps', []),
                "summary_details": summary_data.get('summary_details', 'No detailed summary available.')
            }
        else:
            logger.error(f"Error fetching meeting summary: {response.status_code} {response.text}")
            return {}
    except Exception as e:
        logger.exception(f"Error fetching meeting summary: {e}")
        return {}
