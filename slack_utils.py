import os
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

SLACK_BOT_TOKEN = os.getenv('SLACK_BOT_TOKEN')
slack_client = WebClient(token=SLACK_BOT_TOKEN)

def get_slack_channels():
    try:
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
        response = slack_client.chat_postMessage(channel=channel_id, text=message)
        print(f"Message posted to Slack: {response['ts']}")
    except SlackApiError as e:
        print(f"Error posting to Slack: {e.response['error']}")
