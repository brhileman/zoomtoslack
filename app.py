import os
import json
import requests
import hmac
import hashlib
import base64
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
ZOOM_VERIFICATION_TOKEN = os.getenv('ZOOM_VERIFICATION_TOKEN')
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

        # Handle URL validation event
        if data.get('event') == 'endpoint.url_validation':
            plain_token = data['payload']['plainToken']
            print(f"Zoom URL validation: Received plainToken={plain_token}")
            return jsonify({"plainToken": plain_token}), 200
        
        # Verify the verification token
        if data.get('token') != ZOOM_VERIFICATION_TOKEN:
            print("Unauthorized request: Verification token does not match.")
            return jsonify({'message': 'Unauthorized'}), 401
        
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
            
            # Package information about the recording
            recording_summary = (
                f"New Zoom recording available:\n"
                f"Meeting Topic: {meeting_topic}\n"
                f"Meeting ID: {meeting_id}\n"
                f"Host: {host_email}\n"
                f"Share URL: {share_url}\n"
                f"Share Code: {share_code}\n"
                f"Meeting Summary: {meeting_summary}\n"
            )
            
            # Post the recording info into the determined Slack channel
            print(f"Posting to Slack channel: {slack_channel}")
            post_to_slack(slack_channel, recording_summary)
        
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
            return [channel['name'] for channel in channels]
        else:
            print(f"Error fetching Slack channels: {response['error']}")
            return []
    except SlackApiError as e:
        print(f"Error fetching Slack channels: {e.response['error']}")
        return []


def determine_slack_channel(meeting_topic, meeting_summary):
    try:
        channels = get_slack_channels()
        channels_list = ', '.join([f"#{channel}" for channel in channels])

        prompt = (
            f"Based on the following meeting topic and summary, determine the most appropriate Slack channel from the list: {channels_list}.\n"
            f"Meeting Topic: {meeting_topic}\n"
            f"Meeting Summary: {meeting_summary}\n"
            f"Provide only the channel name, such as #general or #team-updates."
        )
        print(f"Sending prompt to OpenAI to determine Slack channel")
        response = openai.Completion.create(
            engine="text-davinci-003",
            prompt=prompt,
            max_tokens=10
        )
        channel_name = response.choices[0].text.strip()
        return channel_name if channel_name in [f"#{channel}" for channel in channels] else "#zoom-meetings"
    except Exception as e:
        print(f"Error determining Slack channel: {e}")
        return "#zoom-meetings"


def post_to_slack(channel, message):
    try:
        # Slack Bot Token-based API call to post a message
        print(f"Posting message to Slack channel: {channel}")
        response = slack_client.chat_postMessage(
            channel=channel,
            text=message
        )
        print(f"Message posted to Slack: {response['ts']}")
    except SlackApiError as e:
        print(f"Error posting to Slack: {e.response['error']}")


if __name__ == '__main__':
    # Get the port from the environment variable and run the Flask app
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
