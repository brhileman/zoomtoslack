import os
import json
import requests
import hmac
import hashlib
import base64
import time
from flask import Flask, request, jsonify
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
import openai
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

app = Flask(__name__)

# Load tokens and keys from environment variables
SLACK_BOT_TOKEN = os.getenv('SLACK_BOT_TOKEN')
ZOOM_WEBHOOK_SECRET_TOKEN = os.getenv('ZOOM_WEBHOOK_SECRET_TOKEN')
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
ZOOM_CLIENT_ID = os.getenv('ZOOM_CLIENT_ID')
ZOOM_CLIENT_SECRET = os.getenv('ZOOM_CLIENT_SECRET')
ZOOM_ACCOUNT_ID = os.getenv('ZOOM_ACCOUNT_ID')

slack_client = WebClient(token=SLACK_BOT_TOKEN)
openai.api_key = OPENAI_API_KEY

@app.route('/zoom-webhook', methods=['POST'])
def zoom_webhook():
    try:
        # Parse incoming JSON request
        data = request.json

        # Extract headers for verification
        zoom_signature = request.headers.get('x-zm-signature')
        zoom_timestamp = request.headers.get('x-zm-request-timestamp')

        # Check if the timestamp is within 5 minutes of current time to prevent replay attacks
        if abs(time.time() - int(zoom_timestamp)) > 300:
            print("Unauthorized request: Timestamp is too old.")
            return jsonify({'message': 'Unauthorized'}), 401

        # Validate the request is from Zoom
        message = f'v0:{zoom_timestamp}:{json.dumps(data, separators=(",", ":"))}'
        hash_for_verify = hmac.new(
            ZOOM_WEBHOOK_SECRET_TOKEN.encode(),
            message.encode(),
            hashlib.sha256
        ).hexdigest()
        expected_signature = f'v0={hash_for_verify}'

        if zoom_signature != expected_signature:
            print("Unauthorized request: Signature does not match.")
            return jsonify({'message': 'Unauthorized'}), 401

        # Handle URL validation event
        if data.get('event') == 'endpoint.url_validation':
            plain_token = data['payload']['plainToken']
            hash_for_validate = hmac.new(
                ZOOM_WEBHOOK_SECRET_TOKEN.encode(),
                plain_token.encode(),
                hashlib.sha256
            ).hexdigest()
            response = {
                "plainToken": plain_token,
                "encryptedToken": hash_for_validate
            }
            print(f"Zoom URL validation: Received plainToken={plain_token}")
            return jsonify(response), 200
        
        # Handle "Recording Completed" event
        if data.get('event') == 'recording.completed':
            recording_info = data['payload']['object']
            meeting_topic = recording_info.get('topic', 'No topic')
            meeting_id = recording_info['id']
            host_email = recording_info['host_email']
            share_url = recording_info.get('share_url', 'No share URL available')
            share_code = recording_info.get('share_code', 'No share code available')
            
            # Get meeting summary using Zoom API
            print(f"Fetching meeting summary for meeting ID: {meeting_id}")
            meeting_summary = get_meeting_summary(meeting_id)
            
            # Determine Slack channel using OpenAI
            print(f"Determining Slack channel for meeting topic: '{meeting_topic}' and summary: '{meeting_summary}'")
            slack_channel = determine_slack_channel(meeting_topic, meeting_summary)
            
            # Get channel ID
            channel_id = get_channel_id(slack_channel)
            if not channel_id:
                print(f"Channel '{slack_channel}' not found.")
                return jsonify({'message': 'Channel not found'}), 404
            
            # Join the Slack channel before posting
            print(f"Joining Slack channel: {slack_channel}")
            join_slack_channel(channel_id)
            
            # Package information about the recording
            recording_summary = (
                f"Meeting Summary for {meeting_topic}\n"
                f"{recording_info.get('start_time', 'Date Not Available')} ID: {meeting_id}\n"
                f"Quick recap\n\n"
                f"{meeting_summary}\n\n"
                f"Next steps\n\n"
                f"TBD\n\n"
                f"Summary\n\n"
                f"{meeting_summary}\n"
            )
            
            # Post the recording info into the determined Slack channel
            print(f"Posting to Slack channel: {slack_channel}")
            post_to_slack(channel_id, recording_summary)
        
        return jsonify({'message': 'Event received'}), 200
    except Exception as e:
        print(f"Error processing webhook: {e}")
        return jsonify({'message': 'Internal Server Error'}), 500

@app.route('/', methods=['GET'])
def index():
    return "The Zoom to Slack integration app is running successfully!", 200

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


def get_meeting_summary(meeting_id):
    try:
        access_token = get_access_token()
        if not access_token:
            return "No summary available."

        # Double-encode the meeting ID if it contains '/' or '//'
        if '/' in meeting_id:
            meeting_id = requests.utils.quote(requests.utils.quote(meeting_id, safe=''), safe='')

        url = f"https://api.zoom.us/v2/meetings/{meeting_id}/meeting_summary"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        print(f"Making API call to Zoom for meeting summary with URL: {url}")
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            summary_data = response.json()
            return summary_data.get('summary', 'No summary available.')
        else:
            print(f"Error fetching meeting summary: {response.status_code} {response.text}")
            return "No summary available."
    except Exception as e:
        print(f"Error fetching meeting summary: {e}")
        return "No summary available."


def get_slack_channels():
    try:
        print("Fetching Slack channels list")
        response = slack_client.conversations_list()
        if response['ok']:
            channels = response['channels']
            return {channel['name']: channel['id'] for channel in channels}
        else:
            print(f"Error fetching Slack channels: {response['error']}")
            return {}
    except SlackApiError as e:
        print(f"Error fetching Slack channels: {e.response['error']}")
        return {}


def get_channel_id(channel_name):
    channels = get_slack_channels()
    return channels.get(channel_name.lstrip('#'))


def determine_slack_channel(meeting_topic, meeting_summary):
    try:
        channels = get_slack_channels()
        channels_list = ', '.join([f"#{channel}" for channel in channels.keys()])

        prompt = (
            f"Based on the following meeting topic and summary, determine the most appropriate Slack channel from the list: {channels_list}.\n"
            f"Meeting Topic: {meeting_topic}\n"
            f"Meeting Summary: {meeting_summary}\n"
            f"Provide only the channel name, such as #general or #team-updates."
        )
        print(f"Sending prompt to OpenAI to determine Slack channel")
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "user", "content": prompt}
            ],
            max_tokens=10
        )
        channel_name = response.choices[0].message['content'].strip()
        return channel_name if channel_name in [f"#{channel}" for channel in channels.keys()] else "#zoom-meetings"
    except Exception as e:
        print(f"Error determining Slack channel: {e}")
        return "#zoom-meetings"


def join_slack_channel(channel_id):
    try:
        slack_client.conversations_join(channel=channel_id)
        print(f"Joined Slack channel with ID: {channel_id}")
    except SlackApiError as e:
        if e.response['error'] == 'method_not_supported_for_channel_type':
            print(f"Cannot join channel with ID {channel_id}. This might be a private channel.")
        else:
            print(f"Error joining Slack channel: {e.response['error']}")


def post_to_slack(channel_id, message):
    try:
        # Slack Bot Token-based API call to post a message
        print(f"Posting message to Slack channel with ID: {channel_id}")
        response = slack_client.chat_postMessage(
            channel=channel_id,
            text=message
        )
        print(f"Message posted to Slack: {response['ts']}")
    except SlackApiError as e:
        print(f"Error posting to Slack: {e.response['error']}")


if __name__ == '__main__':
    # Get the port from the environment variable and run the Flask app
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
