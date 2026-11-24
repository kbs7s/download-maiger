"""Download maniger - PC helper ("bridge").

Runs on the home PC next to aria2. It:
  * starts aria2 (normal files: zip, exe, photos, audio...)
  * runs yt-dlp for video sites (YouTube, Instagram, TikTok...)
  * keeps one shared download history for the whole family (history.json)
  * lets phones save finished files from the PC (/files/...)
  * forwards /jsonrpc to aria2, so AriaNg can be used too

The web page talks only to this helper, on http://127.0.0.1:6801.
Phones reach it through Tailscale:  tailscale serve --bg 6801

Only the Python standard library is used.
"""

import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.join(ROOT, "bin")
CONF = os.path.join(ROOT, "aria2.conf")
HISTORY_FILE = os.path.join(ROOT, "history.json")
BRIDGE_PORT = int(os.environ.get("DM_PORT", "6801"))
ARIA2_PORT = 6800
VERSION = "1.0"

# Sites that need yt-dlp instead of a plain download
VIDEO_SITES = (
    "youtube.com", "youtu.be", "instagram.com", "tiktok.com", "facebook.com",
    "fb.watch", "twitter.com", "x.com", "vimeo.com", "dailymotion.com",
    "reddit.com", "twitch.tv", "soundcloud.com", "pinterest.com", "snapchat.com",
    "threads.net", "bilibili.com", "aparat.com", "telegram.org", "t.me",
)


def tool(name):
    """Find a tool in engine/bin (Windows) or on PATH (for testing)."""
    for candidate in (os.path.join(BIN, name + ".exe"), os.path.join(BIN, name)):
        if os.path.isfile(candidate):
            return candidate
    return shutil.which(name)


def read_conf():
    conf = {}
    with open(CONF, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                conf[k.strip()] = v.strip()
    return conf


CONFIG = read_conf()
SECRET = CONFIG.get("rpc-secret", "")
DOWNLOAD_DIR = os.path.abspath(CONFIG.get("dir", os.path.join(ROOT, "downloads")))
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# ---------------------------------------------------------------- history

history_lock = threading.Lock()


def load_history():
    try:
        with open(HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return []


HISTORY = load_history()


def save_history():
    tmp = HISTORY_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(HISTORY, f, ensure_ascii=False, indent=1)
    os.replace(tmp, HISTORY_FILE)


def add_history(entry):
    with history_lock:
        if any(h["id"] == entry["id"] for h in HISTORY):
            return
        HISTORY.insert(0, entry)
        save_history()


def rel_path(path):
    if not path:
        return ""
    try:
        rel = os.path.relpath(os.path.abspath(path), DOWNLOAD_DIR)
    except ValueError:  # different drive on Windows
        return ""
    if rel.startswith(".."):
        return ""
    return rel.replace("\\", "/")


def file_size(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


# ---------------------------------------------------------------- aria2

def aria2(method, *params):
    body = json.dumps({
        "jsonrpc": "2.0", "id": "bridge", "method": "aria2." + method,
        "params": ["token:" + SECRET] + list(params),
    }).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:%d/jsonrpc" % ARIA2_PORT, data=body,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        data = json.load(r)
    if "error" in data:
        raise RuntimeError(data["error"].get("message", "aria2 error"))
    return data["result"]


ARIA2_KEYS = ["gid", "status", "totalLength", "completedLength", "downloadSpeed",
              "files", "errorMessage", "dir", "bittorrent"]
gid_users = {}       # gid -> who added it
gid_urls = {}        # gid -> original link


def aria2_name(item):
    files = item.get("files") or []
    bt = item.get("bittorrent") or {}
    if bt.get("info", {}).get("name"):
        return bt["info"]["name"]
    if files:
        if files[0].get("path"):
            return os.path.basename(files[0]["path"])
        uris = files[0].get("uris") or []
        if uris:
            return urllib.parse.unquote(
                os.path.basename(urllib.parse.urlparse(uris[0]["uri"]).path)) or uris[0]["uri"]
    return item.get("gid", "")


def aria2_url(item):
    gid = item.get("gid")
    if gid in gid_urls:
        return gid_urls[gid]
    for f in item.get("files") or []:
        for u in f.get("uris") or []:
            return u.get("uri", "")
    return ""


def aria2_watcher():
    """Copy finished aria2 downloads into the shared history."""
    while True:
        try:
            for item in aria2("tellStopped", 0, 1000, ARIA2_KEYS):
                if item["status"] not in ("complete", "error"):
                    continue
                files = item.get("files") or []
                path = files[0].get("path", "") if files else ""
                if item.get("bittorrent") and item.get("dir"):
                    path = os.path.join(item["dir"], aria2_name(item))
                add_history({
                    "id": "a-" + item["gid"],
                    "kind": "file",
                    "name": aria2_name(item),
                    "url": aria2_url(item),
                    "user": gid_users.get(item["gid"], ""),
                    "status": "done" if item["status"] == "complete" else "error",
                    "error": item.get("errorMessage", ""),
                    "size": int(item.get("totalLength") or 0),
                    "path": rel_path(path) if item["status"] == "complete" else "",
                    "time": int(time.time()),
                })
        except Exception:
            pass  # aria2 not up yet
        time.sleep(3)


# ---------------------------------------------------------------- yt-dlp

jobs = {}
jobs_lock = threading.Lock()
PROGRESS_RE = re.compile(r"^DMPROG\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)")


def run_video(job):
    ytdlp = tool("yt-dlp")
    if not ytdlp:
        job.update(status="error", error="yt-dlp is not installed. Run setup.bat.")
        return finish_video(job)
    # each job works in its own temp folder so two jobs never overwrite each other
    tmp_dir = os.path.join(DOWNLOAD_DIR, ".partial", job["id"])
    args = [ytdlp, "--encoding", "utf-8", "--newline", "--no-playlist", "--no-simulate", "--progress",
            "--no-colors", "--restrict-filenames" if os.name != "nt" else "--windows-filenames",
            "-P", DOWNLOAD_DIR, "-P", "temp:" + tmp_dir, "-o", "%(title).150B [%(id)s].%(ext)s",
            "--progress-template",
            "download:DMPROG %(progress.downloaded_bytes)s %(progress.total_bytes)s "
            "%(progress.total_bytes_estimate)s %(progress.speed)s",
            "--print", "before_dl:DMTITLE %(title)s",
            "--print", "after_move:DMFILE %(filepath)s"]
    ffmpeg = tool("ffmpeg")
    if ffmpeg:
        args += ["--ffmpeg-location", os.path.dirname(ffmpeg)]
    if job["mode"] == "audio":
        args += ["-x", "--audio-format", "mp3", "--audio-quality", "0"]
    else:
        args += ["-f", "bv*[height<=1080]+ba/b", "--merge-output-format", "mp4"]
    args.append(job["url"])

    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, encoding="utf-8", errors="replace",
                                creationflags=flags)
    except OSError as e:
        job.update(status="error", error=str(e))
        return finish_video(job)
    job["proc"] = proc
    last_lines = []
    for line in proc.stdout:
        line = line.strip()
        if not line:
            continue
        m = PROGRESS_RE.match(line)
        if m:
            done, total, est, speed = (_num(x) for x in m.groups())
            job["done"] = done
            job["total"] = total or est
            job["speed"] = speed
            continue
        if line.startswith("DMTITLE "):
            job["name"] = line[8:]
        elif line.startswith("DMFILE "):
            job["file"] = line[7:]
        else:
            last_lines = (last_lines + [line])[-5:]
    proc.wait()
    shutil.rmtree(tmp_dir, ignore_errors=True)
    if job.get("cancelled"):
        job["status"] = "removed"
    elif proc.returncode == 0 and job.get("file"):
        job["status"] = "done"
    else:
        job["status"] = "error"
        errs = [l for l in last_lines if "ERROR" in l]
        job["error"] = (errs or last_lines or ["yt-dlp failed"])[-1][:300]
    finish_video(job)


def _num(s):
    try:
        return float(s)
    except ValueError:
        return 0


def finish_video(job):
    if job["status"] in ("done", "error"):
        path = job.get("file", "")
        add_history({
            "id": "v-" + job["id"], "kind": job["mode"], "name": job.get("name") or job["url"],
            "url": job["url"], "user": job["user"], "status": job["status"],
            "error": job.get("error", ""), "size": file_size(path),
            "path": rel_path(path), "time": int(time.time()),
        })
    with jobs_lock:
        jobs.pop(job["id"], None)


def start_video(url, mode, user):
    job = {"id": uuid.uuid4().hex[:12], "url": url, "mode": mode, "user": user,
           "status": "active", "name": "", "done": 0, "total": 0, "speed": 0}
    with jobs_lock:
        jobs[job["id"]] = job
    threading.Thread(target=run_video, args=(job,), daemon=True).start()
    return job["id"]


def is_video_site(url):
    host = (urllib.parse.urlparse(url).hostname or "").lower()
    return any(host == s or host.endswith("." + s) for s in VIDEO_SITES)


# ---------------------------------------------------------------- API

def api_add(data):
    user = str(data.get("user", ""))[:40]
    mode = data.get("mode", "auto")
    added = []
    for url in data.get("urls", []):
        url = str(url).strip()
        if not url:
            continue
        if not re.match(r"^(https?|ftp|sftp|magnet):", url, re.I):
            added.append({"url": url, "error": "Not a link"})
            continue
        m = mode
        if m == "auto":
            m = "video" if is_video_site(url) else "file"
        if m in ("video", "audio"):
            added.append({"url": url, "id": "v-" + start_video(url, m, user)})
        else:
            gid = aria2("addUri", [url], {})
            gid_users[gid] = user
            gid_urls[gid] = url
            added.append({"url": url, "id": "a-" + gid})
    return {"added": added}


def api_active():
    items = []
    try:
        lists = aria2("tellActive", ARIA2_KEYS) + aria2("tellWaiting", 0, 100, ARIA2_KEYS)
    except Exception as e:
        lists = []
        items.append({"id": "engine", "kind": "error", "name": "Download engine (aria2) is not answering: %s" % e,
                      "status": "error"})
    for it in lists:
        items.append({
            "id": "a-" + it["gid"], "kind": "file", "name": aria2_name(it),
            "status": it["status"], "done": int(it.get("completedLength") or 0),
            "total": int(it.get("totalLength") or 0),
            "speed": int(it.get("downloadSpeed") or 0),
            "user": gid_users.get(it["gid"], ""), "url": aria2_url(it),
        })
    with jobs_lock:
        for j in jobs.values():
            items.append({
                "id": "v-" + j["id"], "kind": j["mode"], "name": j.get("name") or j["url"],
                "status": j["status"], "done": int(j["done"]), "total": int(j["total"]),
                "speed": int(j["speed"]), "user": j["user"], "url": j["url"],
            })
    return {"items": items}


def api_action(data):
    item_id, action = str(data.get("id", "")), data.get("action")
    if item_id.startswith("a-"):
        gid = item_id[2:]
        method = {"pause": "pause", "resume": "unpause", "remove": "remove"}.get(action)
        if not method:
            raise ValueError("Unknown action")
        aria2(method, gid)
        if action == "remove":
            try:
                aria2("removeDownloadResult", gid)
            except Exception:
                pass
    elif item_id.startswith("v-"):
        if action != "remove":
            raise ValueError("Videos can only be cancelled")
        with jobs_lock:
            job = jobs.get(item_id[2:])
        if job and job.get("proc"):
            job["cancelled"] = True
            job["proc"].terminate()
    elif item_id.startswith("h-"):  # forget a history entry (the file stays on the PC)
        with history_lock:
            HISTORY[:] = [h for h in HISTORY if h["id"] != item_id[2:]]
            save_history()
    else:
        raise ValueError("Unknown item")
    return {"ok": True}


def api_info():
    return {"app": "Download maniger", "version": VERSION, "dir": DOWNLOAD_DIR,
            "ytdlp": bool(tool("yt-dlp")), "ffmpeg": bool(tool("ffmpeg"))}


class Handler(BaseHTTPRequestHandler):
    server_version = "DownloadManiger/" + VERSION
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if "/api/active" not in (args[0] if args else ""):
            sys.stdout.write("%s %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    def cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Secret, Range")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Access-Control-Expose-Headers", "Content-Length, Content-Range")

    def send_json(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.cors()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def authorized(self, query):
        given = self.headers.get("X-Secret") or (query.get("token") or [""])[0]
        return bool(SECRET) and given == SECRET

    def read_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(n) if n else b""

    def do_OPTIONS(self):
        self.send_response(204)
        self.cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(url.query)
        if url.path in ("/", "/api/ping"):
            return self.send_json(200, {"app": "Download maniger", "ok": True})
        if not self.authorized(query):
            return self.send_json(401, {"error": "Wrong secret token"})
        try:
            if url.path == "/api/info":
                return self.send_json(200, api_info())
            if url.path == "/api/active":
                return self.send_json(200, api_active())
            if url.path == "/api/history":
                with history_lock:
                    return self.send_json(200, {"items": HISTORY[:2000]})
            if url.path.startswith("/files/"):
                return self.send_file(urllib.parse.unquote(url.path[7:]))
        except Exception as e:
            return self.send_json(500, {"error": str(e)})
        self.send_json(404, {"error": "Not found"})

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        body = self.read_body()
        if url.path == "/jsonrpc":  # pass-through for AriaNg (aria2 checks its own token)
            return self.proxy_aria2(body)
        if not self.authorized(urllib.parse.parse_qs(url.query)):
            return self.send_json(401, {"error": "Wrong secret token"})
        try:
            data = json.loads(body or b"{}")
            if url.path == "/api/add":
                return self.send_json(200, api_add(data))
            if url.path == "/api/action":
                return self.send_json(200, api_action(data))
        except Exception as e:
            return self.send_json(400, {"error": str(e)})
        self.send_json(404, {"error": "Not found"})

    def proxy_aria2(self, body):
        req = urllib.request.Request("http://127.0.0.1:%d/jsonrpc" % ARIA2_PORT, data=body,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                code, out = r.status, r.read()
        except urllib.error.HTTPError as e:
            code, out = e.code, e.read()
        except Exception as e:
            return self.send_json(502, {"error": str(e)})
        self.send_response(code)
        self.cors()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(out)))
        self.end_headers()
        self.wfile.write(out)

    def send_file(self, rel):
        full = os.path.abspath(os.path.join(DOWNLOAD_DIR, rel))
        if not full.startswith(DOWNLOAD_DIR + os.sep) or not os.path.isfile(full):
            return self.send_json(404, {"error": "File not found on the PC"})
        size = os.path.getsize(full)
        start, end = 0, size - 1
        rng = self.headers.get("Range", "")
        m = re.match(r"bytes=(\d*)-(\d*)$", rng)
        partial = bool(m) and size > 0
        if partial:
            if m.group(1):
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else size - 1
            else:
                start = max(0, size - int(m.group(2) or 0))
            end = min(end, size - 1)
            if start > end:
                self.send_response(416)
                self.cors()
                self.send_header("Content-Range", "bytes */%d" % size)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
        name = os.path.basename(full)
        ctype = mimetypes.guess_type(name)[0] or "application/octet-stream"
        self.send_response(206 if partial else 200)
        self.cors()
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if partial:
            self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
        self.send_header("Content-Disposition",
                         "attachment; filename*=UTF-8''" + urllib.parse.quote(name))
        self.end_headers()
        with open(full, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(1024 * 1024, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (ConnectionError, OSError):
                    return
                left -= len(chunk)


def start_aria2():
    exe = tool("aria2c")
    if not exe:
        print("aria2c was not found. Run setup.bat first.")
        sys.exit(1)
    flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    return subprocess.Popen([exe, "--conf-path=" + CONF], cwd=ROOT, creationflags=flags,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main():
    if not SECRET:
        print("No rpc-secret in aria2.conf. Run setup.bat first.")
        sys.exit(1)
    aria = None if os.environ.get("DM_NO_ARIA2") else start_aria2()
    threading.Thread(target=aria2_watcher, daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", BRIDGE_PORT), Handler)
    server.daemon_threads = True
    print("Download maniger is running.")
    print("  On this PC, use server address: http://localhost:%d" % BRIDGE_PORT)
    print("  Files are saved to: %s" % DOWNLOAD_DIR)
    print("Keep this window open. Close it to stop downloading.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if aria:
            aria.terminate()


if __name__ == "__main__":
    main()
