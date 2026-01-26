import os
import sys
import time
import json
import requests
import spotipy
import yt_dlp
from spotipy.oauth2 import SpotifyClientCredentials
from google import genai
from google.genai import types

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
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
            files_dict = {'file': f}
            response = requests.post(url, files=files_dict)
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
    print(f"\n🔗 Sending link to Memories.ai...")
    endpoint = "https://api.memories.ai/serve/api/v1/upload_url"
    headers = {"Authorization": MEMORIES_API_KEY}
    payload = {"url": video_url}
    try:
        response = requests.post(endpoint, headers=headers, data=payload)
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                vid_id = data['data']['videoNo']
                print(f"✅ AI Accepted Video! ID: {vid_id}")
                return vid_id
    except Exception as e:
        print(f"❌ Connection Error: {e}")
    return None

def wait_for_ready_gen(video_id):
    yield "⏳ AI is watching the video..."
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
                        yield "\n✅ Video is Ready!"
                        yield True
                        return
                    elif status == "FAIL":
                        yield False
                        return
            yield "."
            time.sleep(3)
        except:
            yield False
            return

def wait_for_ready(video_id):
    gen = wait_for_ready_gen(video_id)
    result = False
    for item in gen:
        if isinstance(item, bool):
            result = item
        else:
            sys.stdout.write(item)
            sys.stdout.flush()
    print()
    return result

def get_summary(video_id):
    print("📝 Fetching Summary...")
    endpoint = "https://api.memories.ai/serve/api/v1/generate_summary"
    headers = {"Authorization": MEMORIES_API_KEY}
    response = requests.get(endpoint, headers=headers, params={"video_no": video_id, "type": "TOPIC"})
    if response.status_code == 200:
        data = response.json()
        if data.get("success"):
            summary_text = data['data']['summary']
            print("\n" + "="*30 + "\n✨ VIDEO SUMMARY ✨\n" + "="*30)
            print(summary_text)
            return summary_text
    return None

# --- MUSIC MATCHING & DOWNLOAD HANDOFF ---

def get_real_spotify_url(song_name):
    if not sp: return "Spotify Not Connected"
    try:
        results = sp.search(q=song_name, limit=1, type='track')
        items = results.get('tracks', {}).get('items', [])
        if items:
            return items[0]['external_urls']['spotify']
    except:
        pass
    return "Link not found on Spotify"

def get_perfect_song_match(summary):
    print("🔎 Searching trending charts for your vibe...")
    search_tool = types.Tool(google_search=types.GoogleSearch())

    prompt = f"""
    1. Search for CURRENT trending Instagram Reels/TikTok songs (July 2025 till now) that match this specific vibe: "{summary}".
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
        elif json_string.startswith('```') and json_string.endswith('```'):
            # Fallback for just ```
             json_string = json_string[len('```'):-len('```')].strip()

        data = json.loads(json_string)
        real_link = get_real_spotify_url(data.get('song_name'))

        print("\n" + "🍂" * 20 + "\n🎵 PERFECT COZY MATCH FOUND 🎵\n" + "🍂" * 20)
        print(f"🎶 Song:       {data.get('song_name')}")
        print(f"🔗 Spotify:    {real_link}")
        print(f"⏱️ Start At:   {data.get('trending_start_time')}")
        print(f"✨ Vibe:       {data.get('reasoning')}")
        print("🍂" * 20)

        return real_link

    except Exception as e:
        print(f"❌ Error in matching: {e}")
        # Log raw response if possible, though 'response' might not be defined if error happens earlier
        # print(f"📄 Raw Response: {response.text}")
        return None

def download_spotify_as_mp3(url):
    if not url or "spotify.com" not in url:
        print("❌ No valid Spotify URL to download.")
        return None

    try:
        track = sp.track(url)
        search_query = f"{track['artists'][0]['name']} - {track['name']} official audio"
        output = f"{DOWNLOAD_DIR}/{track['name']}"

        ydl_opts = {
            'format': 'bestaudio/best',
            'outtmpl': f'{output}.%(ext)s',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'quiet': False, # Keep it verbose like Colab
            'noplaylist': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            print(f"🚀 Downloading from YouTube: {search_query}")
            ydl.download([f"ytsearch1:{search_query}"])

        print(f"✅ Success! Saved to {output}.mp3")
        return f"{output}.mp3"

    except Exception as e:
        print(f"❌ Download Error: {e}")
        return None

# --- PIPELINE GENERATOR ---

def process_video_pipeline(filename):
    yield "Starting processing...\n"

    yield f"Step 1: Uploading '{filename}' to tmpfiles.org...\n"
    cloud_link = upload_to_tmpfiles(filename)
    if not cloud_link:
        yield "❌ tmpfiles upload failed\n"
        return

    yield "Step 2: Sending to Memories.ai...\n"
    video_id = send_link_to_ai(cloud_link)
    if not video_id:
        yield "❌ video processing failed (send link)\n"
        return

    yield f"Step 3: Waiting for AI processing (ID: {video_id})...\n"
    success = False
    for item in wait_for_ready_gen(video_id):
        if isinstance(item, bool):
            success = item
        else:
            yield f"{item}" # yield exactly what wait_for_ready_gen yields
            if not item.endswith("\n") and item != ".":
                 yield "\n"

    if not success:
        yield "❌ video processing failed (wait)\n"
        return

    yield "Step 4: Fetching summary...\n"
    summary = get_summary(video_id)
    if not summary:
        yield "❌ summary failed\n"
        return
    yield f"Summary: {summary}\n"

    yield "Step 5: Matching song...\n"
    spotify_link = get_perfect_song_match(summary)

    if not spotify_link:
        yield "❌ No song match found\n"
        return

    yield f"Spotify Link: {spotify_link}\n"

    yield "Step 6: Downloading MP3...\n"
    mp3_path = download_spotify_as_mp3(spotify_link)

    if not mp3_path:
        yield "❌ Download failed\n"
        return

    filename_only = os.path.basename(mp3_path)
    # Using a clear marker for the client to parse if needed
    yield f"DOWNLOAD_READY: /downloads/{filename_only}\n"

# --- FASTAPI WRAPPER ---

app = FastAPI()
app.mount("/downloads", StaticFiles(directory=DOWNLOAD_DIR), name="downloads")

@app.post("/upload")
async def upload_video(file: UploadFile = File(...), debug: bool = False):
    filename = file.filename

    with open(filename, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    if debug:
        return StreamingResponse(process_video_pipeline(filename), media_type="text/plain")

    # Default behavior: Consume the pipeline to allow code reuse
    gen = process_video_pipeline(filename)
    last_msg = ""
    try:
        for msg in gen:
            last_msg = msg
            print(msg.strip()) # Log to server console
    except Exception as e:
        print(f"Pipeline error: {e}")
        return JSONResponse({"error": str(e)}, 500)

    # Check for success marker
    if last_msg.startswith("DOWNLOAD_READY: "):
        path_part = last_msg.replace("DOWNLOAD_READY: ", "").strip()
        # path_part is like "/downloads/filename.mp3"
        basename = os.path.basename(path_part)
        local_path = os.path.join(DOWNLOAD_DIR, basename)

        if os.path.exists(local_path):
            return FileResponse(local_path, media_type="audio/mpeg", filename=basename)
        else:
            return JSONResponse({"error": "File not found after processing"}, 500)
    else:
        # Pass the last message as the error reason
        return JSONResponse({"error": f"Processing failed: {last_msg.strip()}"}, 500)
