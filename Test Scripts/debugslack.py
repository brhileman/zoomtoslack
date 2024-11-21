import os
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Get Slack Bot Token from environment
SLACK_BOT_TOKEN = os.getenv('SLACK_BOT_TOKEN')

# Initialize Slack client
if not SLACK_BOT_TOKEN:
    print("SLACK_BOT_TOKEN is not set. Please check your environment variables.")
else:
    print("SLACK_BOT_TOKEN loaded successfully.")
    slack_client = WebClient(token=SLACK_BOT_TOKEN)

    # Test Slack Authentication by listing channels
    try:
        response = slack_client.conversations_list()
        if response['ok']:
            channels = response['channels']
            print(f"Successfully fetched {len(channels)} channels.")
        else:
            print(f"Error fetching Slack channels: {response['error']}")
    except SlackApiError as e:
        print(f"Slack API Error: {e.response['error']}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")