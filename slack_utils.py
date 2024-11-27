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

def get_all_public_channels():
    """
    Retrieves a list of all public Slack channels with their normalized names, topics, and IDs.
    
    Returns:
        list of dict: Each dictionary contains 'name', 'topic', and 'id' of a channel.
    """
    try:
        channels = []
        cursor = None
        while True:
            response = client.conversations_list(
                types="public_channel",
                limit=1000,
                cursor=cursor
            )
            for channel in response['channels']:
                channels.append({
                    'name': channel['name'].lower(),
                    'topic': channel['topic']['value'].lower(),
                    'id': channel['id']
                })
            cursor = response.get('response_metadata', {}).get('next_cursor')
            if not cursor:
                break
        logger.info(f"Retrieved {len(channels)} public channels from Slack.")
        return channels
    except SlackApiError as e:
        logger.error(f"Error fetching public channels: {e.response['error']}")
        return []
    except Exception as e:
        logger.exception(f"Unexpected error fetching public channels: {e}")
        return []

def join_slack_channel(channel_id):
    """
    Makes the bot join the specified Slack channel by ID.
    
    Parameters:
        channel_id (str): The ID of the Slack channel to join.
    
    Returns:
        bool: True if successful or already in the channel, False otherwise.
    """
    try:
        response = client.conversations_join(channel=channel_id)
        logger.info(f"Joined Slack channel ID '{channel_id}'.")
        return True
    except SlackApiError as e:
        if e.response['error'] == 'already_in_channel':
            logger.info(f"Already in Slack channel ID '{channel_id}'.")
            return True
        else:
            logger.error(f"Error joining Slack channel ID '{channel_id}': {e.response['error']}")
            return False
    except Exception as e:
        logger.exception(f"Unexpected error joining Slack channel ID '{channel_id}': {e}")
        return False

def post_to_slack(channel_id, message):
    """
    Posts a message to the specified Slack channel by ID.
    
    Parameters:
        channel_id (str): The ID of the Slack channel to post the message to.
        message (str): The message content to post.
    
    Returns:
        bool: True if the message was posted successfully, False otherwise.
    """
    try:
        response = client.chat_postMessage(channel=channel_id, text=message)
        logger.info(f"Message posted to channel ID '{channel_id}' with timestamp {response['ts']}.")
        return True
    except SlackApiError as e:
        if e.response['error'] == 'channel_not_found':
            logger.error(f"Slack channel ID '{channel_id}' not found.")
        elif e.response['error'] == 'missing_scope':
            logger.error(f"Slack app is missing necessary scopes: {e.response['error']}")
        else:
            logger.error(f"Error posting message to Slack: {e.response['error']}")
        return False
    except Exception as e:
        logger.exception(f"Unexpected error posting message to Slack: {e}")
        return False

def ensure_default_channel_exists(default_channel_name="bot-lost-meeting-recordings"):
    """
    Ensures that the default Slack channel exists. If it doesn't, attempts to create it.
    Returns the channel ID if successful, else None.
    
    Parameters:
        default_channel_name (str): The name of the default Slack channel.
    
    Returns:
        str or None: The ID of the default Slack channel, or None if creation failed.
    """
    try:
        # Fetch all public channels
        public_channels = get_all_public_channels()
        # Normalize the default channel name
        normalized_default_name = default_channel_name.lower()
        # Search for the default channel
        for channel in public_channels:
            if channel['name'] == normalized_default_name:
                logger.info(f"Default Slack channel '{default_channel_name}' already exists with ID: {channel['id']}")
                return channel['id']
        
        # If not found, attempt to create it
        response = client.conversations_create(name=default_channel_name)
        channel = response['channel']
        logger.info(f"Created default Slack channel '{default_channel_name}' with ID: {channel['id']}")
        return channel['id']
    except SlackApiError as e:
        if e.response['error'] == 'name_taken':
            logger.warning(f"Slack channel '{default_channel_name}' already exists.")
            # Fetch the channel ID again
            public_channels = get_all_public_channels()
            for channel in public_channels:
                if channel['name'] == default_channel_name.lower():
                    return channel['id']
        else:
            logger.error(f"Error creating default Slack channel '{default_channel_name}': {e.response['error']}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error ensuring default Slack channel exists: {e}")
        return None
