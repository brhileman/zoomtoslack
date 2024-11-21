# openai_utils.py

import os
import logging
import openai

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

openai.api_key = OPENAI_API_KEY

def transcribe_audio(file_path):
    """
    Transcribes audio using OpenAI's Whisper API.
    """
    try:
        with open(file_path, "rb") as audio_file:
            transcript = openai.Audio.transcribe("whisper-1", audio_file)
        logger.info("Transcription successful.")
        return transcript['text']
    except Exception as e:
        logger.exception(f"Error transcribing audio: {e}")
        return ""

def generate_summary(transcript, meeting_title, host_email, meeting_id, meeting_date, meeting_time, participants, duration):
    """
    Generates a structured summary from the transcript using OpenAI's ChatCompletion API.
    Returns a dictionary with 'meeting_details', 'share_details', 'meeting_summary'.
    """
    try:
        prompt = (
            "You are an assistant that summarizes meeting transcripts into a structured format.\n\n"
            "Please provide the summary in the following format:\n\n"
            "1. **Meeting Title & Basic Details:**\n"
            f"   - **Title:** {meeting_title}\n"
            f"   - **Date & Time:** {meeting_date} at {meeting_time}\n"
            f"   - **Host Email:** {host_email}\n"
            f"   - **Meeting ID:** {meeting_id}\n\n"
            "2. **Share Details:**\n"
            f"   - **Play URL:** [Provide the Play URL]\n"
            f"   - **Password:** [Provide the Password]\n\n"
            "3. **Meeting Summary:**\n"
            "   - **Brief Overview:** [Provide a brief overview]\n"
            "   - **Main Topics Discussed:**\n"
            "     - **Topic 1:** [Description] (Timestamp: [HH:MM])\n"
            "     - **Topic 2:** [Description] (Timestamp: [HH:MM])\n"
            "     - ...\n"
            "   - **Action Items:**\n"
            "     - **Action Item 1:** [Description] (Responsible: [Name])\n"
            "     - **Action Item 2:** [Description] (Responsible: [Name])\n"
            "     - ...\n\n"
            "Participants:\n"
            f"{', '.join(participants)}\n\n"
            "Transcript:\n"
            f"{transcript}\n\n"
            "Please fill in the placeholders with appropriate content based on the transcript."
        )
        response = openai.ChatCompletion.create(
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
        summary_text = response.choices[0].message['content'].strip()

        # Parse the summary into structured sections
        meeting_details = {
            "title": meeting_title,
            "date_time": f"{meeting_date} at {meeting_time}",
            "host_email": host_email,
            "meeting_id": meeting_id,
            "participants": participants,
            "duration": duration
        }

        # Initialize summary sections
        summary_overview = ""
        main_topics = []
        action_items = ""
        play_url = ""
        password = ""

        # Simple parsing logic based on section headers
        lines = summary_text.split('\n')
        current_section = None
        for line in lines:
            line = line.strip()
            if line.startswith("1. **Meeting Title & Basic Details:**"):
                current_section = "details"
                continue
            elif line.startswith("2. **Share Details:**"):
                current_section = "share_details"
                continue
            elif line.startswith("3. **Meeting Summary:**"):
                current_section = "summary"
                continue

            if current_section == "share_details":
                if line.startswith("- **Play URL:**"):
                    play_url = line.replace("- **Play URL:**", "").strip()
                elif line.startswith("- **Password:**"):
                    password = line.replace("- **Password:**", "").strip()
            elif current_section == "summary":
                if line.startswith("- **Brief Overview:**"):
                    overview = line.replace("- **Brief Overview:**", "").strip()
                    summary_overview = overview
                elif line.startswith("- **Main Topics Discussed:**"):
                    current_subsection = "main_topics"
                elif line.startswith("- **Action Items:**"):
                    current_subsection = "action_items"
                elif line.startswith("- **") and current_subsection == "main_topics":
                    # Extract topic and timestamp
                    try:
                        topic_part = line.split("**")[2]  # Extract text between second and third **
                        desc_part = line.split("[Description]")[1].strip().strip("()")
                        timestamp = desc_part.replace("Timestamp:", "").strip()
                        main_topics.append({"topic": topic_part, "timestamp": timestamp})
                    except IndexError:
                        continue
                elif line.startswith("- **") and current_subsection == "action_items":
                    # Extract action item and responsible person
                    try:
                        action_part = line.split("**")[2]  # Extract text between second and third **
                        resp_part = line.split("[Description]")[1].strip().strip("()").replace("Responsible:", "").strip()
                        action_items += f"- **{action_part}** (Responsible: {resp_part})\n"
                    except IndexError:
                        continue

        # Clean up the parsed sections
        summary_overview = summary_overview.strip()
        summary_details = ""
        for topic in main_topics:
            summary_details += f"- **{topic['topic']}** (Timestamp: {topic['timestamp']})\n"

        logger.info("Summary generation successful.")
        return {
            "meeting_details": meeting_details,
            "share_details": {
                "play_url": play_url,
                "password": password
            },
            "meeting_summary": {
                "summary_overview": summary_overview,
                "main_topics": main_topics,
                "action_items": action_items.strip()
            }
        }

def determine_slack_channel(meeting_topic, meeting_summary):
    """
    Determines the appropriate Slack channel to post the meeting summary to using OpenAI's ChatCompletion API.
    Returns the Slack channel name as a string.
    """
    try:
        prompt = (
            "Based on the meeting topic and summary overview, determine the most appropriate public Slack channel to post the meeting summary to.\n\n"
            f"Meeting Topic: {meeting_topic}\n"
            f"Summary Overview: {meeting_summary.get('summary_overview', '')}\n\n"
            "Provide only the Slack channel name (e.g., general, product-team). If unsure, suggest 'general'."
        )
        response = openai.ChatCompletion.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that categorizes information into public Slack channels."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=10,
            temperature=0.3,
            n=1,
            stop=["\n"]
        )
        channel_name = response.choices[0].message['content'].strip().lower()
        logger.info(f"Determined Slack channel: {channel_name}")
        return channel_name
    except Exception as e:
        logger.exception(f"Error determining Slack channel: {e}")
        return "general"
