import os
import requests
from dotenv import load_dotenv
import base64

# Load environment variables from .env file
load_dotenv()

# Load Zoom credentials from environment variables
ZOOM_CLIENT_ID = os.getenv('ZOOM_CLIENT_ID')
ZOOM_CLIENT_SECRET = os.getenv('ZOOM_CLIENT_SECRET')
ZOOM_ACCOUNT_ID = os.getenv('ZOOM_ACCOUNT_ID')


def get_access_token():
    try:
        url = f"https://zoom.us/oauth/token?grant_type=account_credentials&account_id={ZOOM_ACCOUNT_ID}"
        credentials = f"{ZOOM_CLIENT_ID}:{ZOOM_CLIENT_SECRET}"
        encoded_credentials = base64.b64encode(credentials.encode()).decode()
        headers = {
            "Authorization": f"Basic {encoded_credentials}",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        print(f"Requesting Zoom access token")
        response = requests.post(url, headers=headers)
        
        if response.status_code == 200:
            return response.json().get('access_token')
        else:
            print(f"Error fetching access token: {response.status_code} {response.text}")
            return None
    except Exception as e:
        print(f"Error fetching access token: {e}")
        return None


def get_all_recordings():
    access_token = get_access_token()
    if not access_token:
        print("Unable to get access token. Exiting.")
        return

    url = "https://api.zoom.us/v2/users/me/recordings"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    print(f"Fetching all Zoom recordings")
    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        recordings_data = response.json()
        for recording in recordings_data.get('meetings', []):
            print(f"Full Meeting Details: {recording}")
    else:
        print(f"Error fetching recordings: {response.status_code} {response.text}")


if __name__ == '__main__':
    get_all_recordings()
