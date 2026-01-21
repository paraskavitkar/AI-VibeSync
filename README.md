# AI VibeSync

AI VibeSync is a professional AI-powered backend that analyzes video vibes and recommends the perfect trending music for Instagram Reels, TikTok, WhatsApp Status, or any short-form content. It uses **Memories.ai** to analyze video content and **Gemini AI** to find trending music, while verifying official Spotify links for accuracy.

This repository is designed to run on **Render** as a backend API.

---

## Features

- Upload a video file and get the best trending music match automatically.
- Fetches the summary of the video using AI for vibe analysis.
- Searches trending songs on Instagram/TikTok with a "Cozy / Autumn / Slow living" aesthetic.
- Returns only **Spotify link** for seamless integration with apps.
- Designed for professional backend usage with **FastAPI**.

---

## Deployment on Render

1. **Fork or Clone this repository**:

```bash
git clone https://github.com/paraskavitkar/AI-VibeSync.git
cd AI-VibeSync
Set Environment Variables on Render (Settings → Environment → Environment Variables):

text
Copy code
MEMORIES_API_KEY=<your_memories_api_key>
GEMINI_API_KEY=<your_gemini_api_key>
SPOTIFY_CLIENT_ID=<your_spotify_client_id>
SPOTIFY_CLIENT_SECRET=<your_spotify_client_secret>
Important: Do not hardcode API keys in the repo. Render secrets ensure your keys stay safe.

Install requirements (Render does this automatically):

bash
Copy code
pip install -r requirements.txt
Start the API:

Render automatically detects FastAPI. If running locally:

bash
Copy code
uvicorn main:app --host 0.0.0.0 --port 8000
API Usage
Endpoint: /upload
Method: POST
Form Data: file → video file to analyze

Example with curl:

bash
Copy code
curl -X POST "https://<your-render-service>.onrender.com/upload" \
  -F "file=@your_video.mp4"
Response:

json
Copy code
{
  "spotify_link": "https://open.spotify.com/track/XXXXXXXXX"
}

Technologies Used
FastAPI - Modern Python API framework

Spotify API / Spotipy - Search for tracks

Google Gemini AI - Trend & content AI

Memories.ai - Video vibe analysis

Tmpfiles.org - Temporary cloud upload

License
MIT License

Contact
Paras Kavitkar"# AI-VibeSync" 
