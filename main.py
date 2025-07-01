from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import subprocess
import os
import uuid
import threading
import re

app = FastAPI()

# --------------------
# 경로 설정
# --------------------
STATIC_DIR = "./static"
DOWNLOAD_DIR = "./downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# --------------------
# StaticFiles mount
# --------------------
# /static → JS, CSS, 이미지 경로
app.mount("/static", StaticFiles(directory=STATIC_DIR, html=True), name="static")
app.mount("/downloads", StaticFiles(directory=DOWNLOAD_DIR), name="downloads")

# 루트 접속 시 → index.html
@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

# --------------------
# Job 상태 저장
# --------------------
jobs = {}

class DownloadRequest(BaseModel):
    referer: str
    video_id: str
    filename: str

# --------------------
# 다운로드 생성 엔드포인트
# --------------------
@app.post("/download")
async def start_download(req: DownloadRequest):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "downloading",
        "progress": 0,
        "filename": f"{req.filename}.mp4",
        "error": None
    }

    # yt-dlp 실행 (스레드)
    threading.Thread(target=run_download, args=(job_id, req)).start()

    return {"job_id": job_id}

# --------------------
# 상태 조회 엔드포인트
# --------------------
@app.get("/status/{job_id}")
async def get_status(job_id: str):
    job = jobs.get(job_id)
    if not job:
        return {"error": "Invalid job_id"}

    response = {
        "status": job["status"],
        "progress": job["progress"],
        "filename": job["filename"]
    }

    if job["status"] == "completed":
        response["download_url"] = f"/downloads/{job['filename']}"

    if job["error"]:
        response["error"] = job["error"]

    return response

# --------------------
# yt-dlp 실행 함수
# --------------------
def run_download(job_id, req: DownloadRequest):
    cdn_prefix = "vz-f9765c3e-82b"
    m3u8_url = f"https://{cdn_prefix}.b-cdn.net/{req.video_id}/playlist.m3u8"
    output_path = os.path.join(DOWNLOAD_DIR, f"{req.filename}.mp4")

    cmd = [
        "yt-dlp",
        "--progress-template", "%(progress._percent_str)s",
        "-o", output_path,
        "--referer", req.referer,
        "--hls-use-mpegts",
        m3u8_url
    ]

    try:
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in process.stdout:
            percent = parse_progress(line)
            if percent is not None:
                jobs[job_id]["progress"] = percent
        process.wait()

        if process.returncode == 0:
            jobs[job_id]["status"] = "completed"
            jobs[job_id]["progress"] = 100
        else:
            jobs[job_id]["status"] = "error"
            jobs[job_id]["error"] = f"yt-dlp exited with {process.returncode}"

    except Exception as e:
        jobs[job_id]["status"] = "error"
        jobs[job_id]["error"] = str(e)

# --------------------
# 진행률 파싱 함수
# --------------------
def parse_progress(line):
    match = re.search(r'(\d{1,3})%', line)
    if match:
        try:
            return int(match.group(1))
        except:
            return None
    return None

# --------------------
# 단일 비디오 파일 제공
# --------------------
@app.get("/video/{filename}")
async def serve_video(filename: str):
    path = os.path.join(DOWNLOAD_DIR, filename)
    if os.path.exists(path):
        return FileResponse(path, media_type="video/mp4", filename=filename)
    return {"error": "file not found"}
