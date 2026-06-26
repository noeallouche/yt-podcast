import os
import re
import time
import requests
import io
from datetime import datetime, timezone
from flask import Flask, Response, abort, send_file
from xml.etree.ElementTree import Element, SubElement, tostring
import xml.etree.ElementTree as ET
from PIL import Image
import yt_dlp

app = Flask(__name__)

CHANNEL_ID = os.environ.get("CHANNEL_ID", "UCbbmy1wFvL1Xq0G9I-mLtQg")
CHANNEL_NAME = os.environ.get("CHANNEL_NAME", "PaduTeam")
BASE_URL = os.environ.get("BASE_URL", "https://your-app.up.railway.app").rstrip("/")
MAX_EPISODES = int(os.environ.get("MAX_EPISODES", "20"))

_cache = {}
CACHE_TTL = 3600


def get_channel_videos():
    """Récupère les vidéos via le flux RSS natif YouTube (pas de PO token nécessaire)"""
    cache_key = f"videos_{CHANNEL_ID}"
    now = time.time()
    if cache_key in _cache and now - _cache[cache_key]["ts"] < CACHE_TTL:
        return _cache[cache_key]["data"]

    rss_url = f"https://www.youtube.com/feeds/videos.xml?channel_id={CHANNEL_ID}"
    resp = requests.get(rss_url, timeout=15)
    resp.raise_for_status()

    ns = {
        "atom": "http://www.w3.org/2005/Atom",
        "yt": "http://www.youtube.com/xml/schemas/2015",
        "media": "http://search.yahoo.com/mrss/",
    }

    root = ET.fromstring(resp.content)
    videos = []

    # Récupère l'image de la chaîne depuis le premier thumbnail disponible
    channel_image = ""
    first_thumb = root.find(".//media:thumbnail", ns)
    if first_thumb is not None:
        channel_image = first_thumb.get("url", "")

    for entry in root.findall("atom:entry", ns)[:MAX_EPISODES]:
        video_id = entry.findtext("yt:videoId", namespaces=ns)
        title = entry.findtext("atom:title", namespaces=ns)
        published = entry.findtext("atom:published", namespaces=ns)
        description_el = entry.find(".//media:description", ns)
        description = description_el.text if description_el is not None else ""
        thumbnail_el = entry.find(".//media:thumbnail", ns)
        thumbnail = thumbnail_el.get("url") if thumbnail_el is not None else ""

        if video_id and title:
            videos.append({
                "id": video_id,
                "title": title,
                "published": published,
                "description": description or "",
                "thumbnail": thumbnail or "",
            })

    _cache[cache_key] = {"data": videos, "ts": now, "channel_image": channel_image}
    return videos


def get_audio_url(video_id):
    """Récupère l'URL audio directe via yt-dlp"""
    cache_key = f"audio_{video_id}"
    now = time.time()
    if cache_key in _cache and now - _cache[cache_key]["ts"] < 3600:
        return _cache[cache_key]["data"]

    ydl_opts = {
        "quiet": True,
        "format": "bestaudio[ext=m4a]/bestaudio/best",
        "skip_download": True,
        "nocheckcertificate": True,
        "extractor_args": {
            "youtube": {"player_client": ["ios"]},
        },
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
        result = {
            "url": info["url"],
            "duration": info.get("duration", 0),
        }

    _cache[cache_key] = {"data": result, "ts": now}
    return result


def parse_iso_date(iso_str):
    """Convertit ISO 8601 en RFC 2822"""
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
    except Exception:
        return datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")


def format_duration(seconds):
    if not seconds:
        return "00:00:00"
    h, r = divmod(int(seconds), 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


@app.route("/")
def index():
    return f"""
    <h1>🎙️ {CHANNEL_NAME} Podcast RSS</h1>
    <p>Flux RSS podcast :</p>
    <code>{BASE_URL}/feed.xml</code>
    <br><br>
    <p>Copiez cette URL dans <strong>Apple Podcasts → Ajouter un podcast par URL</strong></p>
    <br>
    <p><a href="/feed.xml">Voir le flux XML</a> | <a href="/debug">Debug</a></p>
    """


@app.route("/debug")
def debug():
    try:
        videos = get_channel_videos()
        return {
            "status": "ok",
            "channel_id": CHANNEL_ID,
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
        channel_image = _cache.get(f"videos_{CHANNEL_ID}", {}).get("channel_image", "")
    except Exception as e:
        return Response(f"Erreur: {e}", status=500)

    rss = Element("rss")
    rss.set("version", "2.0")
    rss.set("xmlns:itunes", "http://www.itunes.com/dtds/podcast-1.0.dtd")

    channel = SubElement(rss, "channel")
    SubElement(channel, "title").text = CHANNEL_NAME
    SubElement(channel, "link").text = f"https://www.youtube.com/channel/{CHANNEL_ID}"
    SubElement(channel, "description").text = f"Flux audio de {CHANNEL_NAME}"
    SubElement(channel, "language").text = "fr"
    SubElement(channel, "itunes:author").text = CHANNEL_NAME
    SubElement(channel, "itunes:type").text = "episodic"
    SubElement(channel, "itunes:explicit").text = "no"
    itunes_img = SubElement(channel, "itunes:image")
    itunes_img.set("href", f"{BASE_URL}/artwork.jpg")

    for video in videos:
        video_id = video["id"]
        title = video["title"]

        item = SubElement(channel, "item")
        SubElement(item, "title").text = title
        SubElement(item, "link").text = f"https://www.youtube.com/watch?v={video_id}"
        guid = SubElement(item, "guid")
        guid.set("isPermaLink", "false")
        guid.text = video_id

        enclosure = SubElement(item, "enclosure")
        enclosure.set("url", f"{BASE_URL}/audio/{video_id}.m4a")
        enclosure.set("type", "audio/x-m4a")
        enclosure.set("length", "1")

        SubElement(item, "itunes:title").text = title
        SubElement(item, "itunes:episodeType").text = "full"
        SubElement(item, "pubDate").text = parse_iso_date(video.get("published", ""))
        SubElement(item, "description").text = video.get("description", "")[:500]

        if video.get("thumbnail"):
            img = SubElement(item, "itunes:image")
            img.set("href", video["thumbnail"])

    xml_str = '<?xml version="1.0" encoding="UTF-8"?>\n' + tostring(rss, encoding="unicode")
    # Injection manuelle de la catégorie — ElementTree encode mal les & dans les attributs
    category_xml = '<itunes:category text="Society &amp; Culture"><itunes:category text="Documentary"/></itunes:category>'
    xml_str = xml_str.replace('<itunes:type>episodic</itunes:type>', f'<itunes:type>episodic</itunes:type>{category_xml}')
    return Response(xml_str, mimetype="application/rss+xml")


@app.route("/artwork.jpg")
def artwork():
    """Sert l'image de la chaîne en 1400x1400 (requis par Apple)"""
    try:
        # Récupère la miniature de la première vidéo en haute résolution
        videos = get_channel_videos()
        first_id = videos[0]["id"] if videos else None
        img_url = None
        if first_id:
            for size in ["maxresdefault", "hqdefault", "mqdefault"]:
                test_url = f"https://i.ytimg.com/vi/{first_id}/{size}.jpg"
                r = requests.get(test_url, timeout=10)
                if r.status_code == 200:
                    img_url = test_url
                    img_data = r.content
                    break

        if not img_url:
            abort(404)

        # Redimensionne en 1400x1400 carré
        img = Image.open(io.BytesIO(img_data)).convert("RGB")
        # Crop centré pour rendre carré
        w, h = img.size
        side = min(w, h)
        left = (w - side) // 2
        top = (h - side) // 2
        img = img.crop((left, top, left + side, top + side))
        img = img.resize((1400, 1400), Image.LANCZOS)

        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        buf.seek(0)
        return send_file(buf, mimetype="image/jpeg")
    except Exception as e:
        return Response(f"Erreur artwork: {e}", status=500)


@app.route("/audio/<video_id>.m4a")
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
