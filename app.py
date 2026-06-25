import os
import re
import time
from datetime import datetime, timezone
from flask import Flask, Response, abort
from xml.etree.ElementTree import Element, SubElement, tostring
import yt_dlp

app = Flask(__name__)

CHANNEL_HANDLE = os.environ.get("CHANNEL_HANDLE", "PaduTeam")
CHANNEL_NAME = os.environ.get("CHANNEL_NAME", "PaduTeam")
BASE_URL = os.environ.get("BASE_URL", "https://your-app.up.railway.app").rstrip("/")
MAX_EPISODES = int(os.environ.get("MAX_EPISODES", "20"))

_cache = {}
CACHE_TTL = 3600


def get_channel_videos():
    cache_key = f"videos_{CHANNEL_HANDLE}"
    now = time.time()
    if cache_key in _cache and now - _cache[cache_key]["ts"] < CACHE_TTL:
        return _cache[cache_key]["data"]

    ydl_opts = {
        "quiet": False,
        "no_warnings": False,
        "extract_flat": True,
        "playlistend": MAX_EPISODES,
    }

    # Essaie d'abord avec le handle, puis avec l'ID
    urls_to_try = [
        f"https://www.youtube.com/@{CHANNEL_HANDLE}/videos",
        f"https://www.youtube.com/c/{CHANNEL_HANDLE}/videos",
    ]

    videos = []
    for url in urls_to_try:
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                videos = info.get("entries", []) or []
                if videos:
                    break
        except Exception as e:
            print(f"Erreur avec {url}: {e}")
            continue

    _cache[cache_key] = {"data": videos, "ts": now}
    return videos


def get_audio_url(video_id):
    cache_key = f"audio_{video_id}"
    now = time.time()
    if cache_key in _cache and now - _cache[cache_key]["ts"] < 3600:
        return _cache[cache_key]["data"]

    ydl_opts = {
        "quiet": True,
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "skip_download": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
        result = {
            "url": info["url"],
            "duration": info.get("duration", 0),
            "upload_date": info.get("upload_date", ""),
            "description": info.get("description", ""),
            "thumbnail": info.get("thumbnail", ""),
        }

    _cache[cache_key] = {"data": result, "ts": now}
    return result


def format_duration(seconds):
    if not seconds:
        return "00:00:00"
    h, r = divmod(int(seconds), 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def parse_upload_date(date_str):
    try:
        dt = datetime.strptime(date_str, "%Y%m%d").replace(tzinfo=timezone.utc)
        return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
    except Exception:
        return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")


@app.route("/")
def index():
    return f"""
    <h1>🎙️ {CHANNEL_NAME} Podcast RSS</h1>
    <p>Flux RSS :</p>
    <code>{BASE_URL}/feed.xml</code>
    <br><br>
    <p>Copiez cette URL dans <strong>Apple Podcasts → Ajouter un podcast par URL</strong></p>
    <br>
    <p><a href="/feed.xml">Voir le flux XML</a></p>
    <p><a href="/debug">Debug</a></p>
    """


@app.route("/debug")
def debug():
    """Endpoint pour diagnostiquer les problèmes"""
    try:
        videos = get_channel_videos()
        return {
            "status": "ok",
            "channel": CHANNEL_HANDLE,
            "videos_found": len(videos),
            "first_video": videos[0].get("title") if videos else None,
            "base_url": BASE_URL,
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}, 500


@app.route("/feed.xml")
def rss_feed():
    try:
        videos = get_channel_videos()
    except Exception as e:
        return Response(f"Erreur: {e}", status=500)

    rss = Element("rss")
    rss.set("version", "2.0")
    rss.set("xmlns:itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")

    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = CHANNEL_NAME
    SubElement(channel, "link").text = f"https://www.youtube.com/@{CHANNEL_HANDLE}"
    SubElement(channel, "description").text = f"Flux audio de {CHANNEL_NAME}"
    SubElement(channel, "language").text = "fr"
    SubElement(channel, "itunes:author").text = CHANNEL_NAME
    SubElement(channel, "itunes:type").text = "episodic"

    for video in videos[:MAX_EPISODES]:
        if not video:
            continue
        video_id = video.get("id") or video.get("url", "").split("v=")[-1]
        title = video.get("title", "Sans titre")
        if not video_id or len(video_id) != 11:
            continue

        item = SubElement(channel, "item")
        SubElement(item, "title").text = title
        SubElement(item, "link").text = f"https://www.youtube.com/watch?v={video_id}"
        guid = SubElement(item, "guid")
        guid.set("isPermaLink", "false")
        guid.text = video_id

        audio_proxy_url = f"{BASE_URL}/audio/{video_id}"
        enclosure = SubElement(item, "enclosure")
        enclosure.set("url", audio_proxy_url)
        enclosure.set("type", "audio/mpeg")
        enclosure.set("length", "0")

        SubElement(item, "itunes:title").text = title
        SubElement(item, "itunes:episodeType").text = "full"
        SubElement(item, "pubDate").text = parse_upload_date(video.get("upload_date", ""))

        duration = video.get("duration")
        if duration:
            SubElement(item, "itunes:duration").text = format_duration(duration)

        thumbnail = video.get("thumbnail", "")
        if thumbnail:
            img = SubElement(item, "itunes:image")
            img.set("href", thumbnail)

    xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(rss, encoding="unicode")
    return Response(xml_str, mimetype="application/rss+xml")


@app.route("/audio/<video_id>")
def audio_proxy(video_id):
    if not re.match(r'^[a-zA-Z0-9_-]{11}$', video_id):
        abort(400)
    try:
        info = get_audio_url(video_id)
        return Response(status=302, headers={"Location": info["url"]})
    except Exception as e:
        return Response(f"Erreur: {e}", status=500)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
