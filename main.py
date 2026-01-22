import os
import sys
import time
import json
import requests
import spotipy
import yt_dlp
import uvicorn
from spotipy.oauth2 import SpotifyClientCredentials
from google import genai
from google.genai import types
from fastapi import FastAPI, File, UploadFile
from fastapi.responses import JSONResponse

# --- CONFIGURATION FROM ENV VARIABLES ---
MEMORIES_API_KEY = os.getenv("MEMORIES_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")

# --- CLIENT INITIALIZATION ---
client = genai.Client(api_key=GEMINI_API_KEY)

# Spotify Auth
try:
    sp_auth = SpotifyClientCredentials(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET
    )
    sp = spotipy.Spotify(auth_manager=sp_auth)
except Exception as e:
    print(f"⚠️ Spotify Auth Failed: {e}")
    sp = None

# --- FASTAPI APP ---
app = FastAPI(title="AI VibeSync")

@app.get("/wake")
def wake():
    """Simple wake-up route to reduce cold start delay"""
    return {"status": "awake"}

# --- HELPER FUNCTIONS ---

def upload_to_tmpfiles(file_path):
    print(f"[INFO] Uploading '{file_path}' to tmpfiles.org...")
    url = "https://tmpfiles.org/api/v1/upload"
    try:
        with open(file_path, 'rb') as f:
            response = requests.post(url, files={"file": f})
        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 'success':
                original_url = data['data']['url']
                direct_url = original_url.replace("tmpfiles.org/", "tmpfiles.org/dl/")
                print(f"[SUCCESS] Upload complete: {direct_url}")
                return direct_url
    except Exception as e:
        print(f"[ERROR] Exception during upload: {e}")
    return None

def send_link_to_ai(video_url):
    print("[INFO] Sending link to Memories.ai...")
    endpoint = "https://api.memories.ai/serve/api/v1/upload_url"
    headers = {"Authorization": MEMORIES_API_KEY}
    payload = {"url": video_url}
    try:
        response = requests.post(endpoint, headers=headers, data=payload)
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                return data['data']['videoNo']
    except Exception as e:
        print(f"[ERROR] AI Link Exception: {e}")
    return None

def wait_for_ready(video_id):
    print("[INFO] AI is watching the video...")
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
                        return True
                    elif status == "FAIL":
                        return False
            time.sleep(3)
        except:
            return False

def get_summary(video_id):
    endpoint = "https://api.memories.ai/serve/api/v1/generate_summary"
    headers = {"Authorization": MEMORIES_API_KEY}
    response = requests.get(endpoint, headers=headers, params={"video_no": video_id, "type": "TOPIC"})
    if response.status_code == 200:
        data = response.json()
        if data.get("success"):
            return data['data']['summary']
    return None

def get_real_spotify_url(song_name):
    if not sp: return "Spotify Not Connected"
    try:
        results = sp.search(q=song_name, limit=1, type='track')
        items = results.get('tracks', {}).get('items', [])
        if items:
            return items[0]['external_urls']['spotify']
    except:
        pass
    return "Link not found"

def get_perfect_song_match(summary):
    print("[INFO] Searching trending charts via Gemini 2.5 Flash...")
    search_tool = types.Tool(google_search=types.GoogleSearch())
    prompt = f"""
    1. Search for CURRENT trending Instagram Reels/TikTok songs (July 2025 till now) that match this specific vibe: "{summary}".
    2. Pick the SINGLE best song match from the **top lists of Instagram story add music feature**.
    3. Identify the "Trending Start Time" (e.g. the specific guitar loop or beat drop creators use).

    OUTPUT FORMAT (Strict JSON):
    {{
      "song_name": "Artist - Song Title",
      "trending_start_time": "0:XX",
      "reasoning": "Why this specific song fits the aesthetic"
    }}
    """
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=prompt,
            config=types.GenerateContentConfig(tools=[search_tool])
        )
        json_string = response.text.strip()
        if '```json' in json_string:
            json_string = json_string.split('```json')[1].split('```')[0].strip()
        data = json.loads(json_string)
        real_link = get_real_spotify_url(data.get('song_name'))
        
        data["spotify_link"] = real_link
        return data
    except Exception as e:
        print(f"[ERROR] Gemini Match: {e}")
        return None

# --- DOWNLOAD LOGIC (CODE 2 INTEGRATION) ---

def download_vibe_audio(song_name):
    """
    Downloads audio using SoundCloud as the primary source to avoid 
    YouTube's bot detection on cloud servers.
    """
    # Use SoundCloud search prefix (scsearch1:)
    search_query = f"scsearch1:{song_name} official"
    safe_name = "".join(x for x in song_name if x.isalnum() or x in " -_").strip()
    output_tmpl = f"/tmp/{safe_name}.%(ext)s"

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': output_tmpl,
        'quiet': True,
        'noplaylist': True,
        # Browser impersonation headers
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
            'Accept': '*/*',
            'Accept-Language': 'en-US,en;q=0.5',
        }
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f"[INFO] Searching SoundCloud for: {song_name}")
            info = ydl.extract_info(search_query, download=True)
            # Find the actual filename created (might be .webm or .m4a)
            actual_filename = ydl.prepare_filename(info)
            return actual_filename
    except Exception as sc_error:
        print(f"[WARNING] SoundCloud search failed: {sc_error}")
        # Secondary fallback to YouTube if SoundCloud fails
        try:
            print(f"[INFO] Falling back to YouTube search...")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(f"ytsearch1:{song_name} audio", download=True)
                return ydl.prepare_filename(info)
        except Exception as yt_error:
            print(f"[ERROR] All download sources failed: {yt_error}")
            return None
        
# --- FASTAPI UPLOAD ROUTE ---

@app.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    temp_path = f"/tmp/{file.filename}"
    with open(temp_path, "wb") as f:
        f.write(await file.read())

    # 1. Upload to cloud
    cloud_link = upload_to_tmpfiles(temp_path)
    if not cloud_link:
        return JSONResponse({"error": "Upload failed"}, status_code=500)

    # 2. Process with AI
    video_id = send_link_to_ai(cloud_link)
    if not video_id or not wait_for_ready(video_id):
        return JSONResponse({"error": "AI processing failed"}, status_code=500)

    # 3. Summarize
    video_summary = get_summary(video_id)
    if not video_summary:
        return JSONResponse({"error": "Summary failed"}, status_code=500)

    # 4. Find Song
    song_data = get_perfect_song_match(video_summary)
    if not song_data or "spotify.com" not in song_data.get("spotify_link", ""):
        return JSONResponse({"error": "Song match failed"}, status_code=500)

    # 5. AUTOMATIC DOWNLOAD (SoundCloud First)
    final_audio_path = download_vibe_audio(song_data.get("song_name"))
    
    if final_audio_path:
        song_data["download_status"] = "success"
        song_data["local_path"] = final_audio_path
    else:
        song_data["download_status"] = "failed"

    return song_data

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))


