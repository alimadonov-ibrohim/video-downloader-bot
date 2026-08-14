import glob
import os
import re
import shutil
import tempfile
import uuid

import yt_dlp

MAX_FILE_SIZE = 50 * 1024 * 1024
DOWNLOAD_DIR = os.path.join(tempfile.gettempdir(), "downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

YOUTUBE_CLIENTS = ("tv", "android", "ios", "web")

SUPPORTED_DOMAINS = (
    "youtube.com",
    "youtu.be",
    "youtube-nocookie.com",
    "instagram.com",
    "facebook.com",
    "fb.watch",
    "fb.com",
    "pinterest.com",
    "pin.it",
)
SUPPORTED_RE = re.compile("|".join(re.escape(d) for d in SUPPORTED_DOMAINS), re.IGNORECASE)
URL_REGEX = re.compile(r"https?://[^\s]+", re.IGNORECASE)


def get_ffmpeg_path():
    env = os.getenv("FFMPEG_PATH")
    if env and os.path.exists(env):
        return env
    local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bin", "ffmpeg.exe")
    if os.path.exists(local):
        return local
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def ydl_opts(player_client: str = None):
    opts = {
        "outtmpl": os.path.join(DOWNLOAD_DIR, f"{uuid.uuid4().hex[:8]}_%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "restrictfilenames": True,
        "socket_timeout": 30,
        "retries": 3,
        "nocheckcertificate": True,
    }
    if player_client:
        opts["extractor_args"] = {"youtube": {"player_client": [player_client]}}
    cookies = os.getenv("YT_COOKIES")
    if not cookies:
        local = os.path.join(os.path.dirname(os.path.abspath(__file__)), "youtube_cookies.txt")
        if os.path.exists(local):
            cookies = local
    if not cookies:
        b64 = os.getenv("YT_COOKIES_B64")
        if b64:
            try:
                import base64

                cookies = os.path.join(DOWNLOAD_DIR, "cookies.txt")
                if not os.path.exists(cookies):
                    with open(cookies, "wb") as f:
                        f.write(base64.b64decode(b64))
            except Exception:
                cookies = None
    if cookies and os.path.exists(cookies):
        try:
            writable = os.path.join(DOWNLOAD_DIR, "cookies.txt")
            shutil.copy2(cookies, writable)
            cookies = writable
        except OSError:
            pass
        opts["cookiefile"] = cookies
    ffmpeg = get_ffmpeg_path()
    if ffmpeg:
        opts["format"] = (
            "bestvideo[ext=mp4][filesize<45M]+bestaudio[ext=m4a]/"
            "best[ext=mp4][filesize<50M]/best[ext=mp4]/best"
        )
        opts["merge_output_format"] = "mp4"
        opts["ffmpeg_location"] = ffmpeg
    else:
        opts["format"] = "best[filesize<50M][ext=mp4]/best[filesize<50M]/best[ext=mp4]/best"
    return opts


def download_video(url: str) -> str:
    errors = []
    for client in [None, *YOUTUBE_CLIENTS]:
        try:
            return _download_with_fallback(url, client)
        except Exception as e:
            errors.append(f"[{client or 'default'}] {e}")
    raise RuntimeError(" | ".join(errors))


def _download_with_fallback(url: str, client: str) -> str:
    try:
        return _download(url, ydl_opts(client))
    except Exception as merge_err:
        simple = ydl_opts(client)
        simple["format"] = "best[filesize<50M]/best"
        simple.pop("merge_output_format", None)
        simple.pop("ffmpeg_location", None)
        try:
            return _download(url, simple)
        except Exception as simple_err:
            raise RuntimeError(
                f"merge: {merge_err} | simple: {simple_err}"
            ) from simple_err


def _download(url: str, opts: dict) -> str:
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        for dl in info.get("requested_downloads") or []:
            fp = dl.get("filepath")
            if fp and os.path.exists(fp):
                return fp
        path = ydl.prepare_filename(info)
        if os.path.exists(path):
            return path
        template = opts["outtmpl"].replace("%(id)s", info.get("id") or "*")
        template = template.replace("%(ext)s", "*")
        matches = glob.glob(template)
        if matches:
            return max(matches, key=os.path.getsize)
        raise FileNotFoundError(f"Yuklangan fayl topilmadi: {path}")


def cleanup(path: str):
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass