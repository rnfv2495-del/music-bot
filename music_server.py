import os
import base64
import requests
from flask import Flask, request, jsonify, redirect, session
from flask_cors import CORS

app = Flask(__name__)
app.secret_key = 'music_secret_key_123'
CORS(app, origins='*')

SPOTIFY_CLIENT_ID = os.environ.get('SPOTIFY_CLIENT_ID', '27bf7c0fa6fd42d6a31a76008d261d6b')
SPOTIFY_CLIENT_SECRET = os.environ.get('SPOTIFY_CLIENT_SECRET', '80e0f6d2652d4d929ef789690d22bff2')
SPOTIFY_REDIRECT_URI = os.environ.get('SPOTIFY_REDIRECT_URI', 'https://gift-bot-production.up.railway.app/spotify/callback')
SC_CLIENT_ID = os.environ.get('SC_CLIENT_ID', 'a3e059563d7fd3372b49b37f00a00bcf')

# ========== SPOTIFY ==========

def get_spotify_app_token():
    """Get app-level token (no user auth needed for search)"""
    creds = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
    res = requests.post('https://accounts.spotify.com/api/token',
        headers={'Authorization': f'Basic {creds}'},
        data={'grant_type': 'client_credentials'}
    )
    return res.json().get('access_token')

@app.route('/spotify/search')
def spotify_search():
    q = request.args.get('q', '')
    if not q:
        return jsonify({'error': 'No query'}), 400
    try:
        token = get_spotify_app_token()
        res = requests.get('https://api.spotify.com/v1/search',
            headers={'Authorization': f'Bearer {token}'},
            params={'q': q, 'type': 'track', 'limit': 20, 'market': 'RU'}
        )
        data = res.json()
        tracks = []
        for t in data.get('tracks', {}).get('items', []):
            tracks.append({
                'id': t['id'],
                'title': t['name'],
                'artist': ', '.join(a['name'] for a in t['artists']),
                'cover': t['album']['images'][0]['url'] if t['album']['images'] else None,
                'duration': t['duration_ms'] // 1000,
                'preview_url': t.get('preview_url'),
                'source': 'sp',
                'permalink': t['external_urls'].get('spotify'),
            })
        return jsonify(tracks)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/spotify/playlist')
def spotify_playlist():
    url = request.args.get('url', '')
    if not url:
        return jsonify({'error': 'No URL'}), 400
    try:
        # Extract playlist ID from URL
        # https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M
        playlist_id = None
        if 'playlist/' in url:
            playlist_id = url.split('playlist/')[1].split('?')[0]
        if not playlist_id:
            return jsonify({'error': 'Invalid Spotify playlist URL'}), 400

        token = get_spotify_app_token()
        res = requests.get(f'https://api.spotify.com/v1/playlists/{playlist_id}',
            headers={'Authorization': f'Bearer {token}'},
            params={'market': 'RU', 'fields': 'name,description,images,tracks.items(track(id,name,artists,album,duration_ms,preview_url,external_urls))'}
        )
        data = res.json()
        if 'error' in data:
            return jsonify({'error': data['error']['message']}), 400

        tracks = []
        for item in data.get('tracks', {}).get('items', []):
            t = item.get('track')
            if not t:
                continue
            tracks.append({
                'id': t['id'],
                'title': t['name'],
                'artist': ', '.join(a['name'] for a in t['artists']),
                'cover': t['album']['images'][0]['url'] if t['album']['images'] else None,
                'duration': t['duration_ms'] // 1000,
                'preview_url': t.get('preview_url'),
                'source': 'sp',
                'permalink': t['external_urls'].get('spotify'),
            })
        return jsonify({
            'name': data.get('name', 'Spotify Playlist'),
            'cover': data['images'][0]['url'] if data.get('images') else None,
            'tracks': tracks,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ========== SOUNDCLOUD ==========

@app.route('/soundcloud/search')
def soundcloud_search():
    q = request.args.get('q', '')
    if not q:
        return jsonify({'error': 'No query'}), 400
    try:
        res = requests.get('https://api.soundcloud.com/tracks',
            params={'q': q, 'limit': 20, 'client_id': SC_CLIENT_ID}
        )
        data = res.json()
        tracks = []
        for t in data:
            tracks.append({
                'id': t['id'],
                'title': t['title'],
                'artist': t.get('user', {}).get('username', 'Unknown'),
                'cover': t.get('artwork_url', '').replace('-large', '-t300x300') if t.get('artwork_url') else None,
                'duration': t['duration'] // 1000,
                'preview_url': f"{t['stream_url']}?client_id={SC_CLIENT_ID}" if t.get('stream_url') else None,
                'source': 'sc',
                'permalink': t.get('permalink_url'),
            })
        return jsonify(tracks)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/soundcloud/playlist')
def soundcloud_playlist():
    url = request.args.get('url', '')
    if not url:
        return jsonify({'error': 'No URL'}), 400
    try:
        res = requests.get('https://api.soundcloud.com/resolve',
            params={'url': url, 'client_id': SC_CLIENT_ID}
        )
        data = res.json()
        if 'tracks' not in data:
            return jsonify({'error': 'Not a playlist or invalid URL'}), 400

        tracks = []
        for t in data.get('tracks', []):
            tracks.append({
                'id': t['id'],
                'title': t['title'],
                'artist': t.get('user', {}).get('username', 'Unknown'),
                'cover': t.get('artwork_url', '').replace('-large', '-t300x300') if t.get('artwork_url') else None,
                'duration': t['duration'] // 1000,
                'preview_url': f"{t['stream_url']}?client_id={SC_CLIENT_ID}" if t.get('stream_url') else None,
                'source': 'sc',
                'permalink': t.get('permalink_url'),
            })
        return jsonify({
            'name': data.get('title', 'SoundCloud Playlist'),
            'cover': data.get('artwork_url', '').replace('-large', '-t300x300') if data.get('artwork_url') else None,
            'tracks': tracks,
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ========== COMBINED SEARCH ==========

@app.route('/search')
def search_all():
    q = request.args.get('q', '')
    if not q:
        return jsonify({'error': 'No query'}), 400

    results = {'spotify': [], 'soundcloud': []}

    # Spotify
    try:
        token = get_spotify_app_token()
        res = requests.get('https://api.spotify.com/v1/search',
            headers={'Authorization': f'Bearer {token}'},
            params={'q': q, 'type': 'track', 'limit': 10, 'market': 'RU'}
        )
        for t in res.json().get('tracks', {}).get('items', []):
            results['spotify'].append({
                'id': t['id'],
                'title': t['name'],
                'artist': ', '.join(a['name'] for a in t['artists']),
                'cover': t['album']['images'][0]['url'] if t['album']['images'] else None,
                'duration': t['duration_ms'] // 1000,
                'preview_url': t.get('preview_url'),
                'source': 'sp',
                'permalink': t['external_urls'].get('spotify'),
            })
    except:
        pass

    # SoundCloud
    try:
        res = requests.get('https://api.soundcloud.com/tracks',
            params={'q': q, 'limit': 10, 'client_id': SC_CLIENT_ID}
        )
        for t in res.json():
            results['soundcloud'].append({
                'id': t['id'],
                'title': t['title'],
                'artist': t.get('user', {}).get('username', 'Unknown'),
                'cover': t.get('artwork_url', '').replace('-large', '-t300x300') if t.get('artwork_url') else None,
                'duration': t['duration'] // 1000,
                'preview_url': f"{t['stream_url']}?client_id={SC_CLIENT_ID}" if t.get('stream_url') else None,
                'source': 'sc',
                'permalink': t.get('permalink_url'),
            })
    except:
        pass

    # Merge: interleave results
    merged = []
    sp = results['spotify']
    sc = results['soundcloud']
    for i in range(max(len(sp), len(sc))):
        if i < len(sp): merged.append(sp[i])
        if i < len(sc): merged.append(sc[i])

    return jsonify(merged)

@app.route('/import-playlist')
def import_playlist():
    url = request.args.get('url', '').strip()
    if not url:
        return jsonify({'error': 'No URL'}), 400

    if 'spotify.com' in url:
        if 'playlist/' in url:
            return spotify_playlist()
    elif 'soundcloud.com' in url:
        return soundcloud_playlist()

    return jsonify({'error': 'Unsupported platform. Supported: Spotify, SoundCloud'}), 400

@app.route('/health')
def health():
    return 'OK'

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5001))
    app.run(host='0.0.0.0', port=port)
