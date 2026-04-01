import os
import base64
import threading
import requests
from flask import Flask, request, jsonify
from flask_cors import CORS
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo

BOT_TOKEN = '8621939796:AAGIq5lQwkZl_-IFyZT2gszdhJ8hRPMUPfo'
WEBAPP_URL = 'https://rnfv2495-del.github.io/music-bot/music_player.html'
SPOTIFY_CLIENT_ID = '27bf7c0fa6fd42d6a31a76008d261d6b'
SPOTIFY_CLIENT_SECRET = '80e0f6d2652d4d929ef789690d22bff2'
SC_CLIENT_ID = 'a3e059563d7fd3372b49b37f00a00bcf'

app = Flask(__name__)
CORS(app, origins='*')
app.secret_key = 'music_secret_123'

def get_spotify_token():
    creds = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
    res = requests.post('https://accounts.spotify.com/api/token',
        headers={'Authorization': f'Basic {creds}'},
        data={'grant_type': 'client_credentials'}
    )
    return res.json().get('access_token')

@app.route('/health')
def health():
    return 'OK'

@app.route('/spotify/search')
def spotify_search():
    q = request.args.get('q', '')
    if not q:
        return jsonify({'error': 'No query'}), 400
    try:
        token = get_spotify_token()
        res = requests.get('https://api.spotify.com/v1/search',
            headers={'Authorization': f'Bearer {token}'},
            params={'q': q, 'type': 'track', 'limit': 20, 'market': 'RU'}
        )
        tracks = []
        for t in res.json().get('tracks', {}).get('items', []):
            tracks.append({
                'id': t['id'], 'title': t['name'],
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

@app.route('/soundcloud/search')
def soundcloud_search():
    q = request.args.get('q', '')
    if not q:
        return jsonify({'error': 'No query'}), 400
    try:
        res = requests.get('https://api.soundcloud.com/tracks',
            params={'q': q, 'limit': 20, 'client_id': SC_CLIENT_ID}
        )
        tracks = []
        for t in res.json():
            tracks.append({
                'id': t['id'], 'title': t['title'],
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

def sc_fallback(title, artist):
    """Search SoundCloud for a track to get preview URL"""
    try:
        res = requests.get('https://api.soundcloud.com/tracks',
            params={'q': f'{artist} {title}', 'limit': 1, 'client_id': SC_CLIENT_ID},
            timeout=3
        )
        data = res.json()
        if data and data[0].get('stream_url'):
            return f"{data[0]['stream_url']}?client_id={SC_CLIENT_ID}"
    except:
        pass
    return None

@app.route('/search')
def search_all():
    q = request.args.get('q', '')
    if not q:
        return jsonify({'error': 'No query'}), 400
    merged = []
    try:
        token = get_spotify_token()
        res = requests.get('https://api.spotify.com/v1/search',
            headers={'Authorization': f'Bearer {token}'},
            params={'q': q, 'type': 'track', 'limit': 10, 'market': 'RU'}
        )
        for t in res.json().get('tracks', {}).get('items', []):
            preview = t.get('preview_url')
            title = t['name']
            artist = ', '.join(a['name'] for a in t['artists'])
            # If no preview, try SoundCloud fallback
            if not preview:
                preview = sc_fallback(title, artist)
            merged.append({
                'id': t['id'], 'title': title,
                'artist': artist,
                'cover': t['album']['images'][0]['url'] if t['album']['images'] else None,
                'duration': t['duration_ms'] // 1000,
                'preview_url': preview,
                'source': 'sp',
                'permalink': t['external_urls'].get('spotify'),
            })
    except:
        pass
    try:
        res = requests.get('https://api.soundcloud.com/tracks',
            params={'q': q, 'limit': 10, 'client_id': SC_CLIENT_ID}
        )
        for t in res.json():
            merged.append({
                'id': t['id'], 'title': t['title'],
                'artist': t.get('user', {}).get('username', 'Unknown'),
                'cover': t.get('artwork_url', '').replace('-large', '-t300x300') if t.get('artwork_url') else None,
                'duration': t['duration'] // 1000,
                'preview_url': f"{t['stream_url']}?client_id={SC_CLIENT_ID}" if t.get('stream_url') else None,
                'source': 'sc',
                'permalink': t.get('permalink_url'),
            })
    except:
        pass
    return jsonify(merged)

@app.route('/artist/search')
def artist_search():
    q = request.args.get('q', '')
    if not q:
        return jsonify({'error': 'No query'}), 400
    result = {'spotify': None, 'soundcloud': None, 'tracks': []}
    try:
        token = get_spotify_token()
        # Search artist
        res = requests.get('https://api.spotify.com/v1/search',
            headers={'Authorization': f'Bearer {token}'},
            params={'q': q, 'type': 'artist', 'limit': 1, 'market': 'RU'}
        )
        artists = res.json().get('artists', {}).get('items', [])
        if artists:
            a = artists[0]
            result['spotify'] = {
                'id': a['id'],
                'name': a['name'],
                'cover': a['images'][0]['url'] if a.get('images') else None,
                'followers': a.get('followers', {}).get('total', 0),
                'genres': a.get('genres', [])[:3],
            }
            # Get top tracks
            top = requests.get(f"https://api.spotify.com/v1/artists/{a['id']}/top-tracks",
                headers={'Authorization': f'Bearer {token}'},
                params={'market': 'RU'}
            )
            for t in top.json().get('tracks', [])[:10]:
                preview = t.get('preview_url')
                title = t['name']
                artist = ', '.join(ar['name'] for ar in t['artists'])
                if not preview:
                    preview = sc_fallback(title, artist)
                result['tracks'].append({
                    'id': t['id'], 'title': title,
                    'artist': artist,
                    'cover': t['album']['images'][0]['url'] if t['album']['images'] else None,
                    'duration': t['duration_ms'] // 1000,
                    'preview_url': preview,
                    'source': 'sp',
                    'permalink': t['external_urls'].get('spotify'),
                })
    except Exception as e:
        pass
    try:
        # SoundCloud artist
        res = requests.get('https://api.soundcloud.com/users',
            params={'q': q, 'limit': 1, 'client_id': SC_CLIENT_ID}
        )
        users = res.json()
        if users:
            u = users[0]
            result['soundcloud'] = {
                'id': u['id'],
                'name': u['username'],
                'cover': u.get('avatar_url', '').replace('-large', '-t300x300') if u.get('avatar_url') else None,
                'followers': u.get('followers_count', 0),
            }
            # Get tracks
            tracks_res = requests.get(f"https://api.soundcloud.com/users/{u['id']}/tracks",
                params={'limit': 10, 'client_id': SC_CLIENT_ID}
            )
            for t in tracks_res.json():
                result['tracks'].append({
                    'id': t['id'], 'title': t['title'],
                    'artist': u['username'],
                    'cover': t.get('artwork_url', '').replace('-large', '-t300x300') if t.get('artwork_url') else None,
                    'duration': t['duration'] // 1000,
                    'preview_url': f"{t['stream_url']}?client_id={SC_CLIENT_ID}" if t.get('stream_url') else None,
                    'source': 'sc',
                    'permalink': t.get('permalink_url'),
                })
    except:
        pass
    return jsonify(result)

@app.route('/spotify/playlist')
def spotify_playlist():
    url = request.args.get('url', '')
    if 'playlist/' not in url:
        return jsonify({'error': 'Invalid Spotify playlist URL'}), 400
    try:
        playlist_id = url.split('playlist/')[1].split('?')[0]
        token = get_spotify_token()
        res = requests.get(f'https://api.spotify.com/v1/playlists/{playlist_id}',
            headers={'Authorization': f'Bearer {token}'},
            params={'market': 'RU', 'fields': 'name,images,tracks.items(track(id,name,artists,album,duration_ms,preview_url,external_urls))'}
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
                'id': t['id'], 'title': t['name'],
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

@app.route('/soundcloud/playlist')
def soundcloud_playlist():
    url = request.args.get('url', '')
    try:
        res = requests.get('https://api.soundcloud.com/resolve',
            params={'url': url, 'client_id': SC_CLIENT_ID}
        )
        data = res.json()
        if 'tracks' not in data:
            return jsonify({'error': 'Not a playlist'}), 400
        tracks = []
        for t in data.get('tracks', []):
            tracks.append({
                'id': t['id'], 'title': t['title'],
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

@app.route('/import-playlist')
def import_playlist():
    url = request.args.get('url', '').strip()
    if not url:
        return jsonify({'error': 'No URL'}), 400
    if 'spotify.com' in url and 'playlist/' in url:
        try:
            playlist_id = url.split('playlist/')[1].split('?')[0]
            token = get_spotify_token()
            res = requests.get(f'https://api.spotify.com/v1/playlists/{playlist_id}',
                headers={'Authorization': f'Bearer {token}'},
                params={'market': 'RU', 'fields': 'name,images,tracks.items(track(id,name,artists,album,duration_ms,preview_url,external_urls))'}
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
                    'id': t['id'], 'title': t['name'],
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
    elif 'soundcloud.com' in url:
        try:
            res = requests.get('https://api.soundcloud.com/resolve',
                params={'url': url, 'client_id': SC_CLIENT_ID}
            )
            data = res.json()
            if 'tracks' not in data:
                return jsonify({'error': 'Not a playlist'}), 400
            tracks = []
            for t in data.get('tracks', []):
                tracks.append({
                    'id': t['id'], 'title': t['title'],
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
    return jsonify({'error': 'Unsupported platform. Use Spotify or SoundCloud playlist link'}), 400

# ========== BOT ==========
bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def start(message):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(
        '🎵 Открыть плеер',
        web_app=WebAppInfo(url=WEBAPP_URL)
    ))
    bot.send_message(
        message.chat.id,
        '🎧 *Soundwave*\n\nМузыкальный плеер с поиском по Spotify и SoundCloud.\n\nНажми кнопку чтобы открыть!',
        parse_mode='Markdown',
        reply_markup=markup
    )

@bot.message_handler(commands=['player'])
def player(message):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton(
        '🎵 Открыть плеер',
        web_app=WebAppInfo(url=WEBAPP_URL)
    ))
    bot.send_message(message.chat.id, '🎵 Открывай!', reply_markup=markup)

def run_bot():
    print('Bot started')
    bot.polling(none_stop=True, timeout=60)

if __name__ == '__main__':
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
