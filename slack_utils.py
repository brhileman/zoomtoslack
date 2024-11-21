# slack_utils.py

import os
import logging
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Configure logging
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s %(levelname)s %(name)s %(message)s',
    handlers=[
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

SLACK_BOT_TOKEN = os.getenv('SLACK_BOT_TOKEN')
if not SLACK_BOT_TOKEN:
    logger.error("SLACK_BOT_TOKEN is not set in environment variables.")
    raise EnvironmentError("SLACK_BOT_TOKEN is required.")

client = WebClient(token=SLACK_BOT_TOKEN)

def get_channel_id(channel_name):
    """
    Retrieves the Slack channel ID for a given channel name.
    """
    try:
        response = client.conversations_list(types="public_channel,private_channel")
        channels = response['channels']
        for channel in channels:
            if channel['name'] == channel_name.strip("#"):
                logger.info(f"Found Slack channel '{channel_name}' with ID: {channel['id']}")
                return channel['id']
        logger.warning(f"Slack channel '{channel_name}' not found.")
        return None
    except SlackApiError as e:
        logger.error(f"Error fetching channels: {e.response['error']}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error fetching channels: {e}")
        return None

def join_slack_channel(channel_name):
    """
    Makes the bot join the specified Slack channel.
    """
    try:
        response = client.conversations_join(channel=channel_name)
        logger.info(f"Joined Slack channel '{channel_name}'.")
        return True
    except SlackApiError as e:
        if e.response['error'] == 'already_in_channel':
            logger.info(f"Already in Slack channel '{channel_name}'.")
            return True
        else:
            logger.error(f"Error joining channel '{channel_name}': {e.response['error']}")
            return False
    except Exception as e:
        logger.exception(f"Unexpected error joining channel '{channel_name}': {e}")
        return False

def post_to_slack(channel_id, message):
    """
    Posts a message to the specified Slack channel.
    """
    try:
        response = client.chat_postMessage(channel=channel_id, text=message)
        logger.info(f"Message posted to channel ID '{channel_id}'.")
        return True
    except SlackApiError as e:
        logger.error(f"Error posting message: {e.response['error']}")
        return False
    except Exception as e:
        logger.exception(f"Unexpected error posting message: {e}")
        return False
