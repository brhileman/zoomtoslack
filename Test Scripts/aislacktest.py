import openai
import os
from dotenv import load_dotenv
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Load environment variables from .env file
load_dotenv()

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
SLACK_BOT_TOKEN = os.getenv('SLACK_BOT_TOKEN')

client = openai.OpenAI(api_key=OPENAI_API_KEY)
slack_client = WebClient(token=SLACK_BOT_TOKEN)

def test_determine_slack_channel():
    # Mocked data for testing
    meeting_topic = "Zoom to Slack App Project Meeting"
    meeting_summary = {
        'summary_overview': "Discussion about the Zoom to Slack app project, including integration details and next steps."
    }

    try:
        # Fetch Slack channels list
        response = slack_client.conversations_list()
        if response['ok']:
            channels = response['channels']
            channels_dict = {channel['name']: channel['id'] for channel in channels}
            print(f"Fetched Slack Channels: {channels_dict}")
        else:
            print(f"Error fetching Slack channels: {response['error']}")
            return
    except SlackApiError as e:
        print(f"Slack API Error: {e.response['error']}")
        return
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return

    channels_list = ', '.join([f"#{channel}" for channel in channels_dict.keys()])

    prompt = (
        f"Based on the following meeting topic and summary, determine the most appropriate Slack channel from the list: {channels_list}.\n"
        f"Meeting Topic: {meeting_topic}\n"
        f"Meeting Summary: {meeting_summary.get('summary_overview', 'No overview available.')}\n"
        f"Provide only the channel name, such as #general or #team-updates."
    )

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=10
        )
        channel_name = response.choices[0].message.content.strip()
        print(f"Suggested Slack Channel: {channel_name}")
    except Exception as e:
        if "insufficient_quota" in str(e):
            print("Quota exceeded, using mocked response.")
            channel_name = "#zoom-meetings"
            print(f"Suggested Slack Channel (Mocked): {channel_name}")
        else:
            print(f"Error determining Slack channel: {e}")

if __name__ == "__main__":
    test_determine_slack_channel()
