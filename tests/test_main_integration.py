import sys
import os
from unittest.mock import MagicMock, patch

# Mock dependencies before importing main to handle global init
with patch.dict(os.environ, {
    "MEMORIES_API_KEY": "test_memories_key",
    "GEMINI_API_KEY": "test_gemini_key",
    "SPOTIFY_CLIENT_ID": "test_spotify_id",
    "SPOTIFY_CLIENT_SECRET": "test_spotify_secret"
}):
    # Patch google.genai.Client to avoid instantiation error
    with patch("google.genai.Client") as MockClient:
        # Patch spotipy credentials and client
        with patch("spotipy.oauth2.SpotifyClientCredentials"):
            with patch("spotipy.Spotify") as MockSpotify:
                import main

from fastapi.testclient import TestClient

client = TestClient(main.app)

def test_upload_debug_true():
    # Mock the pipeline steps
    with patch("main.upload_to_tmpfiles", return_value="http://tmp/file"):
        with patch("main.send_link_to_ai", return_value="123"):
            # wait_for_ready_gen needs to yield status then True
            with patch("main.wait_for_ready_gen", side_effect=lambda vid: iter(["Ready", True])):
                with patch("main.get_summary", return_value="Cool vibes"):
                    with patch("main.get_perfect_song_match", return_value="http://spotify/track"):
                        with patch("main.download_spotify_as_mp3", return_value="downloads/track.mp3"):

                            # Create a dummy file
                            with open("test_video.mp4", "wb") as f:
                                f.write(b"video data")

                            response = client.post(
                                "/upload?debug=true",
                                files={"file": ("test_video.mp4", b"video data", "video/mp4")}
                            )

                            assert response.status_code == 200
                            content = response.text
                            # print(content)
                            assert "Step 1" in content
                            assert "DOWNLOAD_READY: /downloads/track.mp3" in content

                            # Cleanup
                            if os.path.exists("test_video.mp4"):
                                os.remove("test_video.mp4")

def test_upload_debug_false():
    # Mock the pipeline steps
    with patch("main.upload_to_tmpfiles", return_value="http://tmp/file"):
        with patch("main.send_link_to_ai", return_value="123"):
            # Now even non-debug uses wait_for_ready_gen via the pipeline
            with patch("main.wait_for_ready_gen", side_effect=lambda vid: iter(["Ready", True])):
                with patch("main.get_summary", return_value="Cool vibes"):
                    with patch("main.get_perfect_song_match", return_value="http://spotify/track"):
                        with patch("main.download_spotify_as_mp3", return_value="downloads/track.mp3"):

                            # Ensure download dir and file exist
                            os.makedirs("downloads", exist_ok=True)
                            with open("downloads/track.mp3", "wb") as f:
                                f.write(b"mp3 data")

                            response = client.post(
                                "/upload",
                                files={"file": ("test_video.mp4", b"video data", "video/mp4")}
                            )

                            assert response.status_code == 200
                            assert response.headers["content-type"] == "audio/mpeg"
