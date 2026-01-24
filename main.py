import os
import sys
import time
import json
import re
import requests
import spotipy
import yt_dlp
from yt_dlp.utils import DownloadError
from spotipy.oauth2 import SpotifyClientCredentials
from google import genai
from google.genai import types

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
import shutil

# --- CONFIGURATION ---
MEMORIES_API_KEY = os.getenv("MEMORIES_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# --- CLIENT INITIALIZATION ---
client = genai.Client(api_key=GEMINI_API_KEY)

try:
    sp_auth = SpotifyClientCredentials(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET
    )
    sp = spotipy.Spotify(auth_manager=sp_auth)
except Exception as e:
    print(f"⚠️ Spotify Auth Failed: {e}")
    sp = None

# --- VIDEO PROCESSING FUNCTIONS ---

def upload_to_tmpfiles(filename):
    print(f"📤 Uploading '{filename}' to tmpfiles.org...")
    url = "https://tmpfiles.org/api/v1/upload"
    try:
        with open(filename, 'rb') as f:
            response = requests.post(url, files={'file': f})
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'success':
                original_url = data['data']['url']
                direct_url = original_url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
                print(f"✅ Upload Success! Direct Link: {direct_url}")
                return direct_url
        raise Exception(f"Tmpfiles upload failed: {response.text}")
    except Exception as e:
        print(f"❌ Error during upload: {e}")
        raise e

def send_link_to_ai(video_url):
    print("🔗 Sending link to Memories.ai...")
    endpoint = "https://api.memories.ai/serve/api/v1/upload_url"
    headers = {"Authorization": MEMORIES_API_KEY}
    payload = {"url": video_url}
    response = requests.post(endpoint, headers=headers, data=payload)
    if response.status_code == 200:
        data = response.json()
        if data.get("success"):
            vid_id = data['data']['videoNo']
            print(f"✅ AI Accepted Video! ID: {vid_id}")
            return vid_id
        raise Exception(f"Memories.ai upload failed: {data.get('message', 'Unknown error')}")
    raise Exception(f"Memories.ai API Error: {response.status_code} - {response.text}")

def check_video_status(video_id):
    endpoint = "https://api.memories.ai/serve/api/v1/list_videos"
    headers = {"Authorization": MEMORIES_API_KEY}
    response = requests.post(endpoint, headers=headers, json={"video_no": video_id})
    if response.status_code == 200:
        data = response.json()
        videos = data.get("data", {}).get("videos", [])
        if videos:
            return videos[0].get("status")
    return None

def get_summary(video_id):
    print("📝 Fetching Summary...")
    endpoint = "https://api.memories.ai/serve/api/v1/generate_summary"
    headers = {"Authorization": MEMORIES_API_KEY}
    response = requests.get(endpoint, headers=headers, params={"video_no": video_id, "type": "TOPIC"})
    if response.status_code == 200:
        data = response.json()
        if data.get("success"):
            return data['data']['summary']
        raise Exception(f"Summary generation failed: {data.get('message')}")
    raise Exception(f"Summary API Error: {response.status_code}")

# --- MUSIC MATCHING & DOWNLOAD HANDOFF ---

def get_real_spotify_url(song_name):
    if not sp:
        return None
    results = sp.search(q=song_name, limit=1, type='track')
    items = results.get('tracks', {}).get('items', [])
    if items:
        return items[0]['external_urls']['spotify']
    return None

def get_perfect_song_match(summary):
    print("🔎 Searching trending charts for your vibe...")
    search_tool = types.Tool(google_search=types.GoogleSearch())

    prompt = f"""
    1. Search for CURRENT trending Instagram Reels/TikTok songs (July 2025 till now) that match this specific vibe: "{summary}".
    3. Pick the SINGLE best song match from the **top lists of Instagram story add music feature**.
    4. Identify the "Trending Start Time".

    OUTPUT FORMAT (Strict JSON):
    {{
      "song_name": "Artist - Song Title",
      "trending_start_time": "0:XX",
      "reasoning": "Why it fits"
    }}
    """

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(tools=[search_tool])
    )

    if not response.text:
        raise Exception("Gemini returned no text. Possible safety block or empty response.")

    json_string = response.text.strip()
    if json_string.startswith('```'):
        parts = json_string.split("```")
        if len(parts) > 1:
            json_string = parts[1].strip()
            if json_string.lower().startswith("json"):
                json_string = json_string[4:].strip()

    try:
        data = json.loads(json_string)
        return get_real_spotify_url(data.get("song_name"))
    except json.JSONDecodeError:
        raise Exception(f"Failed to parse JSON from Gemini: {json_string}")

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name)

def download_spotify_as_mp3(url):
    if not url:
        return None

    track = sp.track(url)
    search_query = f"{track['artists'][0]['name']} - {track['name']} official audio"
    safe_name = sanitize_filename(track['name'])
    output = f"{DOWNLOAD_DIR}/{safe_name}"

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': f'{output}.%(ext)s',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'noplaylist': True,
        'nocheckcertificate': True,
        'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    }

    try:
        print(f"🎵 Attempting to download via YouTube: {search_query}")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"ytsearch1:{search_query}"])
    except DownloadError as e:
        print(f"⚠️ YouTube download failed: {e}")
        print(f"🔄 Trying SoundCloud fallback for: {search_query}")
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([f"scsearch1:{search_query}"])
        except Exception as e2:
            raise Exception(f"SoundCloud fallback also failed: {e2}")

    return f"{output}.mp3"

def process_video_gen(filename):
    yield "Step 1: Uploading video to tmpfiles.org..."
    try:
        cloud_link = upload_to_tmpfiles(filename)
        yield f"Upload successful: {cloud_link}"
    except Exception as e:
        yield f"Error: {str(e)}"
        return

    yield "Step 2: Sending video to Memories.ai..."
    try:
        video_id = send_link_to_ai(cloud_link)
        yield f"Video accepted. ID: {video_id}"
    except Exception as e:
        yield f"Error: {str(e)}"
        return

    yield "Step 3: Waiting for AI processing..."
    while True:
        try:
            status = check_video_status(video_id)
            if status == "PARSE":
                yield "AI processing complete."
                break
            elif status == "FAIL":
                yield "Error: AI processing failed."
                return
            else:
                yield "Waiting for AI..."
                time.sleep(3)
        except Exception as e:
             yield f"Error checking status: {str(e)}"
             time.sleep(3)

    yield "Step 4: Fetching video summary..."
    try:
        summary = get_summary(video_id)
        yield f"Summary fetched: {summary[:50]}..."
    except Exception as e:
        yield f"Error: {str(e)}"
        return

    yield "Step 5: Matching song with Gemini AI..."
    try:
        spotify_link = get_perfect_song_match(summary)
        if not spotify_link:
            yield "Error: No matching song found."
            return
        yield f"Match found: {spotify_link}"
    except Exception as e:
        yield f"Error: {str(e)}"
        return

    yield "Step 6: Downloading song as MP3..."
    try:
        mp3_path = download_spotify_as_mp3(spotify_link)
        if not mp3_path or not os.path.exists(mp3_path):
             yield "Error: MP3 download failed."
             return
        yield "Download complete."
    except Exception as e:
        yield f"Error: {str(e)}"
        return

    yield f"SUCCESS: {mp3_path}"

# --- FASTAPI WRAPPER (ONLY INPUT/OUTPUT CHANGE) ---

app = FastAPI()

@app.post("/upload")
def upload_video(file: UploadFile = File(...)):
    filename = file.filename
    with open(filename, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    generator = process_video_gen(filename)
    last_message = ""

    for message in generator:
        print(message)
        last_message = message
        if message.startswith("Error:"):
            return JSONResponse({"error": message}, 500)

    if last_message.startswith("SUCCESS:"):
        mp3_path = last_message.replace("SUCCESS: ", "")
        return FileResponse(
            mp3_path,
            media_type="audio/mpeg",
            filename=os.path.basename(mp3_path)
        )

    return JSONResponse({"error": "Process incomplete", "last_message": last_message}, 500)

@app.post("/debug")
def debug_video(file: UploadFile = File(...)):
    filename = file.filename
    with open(filename, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    def stream_generator():
        for message in process_video_gen(filename):
            yield message + "\n"

    return StreamingResponse(stream_generator(), media_type="text/plain")
