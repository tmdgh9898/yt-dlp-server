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

# 다운로드 파일 저장 경로
DOWNLOAD_DIR = "./downloads"
STATIC_DIR = "./static"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ✅ 1️⃣ Static 파일 (웹 페이지) 서비스
# / 요청 시 -> static/index.html 자동 서빙
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")

# ✅ 2️⃣ 다운로드된 mp4 파일 서비스
app.mount("/downloads", StaticFiles(directory=DOWNLOAD_DIR), name="downloads")

# ✅ 3️⃣ 다운로드 작업 상태 저장
jobs = {}

# ✅ 4️⃣ 클라이언트가 보내는 요청 Body 모델
class DownloadRequest(BaseModel):
    referer: str
    video_id: str
    filename: str

# ✅ 5️⃣ 다운로드 생성 요청
@app.post("/download")
async def start_download(req: DownloadRequest):
    job_id = str(uuid.uuid4())
    jobs[job_id] = {
        "status": "downloading",
        "progress": 0,
        "filename": f"{req.filename}.mp4",
        "error": None
    }
    # yt-dlp를 백그라운드 스레드에서 실행
    threading.Thread(target=run_download, args=(job_id, req)).start()
    return {"job_id": job_id}

# ✅ 6️⃣ 다운로드 진행상황 조회
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

# ✅ 7️⃣ 실제 다운로드 실행 (백그라운드)
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

# ✅ 8️⃣ yt-dlp 로그에서 % 진행률 추출
def parse_progress(line):
    match = re.search(r'(\d{1,3})%', line)
    if match:
        try:
            return int(match.group(1))
        except:
            return None
    return None

# ✅ 9️⃣ 개별 파일 직접 제공 (선택적, 안전장치)
@app.get("/video/{filename}")
async def serve_video(filename: str):
    path = os.path.join(DOWNLOAD_DIR, filename)
    if os.path.exists(path):
        return FileResponse(path, media_type="video/mp4", filename=filename)
    return {"error": "file not found"}
