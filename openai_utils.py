import openai
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
openai.api_key = OPENAI_API_KEY

def determine_slack_channel(meeting_topic, meeting_summary):
    try:
        channels = get_slack_channels()
        channels_list = ', '.join([f"#{channel}" for channel in channels.keys()])

        prompt = (
            f"Based on the following meeting topic and summary, determine the most appropriate Slack channel from the list: {channels_list}.\n"
            f"Meeting Topic: {meeting_topic}\n"
            f"Meeting Summary: {meeting_summary.get('summary_overview', 'No overview available.')}\n"
            f"Provide only the channel name, such as #general or #team-updates."
        )
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=10
        )
        channel_name = response.choices[0].message['content'].strip()
        return channel_name if channel_name in [f"#{channel}" for channel in channels.keys()] else "#zoom-meetings"
    except Exception as e:
        print(f"Error determining Slack channel: {e}")
        return "#zoom-meetings"
