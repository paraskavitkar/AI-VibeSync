import os
import sys
import time
import json
import re
import requests
import spotipy
import yt_dlp
from spotipy.oauth2 import SpotifyClientCredentials
from google import genai
from google.genai import types

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
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
        return None
    except Exception as e:
        print(f"❌ Error during upload: {e}")
        return None

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
    return None

def wait_for_ready(video_id):
    print("⏳ AI is watching the video...")
    endpoint = "https://api.memories.ai/serve/api/v1/list_videos"
    headers = {"Authorization": MEMORIES_API_KEY}
    while True:
        response = requests.post(endpoint, headers=headers, json={"video_no": video_id})
        if response.status_code == 200:
            data = response.json()
            videos = data.get("data", {}).get("videos", [])
            if videos:
                status = videos[0].get("status")
                if status == "PARSE":
                    print("✅ Video is Ready!")
                    return True
                if status == "FAIL":
                    return False
        sys.stdout.write(".")
        sys.stdout.flush()
        time.sleep(3)

def get_summary(video_id):
    print("📝 Fetching Summary...")
    endpoint = "https://api.memories.ai/serve/api/v1/generate_summary"
    headers = {"Authorization": MEMORIES_API_KEY}
    response = requests.get(endpoint, headers=headers, params={"video_no": video_id, "type": "TOPIC"})
    if response.status_code == 200:
        data = response.json()
        if data.get("success"):
            return data['data']['summary']
    return None

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

    json_string = response.text.strip()
    if json_string.startswith('```'):
        parts = json_string.split("```")
        if len(parts) > 1:
            json_string = parts[1].strip()
            if json_string.lower().startswith("json"):
                json_string = json_string[4:].strip()

    data = json.loads(json_string)
    return get_real_spotify_url(data.get("song_name"))

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
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([f"ytsearch1:{search_query}"])

    return f"{output}.mp3"

# --- FASTAPI WRAPPER (ONLY INPUT/OUTPUT CHANGE) ---

app = FastAPI()

@app.post("/upload")
def upload_video(file: UploadFile = File(...)):
    filename = file.filename

    with open(filename, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    cloud_link = upload_to_tmpfiles(filename)
    if not cloud_link:
        return JSONResponse({"error": "tmpfiles upload failed"}, 500)

    video_id = send_link_to_ai(cloud_link)
    if not video_id or not wait_for_ready(video_id):
        return JSONResponse({"error": "video processing failed"}, 500)

    summary = get_summary(video_id)
    if not summary:
        return JSONResponse({"error": "summary failed"}, 500)

    spotify_link = get_perfect_song_match(summary)
    mp3_path = download_spotify_as_mp3(spotify_link)

    if not mp3_path or not os.path.exists(mp3_path):
        return JSONResponse({"error": "mp3 download failed"}, 500)

    return FileResponse(
        mp3_path,
        media_type="audio/mpeg",
        filename=os.path.basename(mp3_path)
    )
