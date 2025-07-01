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

# 경로 설정
STATIC_DIR = "./static"
DOWNLOAD_DIR = "./downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ✅ StaticFiles 서비스 경로 분리
# /static 경로로 JS, CSS, 이미지 등 정적 파일 제공
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/downloads", StaticFiles(directory=DOWNLOAD_DIR), name="downloads")

# ✅ 루트(/) 접속 시 index.html 반환
@app.get("/")
async def serve_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


# ========================
# 다운로드 요청/상태 관리
# ========================
jobs = {}

class DownloadRequest(BaseModel):
    referer: str
    video_id: str
    filename: str

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

# ========================
# yt-dlp 다운로드 실행
# ========================
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

def parse_progress(line):
    match = re.search(r'(\d{1,3})%', line)
    if match:
        try:
            return int(match.group(1))
        except:
            return None
    return None


# ========================
# 비디오 단일 파일 직접 제공
# ========================
@app.get("/video/{filename}")
async def serve_video(filename: str):
    path = os.path.join(DOWNLOAD_DIR, filename)
    if os.path.exists(path):
        return FileResponse(path, media_type="video/mp4", filename=filename)
    return {"error": "file not found"}
