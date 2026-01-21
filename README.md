# AI VibeSync

**AI VibeSync** is a professional AI-powered backend that analyzes video vibes and recommends the perfect trending music for Instagram Reels, TikTok, WhatsApp Status, or any short-form content. It uses **Memories.ai** to analyze video content and **Gemini AI** to find trending music, while verifying official Spotify links for accuracy.

This repository is designed to run on **Render** as a backend API.

---

## Features

- 🎥 **Auto-Analysis:** Upload a video file and get the best trending music match automatically.
- 🧠 **AI Vibe Detection:** Fetches the summary of the video using AI for vibe analysis.
- 🍂 **Aesthetic Matching:** Searches trending songs on Instagram/TikTok with same aesthetic.
- 🔗 **Spotify Integration:** Returns only **Spotify links** for seamless integration with apps.
- ⚡ **FastAPI:** Designed for professional backend usage.

---

## Deployment on Render

### 1. Fork or Clone this repository

```bash
git clone [https://github.com/paraskavitkar/AI-VibeSync.git](https://github.com/paraskavitkar/AI-VibeSync.git)
cd AI-VibeSync

```

### 2. Set Environment Variables

On Render, navigate to **Settings → Environment → Environment Variables** and add the following:

```text
MEMORIES_API_KEY=<your_memories_api_key>
GEMINI_API_KEY=<your_gemini_api_key>
SPOTIFY_CLIENT_ID=<your_spotify_client_id>
SPOTIFY_CLIENT_SECRET=<your_spotify_client_secret>

```

> **Important:** Do not hardcode API keys in the repo. Render secrets ensure your keys stay safe.

### 3. Install Requirements

Render will automatically install dependencies based on `requirements.txt`. If running locally:

```bash
pip install -r requirements.txt

```

### 4. Start the API

Render automatically detects FastAPI. If running locally, use:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000

```

---

## API Usage

**Endpoint:** `/upload`

**Method:** `POST`

**Form Data:** `file` → video file to analyze

### Example using curl

```bash
curl -X POST "https://<your-render-service>[.onrender.com/upload](https://.onrender.com/upload)" \
  -F "file=@your_video.mp4"

```

### Response

```json
{
  "spotify_link": "[https://open.spotify.com/track/](https://open.spotify.com/track/)..."
}

```

---

## Technologies Used

* **[FastAPI](https://www.google.com/search?q=https://fastapi.tiangolo.com/)** - Modern Python API framework
* **[Spotify API / Spotipy](https://www.google.com/search?q=https://spotipy.readthedocs.io/)** - Search for tracks
* **[Google Gemini AI](https://www.google.com/search?q=https://deepmind.google/technologies/gemini/)** - Trend & content AI
* **[Memories.ai](https://www.google.com/search?q=https://memories.ai/)** - Video vibe analysis
* **[Tmpfiles.org](https://www.google.com/search?q=https://tmpfiles.org/)** - Temporary cloud upload

---

## License

MIT License

---

## Contact

[**Paras Kavitkar**](https://github.com/paraskavitkar/paraskavitkar)

```

```
