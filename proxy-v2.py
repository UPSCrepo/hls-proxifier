from flask import Flask, request, url_for, Response
from urllib.parse import urljoin, urlparse
import requests
import m3u8
import json

proxy = Flask(__name__)

MAX_RETRIES = 5

def get_base_url(url):
    return urljoin(url, ".")

def is_absolute_url(url):
    parsed_url = urlparse(url)
    return bool(parsed_url.scheme) and bool(parsed_url.netloc)

def configure_single(m3u8_obj, base_url, json_stream_headers):
    for playlist in m3u8_obj.playlists:
        uri = playlist.uri
        stream_base = base_url if not is_absolute_url(uri) else None
        is_absolute = is_absolute_url(uri)
        playlist.uri = url_for(
            "handle_single", 
            slug=uri, 
            base=stream_base, 
            absolute=is_absolute, 
            headers=json.dumps(json_stream_headers)
        )
    return m3u8_obj

def configure_segments(m3u8_obj, base_url, json_stream_headers):
    for segment in m3u8_obj.segments:
        uri = segment.uri
        ts_base = base_url if not is_absolute_url(uri) else None
        is_absolute = is_absolute_url(uri)
        segment.uri = url_for(
            "handle_ts", 
            slug=uri, 
            base=ts_base, 
            absolute=is_absolute, 
            headers=json.dumps(json_stream_headers)
        )
    return m3u8_obj

def configure_keys(m3u8_obj, base_url, json_stream_headers):
    for key in m3u8_obj.keys:
        if key and key.uri:
            key_base = base_url if not is_absolute_url(key.uri) else ""
            is_absolute = is_absolute_url(key.uri)
            key.uri = url_for(
                "handle_key", 
                slug=key.uri,
                base=key_base, 
                absolute=is_absolute, 
                headers=json.dumps(json_stream_headers)
            )
    return m3u8_obj

def configure_audio_tracks(m3u8_obj, base_url, json_stream_headers):
    for media in m3u8_obj.media:
        if media.uri:
            uri = media.uri
            audio_base = base_url if not is_absolute_url(uri) else None
            is_absolute = is_absolute_url(uri)
            media.uri = url_for(
                "handle_single",
                slug=uri,
                base=audio_base,
                absolute=is_absolute,
                headers=json.dumps(json_stream_headers)
            )
    return m3u8_obj

@proxy.route("/")
def index():
    return "(HLS-Proxifier with Audio) is up and running!"

@proxy.route("/proxify")
def hls_proxy():
    stream_url = request.args.get("url")
    stream_headers = request.args.get("headers")

    if stream_headers:
        stream_headers = json.loads(stream_headers)
    else:
        stream_headers = {}

    for _ in range(MAX_RETRIES):
        try:
            response = requests.get(stream_url, headers=stream_headers)
            response.raise_for_status()
            break
        except:
            continue

    m3u8_obj = m3u8.loads(response.text)

    base_url = get_base_url(response.url)

    if m3u8_obj.is_variant:
        if len(m3u8_obj.playlists) >= 2:
            m3u8_obj = configure_single(m3u8_obj, base_url, stream_headers)
        else:
            uri = m3u8_obj.playlists[0].uri
            segment_response = requests.get(urljoin(base_url, uri), headers=stream_headers)
            m3u8_obj = m3u8.loads(segment_response.text)
            m3u8_obj = configure_segments(m3u8_obj, get_base_url(segment_response.url), stream_headers)
    else:
        m3u8_obj = configure_segments(m3u8_obj, base_url, stream_headers)

    m3u8_obj = configure_keys(m3u8_obj, base_url, stream_headers)
    m3u8_obj = configure_audio_tracks(m3u8_obj, base_url, stream_headers)

    return Response(m3u8_obj.dumps(), content_type="application/vnd.apple.mpegurl")

@proxy.route("/single")
def handle_single():
    single_slug = request.args.get("slug")
    single_base = request.args.get("base")
    json_single_headers = json.loads(request.args.get("headers"))
    is_absolute = request.args.get("absolute").lower() == "true"

    single_url = single_slug if is_absolute else urljoin(single_base, single_slug)

    for _ in range(MAX_RETRIES):
        try:
            response = requests.get(single_url, headers=json_single_headers)
            response.raise_for_status()
            break
        except:
            continue

    m3u8_obj = m3u8.loads(response.text, uri=get_base_url(single_url))
    base_url = get_base_url(response.url)

    m3u8_obj = configure_segments(m3u8_obj, base_url, json_single_headers)
    m3u8_obj = configure_keys(m3u8_obj, base_url, json_single_headers)
    m3u8_obj = configure_audio_tracks(m3u8_obj, base_url, json_single_headers)

    return Response(m3u8_obj.dumps(), content_type="application/vnd.apple.mpegurl")

@proxy.route("/ts")
def handle_ts():
    ts_slug = request.args.get("slug")
    json_ts_headers = json.loads(request.args.get("headers"))
    ts_base = request.args.get("base")
    is_absolute = request.args.get("absolute").lower() == "true"

    ts_url = ts_slug if is_absolute else urljoin(ts_base, ts_slug)

    for _ in range(MAX_RETRIES):
        response = requests.get(ts_url, headers=json_ts_headers)
        if response.status_code == 502:
            continue
        break

    return Response(response.content, content_type="application/octet-stream")

@proxy.route("/key")
def handle_key():
    key_slug = request.args.get("slug")
    json_key_headers = json.loads(request.args.get("headers"))
    key_base = request.args.get("base")
    is_absolute = request.args.get("absolute").lower() == 'true'

    key_url = key_slug if is_absolute else urljoin(key_base, key_slug)

    for _ in range(MAX_RETRIES):
        try:
            response = requests.get(key_url, headers=json_key_headers)
            response.raise_for_status()
            break
        except:
            continue

    return Response(response.content, content_type="application/octet-stream")

if __name__ == "__main__":
    proxy.run(debug=True)
