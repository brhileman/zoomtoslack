import openai
import os
import logging
from slack_utils import get_slack_channels

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

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY is not set in environment variables.")
    raise EnvironmentError("OPENAI_API_KEY is required.")

openai.api_key = OPENAI_API_KEY

def determine_slack_channel(meeting_topic, meeting_summary):
    try:
        channels_dict = get_slack_channels()
        if not channels_dict:
            logger.warning("No Slack channels fetched. Defaulting to #zoom-meetings.")
            return "#zoom-meetings"

        channels_list = ', '.join([f"#{channel}" for channel in channels_dict.keys()])

        prompt = (
            f"Based on the following meeting topic and summary, determine the most appropriate Slack channel from the list: {channels_list}.\n"
            f"Meeting Topic: {meeting_topic}\n"
            f"Meeting Summary: {meeting_summary.get('summary_overview', 'No overview available.')}\n"
            f"Provide only the channel name, such as #general or #team-updates."
        )

        logger.debug(f"OpenAI prompt: {prompt}")

        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=10,
            n=1,
            stop=None,
            temperature=0.3
        )
        channel_name = response.choices[0].message['content'].strip()
        logger.info(f"OpenAI suggested channel: {channel_name}")

        # Validate the channel name
        valid_channels = [f"#{channel}" for channel in channels_dict.keys()]
        if channel_name in valid_channels:
            return channel_name
        else:
            logger.warning(f"Suggested channel '{channel_name}' is not in the channels list. Defaulting to #zoom-meetings.")
            return "#zoom-meetings"

    except openai.error.RateLimitError:
        logger.error("OpenAI API rate limit exceeded. Using default channel '#zoom-meetings'.")
        return "#zoom-meetings"
    except openai.error.OpenAIError as e:
        logger.error(f"OpenAI API error: {e}. Using default channel '#zoom-meetings'.")
        return "#zoom-meetings"
    except Exception as e:
        logger.exception(f"Unexpected error in determine_slack_channel: {e}. Using default channel '#zoom-meetings'.")
        return "#zoom-meetings"
