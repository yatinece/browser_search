
from youtube_transcript_api import YouTubeTranscriptApi

video_id = "Avvh9tWLoLc"

# List all available transcripts (includes language codes)
transcripts = YouTubeTranscriptApi.list_transcripts(video_id)

for transcript in transcripts:
    print(f"Language: {transcript.language}, Code: {transcript.language_code}, Generated: {transcript.is_generated}")

# Fetch Hindi transcript (auto-generated or uploaded)
transcript = transcripts.find_transcript(['en'])  # 'hi' for Hindi
entries = transcript.fetch()

# Extract text
full_text = " ".join([entry.text for entry in entries])
print(full_text)
