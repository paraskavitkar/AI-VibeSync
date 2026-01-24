import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from fastapi.responses import StreamingResponse
from fastapi import FastAPI

# Mocking the pipeline generator logic
def mock_process_video_pipeline(filename):
    yield "Step 1: Uploading...\n"
    yield "Step 2: AI Processing...\n"
    yield "DOWNLOAD_LINK: /downloads/song.mp3\n"

# Mocking the FastAPI app logic we want to implement
app = FastAPI()

@app.get("/upload_mock")
def upload_mock(debug: bool = False):
    if debug:
        return StreamingResponse(mock_process_video_pipeline("test.mp4"), media_type="text/plain")
    else:
        # Simulate blocking consumption
        last_line = ""
        for line in mock_process_video_pipeline("test.mp4"):
            last_line = line

        # If successfully reached end
        if "DOWNLOAD_LINK" in last_line:
            # logic to return file
            return {"status": "file returned"}
        return {"status": "error"}

client = TestClient(app)

def test_streaming_debug_true():
    response = client.get("/upload_mock?debug=true")
    assert response.status_code == 200
    # TestClient.text returns the full content
    content = response.text
    assert "Step 1: Uploading..." in content
    assert "Step 2: AI Processing..." in content
    assert "DOWNLOAD_LINK: /downloads/song.mp3" in content

def test_streaming_debug_false():
    response = client.get("/upload_mock?debug=false")
    assert response.status_code == 200
    json_resp = response.json()
    assert json_resp == {"status": "file returned"}
