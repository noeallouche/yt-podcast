import os
import re
import json
import time
import hashlib
import requests
from datetime import datetime, timezone
from flask import Flask, Response, request, abort
from xml.etree.ElementTree import Element, SubElement, tostring
import yt_dlp

app = Flask(__name__)

CHANNEL_ID = os.environ.get("CHANNEL_ID", "UCbbmy1wFvL1Xq0G9I-mLtQg")
CHANNEL_NAME = os.environ.get("CHANNEL_NAME", "PaduTeam")
BASE_URL = os.environ.get("BASE_URL", "https://your-app.onrender.com")
MAX_EPISODES = int(os.environ.get("MAX_EPISODES", "20"))

# Simple in-memory cache
_cache = {}
CACHE_TTL = 3600  # 1 heure


def get_channel_videos():
    """Récupère les dernières vidéos de la chaîne via yt-dlp"""
    cache_key = f"videos_{CHANNEL_ID}"
    now = time.time()

    if cache_key in _cache and now - _cache[cache_key]["ts"] < CACHE_TTL:
        return _cache[cache_key]["data"]

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "playlist_items": f"1:{MAX_EPISODES}",
    }

    url = f"https://www.youtube.com/channel/{CHANNEL_ID}/videos"

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        videos = info.get("entries", [])

    _cache[cache_key] = {"data": videos, "ts": now}
    return videos


def get_audio_url(video_id):
    """Récupère l'URL de l'audio direct d'une vidéo"""
    cache_key = f"audio_{video_id}"
    now = time.time()

    if cache_key in _cache and now - _cache[cache_key]["ts"] < 3600:
        return _cache[cache_key]["data"]

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "skip_download": True,
    }

    url = f"https://www.youtube.com/watch?v={video_id}"

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        audio_url = info["url"]
        duration = info.get("duration", 0)
        filesize = info.get("filesize") or info.get("filesize_approx", 0)
        upload_date = info.get("upload_date", "")
        description = info.get("description", "")
        thumbnail = info.get("thumbnail", "")

    result = {
        "url": audio_url,
        "duration": duration,
        "filesize": filesize,
        "upload_date": upload_date,
        "description": description,
        "thumbnail": thumbnail,
    }

    _cache[cache_key] = {"data": result, "ts": now}
    return result


def format_duration(seconds):
    """Convertit les secondes en HH:MM:SS"""
    if not seconds:
        return "00:00:00"
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def parse_upload_date(date_str):
    """Convertit YYYYMMDD en RFC 2822"""
    if not date_str or len(date_str) != 8:
        return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")
    try:
        dt = datetime.strptime(date_str, "%Y%m%d").replace(tzinfo=timezone.utc)
        return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
    except Exception:
        return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")


@app.route("/")
def index():
    return f"""
    <h1>🎙️ {CHANNEL_NAME} Podcast RSS</h1>
    <p>Flux RSS podcast pour Apple Podcasts :</p>
    <code>{BASE_URL}/feed.xml</code>
    <br><br>
    <p>Copiez cette URL dans <strong>Apple Podcasts → Ajouter un podcast par URL</strong></p>
    """


@app.route("/feed.xml")
def rss_feed():
    try:
        videos = get_channel_videos()
    except Exception as e:
        return Response(f"Erreur lors de la récupération des vidéos : {e}", status=500)

    # Racine RSS
    rss = Element("rss")
    rss.set("version", "2.0")
    rss.set("xmlns:itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")
    rss.set("xmlns:content", "http://purl.org/rss/1.0/modules/content/")

    channel = SubElement(rss, "channel")

    SubElement(channel, "title").text = CHANNEL_NAME
    SubElement(channel, "link").text = f"https://www.youtube.com/channel/{CHANNEL_ID}"
    SubElement(channel, "description").text = f"Flux audio de la chaîne YouTube {CHANNEL_NAME}"
    SubElement(channel, "language").text = "fr"
    SubElement(channel, "lastBuildDate").text = datetime.now(timezone.utc).strftime(
        "%a, %d %b %Y %H:%M:%S +0000"
    )

    itunes_author = SubElement(channel, "itunes:author")
    itunes_author.text = CHANNEL_NAME

    itunes_type = SubElement(channel, "itunes:type")
    itunes_type.text = "episodic"

    itunes_category = SubElement(channel, "itunes:category")
    itunes_category.set("text", "Society &amp; Culture")

    for video in videos[:MAX_EPISODES]:
        video_id = video.get("id") or video.get("url", "").split("v=")[-1]
        title = video.get("title", "Sans titre")

        if not video_id:
            continue

        item = SubElement(channel, "item")
        SubElement(item, "title").text = title
        SubElement(item, "link").text = f"https://www.youtube.com/watch?v={video_id}"

        guid = SubElement(item, "guid")
        guid.set("isPermaLink", "false")
        guid.text = video_id

        # URL audio via notre proxy
        audio_proxy_url = f"{BASE_URL}/audio/{video_id}"

        enclosure = SubElement(item, "enclosure")
        enclosure.set("url", audio_proxy_url)
        enclosure.set("type", "audio/mpeg")
        enclosure.set("length", "0")

        # Infos itunes
        SubElement(item, "itunes:title").text = title
        SubElement(item, "itunes:episodeType").text = "full"

        upload_date = video.get("upload_date", "")
        SubElement(item, "pubDate").text = parse_upload_date(upload_date)

        description = video.get("description", f"Vidéo YouTube : {title}")
        SubElement(item, "description").text = description[:500] if description else ""

        thumbnail = video.get("thumbnail", "")
        if thumbnail:
            itunes_image = SubElement(item, "itunes:image")
            itunes_image.set("href", thumbnail)

        duration = video.get("duration")
        if duration:
            SubElement(item, "itunes:duration").text = format_duration(duration)

    xml_str = tostring(rss, encoding="unicode", xml_declaration=False)
    xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + xml_str

    return Response(xml_str, mimetype="application/rss+xml")


@app.route("/audio/<video_id>")
def audio_proxy(video_id):
    """Redirige vers l'URL audio directe de YouTube"""
    if not re.match(r'^[a-zA-Z0-9_-]{11}$', video_id):
        abort(400)

    try:
        info = get_audio_url(video_id)
        audio_url = info["url"]
        # Redirection vers l'URL audio YouTube (temporaire, expire après quelques heures)
        return Response(
            status=302,
            headers={"Location": audio_url}
        )
    except Exception as e:
        return Response(f"Erreur : {e}", status=500)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
