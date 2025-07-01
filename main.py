from fastapi import FastAPI, Form
from fastapi.responses import StreamingResponse, FileResponse
import subprocess
import os

app = FastAPI()
DOWNLOAD_DIR = "./downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

@app.post("/download")
def download_video(
    referer: str = Form(...),
    video_id: str = Form(...),
    filename: str = Form(...)
):
    cdn_prefix = "vz-f9765c3e-82b"
    m3u8_url = f"https://{cdn_prefix}.b-cdn.net/{video_id}/playlist.m3u8"
    output_path = os.path.join(DOWNLOAD_DIR, f"{filename}.mp4")

    cmd = [
        "yt-dlp",
        "--progress-template", "Downloading: %(progress._percent_str)s",
        "-o", output_path,
        "--referer", referer,
        "--hls-use-mpegts",
        m3u8_url
    ]

    def run_ytdlp():
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in process.stdout:
            yield line
        process.wait()
        yield f"\n✅ Download complete. Exit code: {process.returncode}\n"

    return StreamingResponse(run_ytdlp(), media_type="text/plain")


@app.get("/video/{filename}")
def serve_video(filename: str):
    path = os.path.join(DOWNLOAD_DIR, filename)
    if os.path.exists(path):
        return FileResponse(path, media_type="video/mp4", filename=filename)
    return {"error": "file not found"}
