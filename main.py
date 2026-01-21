import os
import sys
import time
import json
import requests
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from google import genai
from google.genai import types
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse

# --- CONFIGURATION ---
MEMORIES_API_KEY = os.getenv("MEMORIES_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

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

# --- PART 1: VIDEO PROCESSING FUNCTIONS ---

def upload_to_tmpfiles(filename):
    print(f"[UPLOAD] Uploading '{filename}' to tmpfiles.org...")
    url = "https://tmpfiles.org/api/v1/upload"

    try:
        with open(filename, 'rb') as f:
            response = requests.post(url, files={'file': f})

        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'success':
                direct_url = data['data']['url'].replace("tmpfiles.org/", "tmpfiles.org/dl/")
                print(f"[UPLOAD] Success: {direct_url}")
                return direct_url
        print(f"[UPLOAD] Failed: {response.text}")
        return None

    except Exception as e:
        print(f"[UPLOAD] Error: {e}")
        return None

def send_link_to_ai(video_url):
    print("[MEMORIES] Sending video to AI...")
    endpoint = "https://api.memories.ai/serve/api/v1/upload_url"
    headers = {"Authorization": MEMORIES_API_KEY}
    payload = {"url": video_url}

    try:
        response = requests.post(endpoint, headers=headers, data=payload)
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                vid_id = data['data']['videoNo']
                print(f"[MEMORIES] Video Accepted: ID {vid_id}")
                return vid_id
        print(f"[MEMORIES] Rejected or Failed: {response.text}")
    except Exception as e:
        print(f"[MEMORIES] Connection Error: {e}")
    return None

def wait_for_ready(video_id):
    print("[MEMORIES] Waiting for AI to parse video...")
    endpoint = "https://api.memories.ai/serve/api/v1/list_videos"
    headers = {"Authorization": MEMORIES_API_KEY}

    while True:
        try:
            response = requests.post(endpoint, headers=headers, json={"video_no": video_id})
            if response.status_code == 200:
                data = response.json()
                videos = data.get("data", {}).get("videos", [])
                if videos:
                    status = videos[0].get("status")
                    if status == "PARSE":
                        print("[MEMORIES] Video ready!")
                        return True
                    elif status == "FAIL":
                        print("[MEMORIES] AI Failed to process video.")
                        return False
            sys.stdout.write(".")
            sys.stdout.flush()
            time.sleep(3)
        except Exception as e:
            print(f"[MEMORIES] Error: {e}")
            return False

def get_summary(video_id):
    print("[MEMORIES] Fetching summary...")
    endpoint = "https://api.memories.ai/serve/api/v1/generate_summary"
    headers = {"Authorization": MEMORIES_API_KEY}

    response = requests.get(endpoint, headers=headers, params={"video_no": video_id, "type": "TOPIC"})
    if response.status_code == 200:
        data = response.json()
        if data.get("success"):
            summary_text = data['data']['summary']
            print("[MEMORIES] Summary fetched successfully.")
            return summary_text
    return None

# --- PART 2: MUSIC MATCHING ---

def get_real_spotify_url(song_name):
    if not sp: return "Spotify Not Connected"
    try:
        results = sp.search(q=song_name, limit=1, type='track')
        items = results.get('tracks', {}).get('items', [])
        if items:
            return items[0]['external_urls']['spotify']
    except Exception:
        pass
    return "Link not found on Spotify"

def get_perfect_song_match(summary):
    print("[GEMINI] Searching trending songs...")
    search_tool = types.Tool(google_search=types.GoogleSearch())

    prompt = f"""
    1. Search for CURRENT trending Instagram Reels/TikTok songs (July 2025 till now) that match this specific vibe: "{summary}".
    2. Look for "Cozy", "Autumn aesthetic", or "Slow living" trends.
    3. Pick the SINGLE best song match from the **top lists of Instagram story add music feature**.
    4. Identify the "Trending Start Time" (e.g. the specific guitar loop or beat drop creators use).

    OUTPUT FORMAT (Strict JSON):
    {{
      "song_name": "Artist - Song Title",
      "trending_start_time": "0:XX",
      "reasoning": "Why this specific song fits the coffee/bed/autumn aesthetic"
    }}
    """

    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(tools=[search_tool])
        )

        json_string = response.text.strip()
        if json_string.startswith('```json') and json_string.endswith('```'):
            json_string = json_string[len('```json'):-len('```')].strip()
        data = json.loads(json_string)

        real_link = get_real_spotify_url(data.get('song_name'))
        print(f"[RESULT] Song: {data.get('song_name')} | Spotify: {real_link}")
        return real_link
    except Exception as e:
        print(f"[GEMINI] Error: {e}")
        return None

# --- FASTAPI BACKEND ---

app = FastAPI(title="AI VibeSync", description="AI-powered music matcher for your videos", version="1.0")

@app.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    filename = f"/tmp/{file.filename}"
    with open(filename, "wb") as f:
        f.write(await file.read())
    print(f"[UPLOAD] Received file: {file.filename}")

    # 1. Upload to tmpfiles
    cloud_link = upload_to_tmpfiles(filename)
    if not cloud_link:
        return JSONResponse(content={"error": "Upload failed"}, status_code=500)

    # 2. Send to Memories.ai
    video_id = send_link_to_ai(cloud_link)
    if not video_id:
        return JSONResponse(content={"error": "AI upload failed"}, status_code=500)

    # 3. Wait & summarize
    if not wait_for_ready(video_id):
        return JSONResponse(content={"error": "Video processing failed"}, status_code=500)
    summary = get_summary(video_id)
    if not summary:
        return JSONResponse(content={"error": "Summary failed"}, status_code=500)

    # 4. Get Spotify link
    spotify_link = get_perfect_song_match(summary)
    if not spotify_link:
        return JSONResponse(content={"error": "Spotify search failed"}, status_code=500)

    return {"spotify_link": spotify_link}
