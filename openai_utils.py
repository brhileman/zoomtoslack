# openai_utils.py

import os
import logging
from openai import OpenAI, APIConnectionError, APIStatusError, RateLimitError
import json

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

# Ensure OpenAI API key is set
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
if not OPENAI_API_KEY:
    logger.error("OPENAI_API_KEY is not set in environment variables.")
    raise EnvironmentError("OPENAI_API_KEY is required.")

# Instantiate the OpenAI client
openai_client = OpenAI(
    api_key=OPENAI_API_KEY
)

def transcribe_audio(file_path):
    """
    Transcribes audio using OpenAI's Whisper API.
    
    Parameters:
        file_path (str): The path to the audio file to transcribe.
    
    Returns:
        str: The transcribed text or an empty string if transcription fails.
    """
    try:
        with open(file_path, "rb") as audio_file:
            transcript_response = openai_client.audio.transcriptions.create(
                file=audio_file,
                model="whisper-1"  # Specify the appropriate model
            )
        transcript = transcript_response.text
        logger.info("Transcription successful.")
        return transcript
    except (APIConnectionError, RateLimitError, APIStatusError) as api_err:
        logger.error(f"API error during transcription: {api_err}")
        return ""
    except Exception as e:
        logger.exception(f"Unexpected error during transcription: {e}")
        return ""

def determine_slack_channel(meeting_topic, meeting_summary, public_channels):
    """
    Determines the appropriate Slack channel to post the meeting summary to using OpenAI's ChatCompletion API.
    
    Parameters:
        meeting_topic (str): The topic of the meeting.
        meeting_summary (dict): The meeting summary overview.
        public_channels (list of dict): List of public channels with 'name', 'topic', and 'id'.
    
    Returns:
        str or None: The Slack channel ID (e.g., 'C012AB3CD'), or None if no suitable channel is found.
    """
    try:
        # Prepare channel data for OpenAI prompt
        channel_info = "\n".join([f"- Name: {channel['name']}, Topic: {channel['topic']}" for channel in public_channels])
        
        prompt = (
            "Based on the meeting topic and summary overview, determine the most appropriate Slack channel ID to post the meeting summary to.\n\n"
            f"Meeting Topic: {meeting_topic}\n"
            f"Summary Overview: {meeting_summary.get('summary_overview', '')}\n\n"
            "List of available Slack channels:\n"
            f"{channel_info}\n\n"
            "Provide only the Slack channel ID (e.g., C012AB3CD). If no suitable channel is found, respond with 'None'.\n\n"
            "Examples:\n"
            "- If the most appropriate channel is 'general' with ID 'C1234567890', respond with 'C1234567890'.\n"
            "- If no suitable channel exists, respond with 'None'.\n\n"
        )
        
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that categorizes information into Slack channels based on relevance."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=10,  # Reduced tokens since we expect a short response
            temperature=0.0,  # Lower temperature for more deterministic output
            n=1,
            stop=["\n"]
        )
        
        channel_id_raw = response.choices[0].message.content.strip()
        
        # Validate and extract the channel ID using regex
        # Slack channel IDs start with 'C' followed by alphanumeric characters, typically 8 or more characters long
        channel_id_match = re.match(r'^(C[A-Z0-9]{7,})$', channel_id_raw)
        if channel_id_match:
            channel_id = channel_id_match.group(1)
            logger.info(f"Determined Slack channel ID: {channel_id}")
            return channel_id
        elif channel_id_raw.lower() == 'none':
            logger.info("No suitable Slack channel found by OpenAI.")
            return None
        else:
            # Attempt to extract channel ID from a descriptive sentence
            extracted_id = re.search(r'(C[A-Z0-9]{7,})', channel_id_raw)
            if extracted_id:
                channel_id = extracted_id.group(1)
                logger.info(f"Extracted Slack channel ID from response: {channel_id}")
                return channel_id
            else:
                logger.warning(f"Unexpected response format from OpenAI: '{channel_id_raw}'")
                return None
    except (APIConnectionError, RateLimitError, APIStatusError) as api_err:
        logger.error(f"API error during Slack channel determination: {api_err}")
        return None
    except Exception as e:
        logger.exception(f"Unexpected error during Slack channel determination: {e}")
        return None

def generate_summary(transcript, meeting_title, host_email, meeting_id, meeting_date, meeting_time, duration):
    """
    Generates a structured summary from the transcript using OpenAI's ChatCompletion API.
    
    Parameters:
        transcript (str): The transcribed meeting audio.
        meeting_title (str): The title of the meeting.
        host_email (str): The host's email address.
        meeting_id (str): The Zoom meeting ID.
        meeting_date (str): The date of the meeting.
        meeting_time (str): The time of the meeting.
        duration (int): Duration of the meeting in minutes.
    
    Returns:
        dict: A structured summary containing meeting details, share details, and meeting summary.
    """
    try:
        prompt = (
            "You are an assistant that summarizes meeting transcripts into a structured JSON format.\n\n"
            "Please provide the summary in the following JSON format:\n\n"
            "{\n"
            "  \"meeting_details\": {\n"
            "    \"title\": \"\",\n"
            "    \"date_time\": \"\",\n"
            "    \"host_email\": \"\",\n"
            "    \"meeting_id\": \"\",\n"
            "    \"duration\": \"\"\n"
            "  },\n"
            "  \"share_details\": {\n"
            "    \"play_url\": \"\",\n"
            "    \"password\": \"\"\n"
            "  },\n"
            "  \"meeting_summary\": {\n"
            "    \"summary_overview\": \"\",\n"
            "    \"main_topics\": [\n"
            "      {\"topic\": \"\", \"timestamp\": \"\"},\n"
            "      ...\n"
            "    ],\n"
            "    \"action_items\": [\n"
            "      {\"action_item\": \"\", \"responsible\": \"\"},\n"
            "      ...\n"
            "    ]\n"
            "  }\n"
            "}\n\n"
            "Transcript:\n"
            f"{transcript}\n\n"
            "Please ensure the JSON structure is followed precisely."
        )
        response = openai_client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that summarizes meeting transcripts."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=1500,
            temperature=0.3,
            n=1,
            stop=None
        )
        summary_text = response.choices[0].message.content.strip()

        # Parse the JSON response
        summary_json = json.loads(summary_text)

        # Add meeting details
        summary_json['meeting_details'] = {
            "title": meeting_title,
            "date_time": f"{meeting_date} at {meeting_time}",
            "host_email": host_email,
            "meeting_id": meeting_id,
            "duration": duration
        }

        logger.info("Summary generation successful.")
        return summary_json
    except json.JSONDecodeError as json_err:
        logger.error(f"JSON decode error during summary parsing: {json_err}")
        logger.debug(f"Summary text: {summary_text}")
        return {}
    except (APIConnectionError, RateLimitError, APIStatusError) as api_err:
        logger.error(f"API error during summary generation: {api_err}")
        return {}
    except Exception as e:
        logger.exception(f"Unexpected error during summary generation: {e}")
        return {}
