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

# 다운로드 경로 설정
DOWNLOAD_DIR = "./downloads"
STATIC_DIR = "./static"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# 웹 UI 서빙
app.mount("/web", StaticFiles(directory=STATIC_DIR, html=True), name="static")
app.mount("/downloads", StaticFiles(directory=DOWNLOAD_DIR), name="downloads")

# 다운로드 작업 상태 저장소
jobs = {}

# 클라이언트가 보내는 요청 형식
class DownloadRequest(BaseModel):
    referer: str
    video_id: str
    filename: str

# 다운로드 생성 (비동기 스레드 실행)
@app.post("/download")
async def start_download(req: DownloadRequest):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "downloading",
        "progress": 0,
        "filename": f"{req.filename}.mp4",
        "error": None
    }
    threading.Thread(target=run_download, args=(job_id, req)).start()
    return {"job_id": job_id}

# 다운로드 진행상황 조회
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

# 실제 다운로드 실행 (백그라운드 스레드)
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

    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)

    try:
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

# yt-dlp 출력에서 % 진행률 파싱
def parse_progress(line):
    match = re.search(r'(\d{1,3})%', line)
    if match:
        try:
            return int(match.group(1))
        except:
            return None
    return None

# 비디오 제공
@app.get("/video/{filename}")
async def serve_video(filename: str):
    path = os.path.join(DOWNLOAD_DIR, filename)
    if os.path.exists(path):
        return FileResponse(path, media_type="video/mp4", filename=filename)
    return {"error": "file not found"}

@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))
