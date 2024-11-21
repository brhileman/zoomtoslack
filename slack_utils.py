import os
import logging
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
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

SLACK_BOT_TOKEN = os.getenv('SLACK_BOT_TOKEN')
if not SLACK_BOT_TOKEN:
    logger.error("SLACK_BOT_TOKEN is not set in environment variables.")
    raise EnvironmentError("SLACK_BOT_TOKEN is required.")

slack_client = WebClient(token=SLACK_BOT_TOKEN)

def get_slack_channels():
    try:
        response = slack_client.conversations_list(types="public_channel,private_channel")
        if response['ok']:
            channels = response['channels']
            channels_dict = {channel['name']: channel['id'] for channel in channels}
            logger.info(f"Fetched Slack Channels: {', '.join(channels_dict.keys())}")
            return channels_dict
        else:
            logger.error(f"Error fetching Slack channels: {response['error']}")
            return {}
    except SlackApiError as e:
        logger.error(f"Slack API Error while fetching channels: {e.response['error']}")
        return {}
    except Exception as e:
        logger.exception(f"Unexpected error while fetching Slack channels: {e}")
        return {}

def get_channel_id(channel_name):
    channels = get_slack_channels()
    channel_id = channels.get(channel_name.lstrip('#'))
    if channel_id:
        logger.info(f"Found channel ID for '{channel_name}': {channel_id}")
    else:
        logger.warning(f"Channel '{channel_name}' not found.")
    return channel_id

def join_slack_channel(channel_name):
    try:
        # Attempt to join the channel by ID
        channel_id = get_channel_id(channel_name)
        if not channel_id:
            logger.error(f"Cannot join channel '{channel_name}' because it was not found.")
            return False

        response = slack_client.conversations_join(channel=channel_id)
        if response['ok']:
            logger.info(f"Joined Slack channel: {channel_name}")
            return True
        else:
            logger.error(f"Error joining Slack channel '{channel_name}': {response['error']}")
            return False
    except SlackApiError as e:
        if e.response['error'] == 'already_in_channel':
            logger.info(f"Already a member of channel '{channel_name}'.")
            return True
        else:
            logger.error(f"Slack API Error while joining channel '{channel_name}': {e.response['error']}")
            return False
    except Exception as e:
        logger.exception(f"Unexpected error while joining Slack channel '{channel_name}': {e}")
        return False

def post_to_slack(channel_id, message):
    try:
        response = slack_client.chat_postMessage(channel=channel_id, text=message)
        if response['ok']:
            logger.info(f"Message posted to Slack channel ID '{channel_id}' at {response['ts']}.")
        else:
            logger.error(f"Error posting message to Slack: {response['error']}")
    except SlackApiError as e:
        logger.error(f"Slack API Error while posting message: {e.response['error']}")
    except Exception as e:
        logger.exception(f"Unexpected error while posting message to Slack: {e}")
