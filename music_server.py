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
SC_CLIENT_ID = 'iZIs9mchVcX5lhVRyQGGAYlNPVldzAoX'
SC_CLIENT_SECRET = 'pAKMBORnMBLqLRMGBaHDH7gkQJpBbsK5'
SC_CLIENT_ID2 = '2t9loNQH90kzJcsFCODdigxfp325aq4z'
SC_API = 'https://api-v2.soundcloud.com'

app = Flask(__name__)
CORS(app, origins='*')
app.secret_key = 'music_secret_123'

# ========== HELPERS ==========

def get_spotify_token():
    creds = base64.b64encode(f"{SPOTIFY_CLIENT_ID}:{SPOTIFY_CLIENT_SECRET}".encode()).decode()
    res = requests.post('https://accounts.spotify.com/api/token',
        headers={'Authorization': f'Basic {creds}'},
        data={'grant_type': 'client_credentials'},
        timeout=5
    )
    return res.json().get('access_token')

def sc_track_to_dict(t):
    """Convert SoundCloud v2 track to our format"""
    preview_url = None
    transcodings = t.get('media', {}).get('transcodings', [])
    for tc in transcodings:
        fmt = tc.get('format', {})
        if fmt.get('protocol') == 'progressive':
            try:
                r = requests.get(tc['url'], params={'client_id': SC_CLIENT_ID}, timeout=3)
                preview_url = r.json().get('url')
            except:
                pass
            break
    if not preview_url and transcodings:
        try:
            r = requests.get(transcodings[0]['url'], params={'client_id': SC_CLIENT_ID}, timeout=3)
            preview_url = r.json().get('url')
        except:
            pass
    return {
        'id': str(t.get('id', '')),
        'title': t.get('title', ''),
        'artist': t.get('user', {}).get('username', 'Unknown'),
        'cover': (t.get('artwork_url') or '').replace('-large', '-t300x300') or None,
        'duration': (t.get('duration') or 0) // 1000,
        'preview_url': preview_url,
        'source': 'sc',
        'permalink': t.get('permalink_url'),
    }

def sp_track_to_dict(t):
    """Convert Spotify track to our format"""
    return {
        'id': t['id'],
        'title': t['name'],
        'artist': ', '.join(a['name'] for a in t.get('artists', [])),
        'cover': t['album']['images'][0]['url'] if t.get('album', {}).get('images') else None,
        'duration': (t.get('duration_ms') or 0) // 1000,
        'preview_url': t.get('preview_url'),
        'source': 'sp',
        'permalink': t.get('external_urls', {}).get('spotify'),
    }

# ========== ROUTES ==========

@app.route('/health')
def health():
    return 'OK'

@app.route('/search')
def search_all():
    q = request.args.get('q', '')
    if not q:
        return jsonify({'error': 'No query'}), 400

    merged = []

    # Spotify
    try:
        token = get_spotify_token()
        res = requests.get('https://api.spotify.com/v1/search',
            headers={'Authorization': f'Bearer {token}'},
            params={'q': q, 'type': 'track', 'limit': 10},
            timeout=5
        )
        for t in res.json().get('tracks', {}).get('items', []):
            merged.append(sp_track_to_dict(t))
        print(f'[search] spotify: {len([x for x in merged if x["source"]=="sp"])} tracks')
    except Exception as e:
        print(f'[search] spotify error: {e}')

    # SoundCloud v2
    try:
        res = requests.get(f'{SC_API}/search/tracks',
            params={'q': q, 'limit': 10, 'client_id': SC_CLIENT_ID},
            headers={'Accept': 'application/json; charset=utf-8'},
            timeout=5
        )
        items = res.json().get('collection', [])
        for t in items:
            merged.append(sc_track_to_dict(t))
        print(f'[search] sc: {len([x for x in merged if x["source"]=="sc"])} tracks')
    except Exception as e:
        print(f'[search] sc error: {e}')

    print(f'[search] total: {len(merged)}')
    return jsonify(merged)

@app.route('/spotify/search')
def spotify_search():
    q = request.args.get('q', '')
    if not q:
        return jsonify({'error': 'No query'}), 400
    try:
        token = get_spotify_token()
        res = requests.get('https://api.spotify.com/v1/search',
            headers={'Authorization': f'Bearer {token}'},
            params={'q': q, 'type': 'track', 'limit': 20},
            timeout=5
        )
        return jsonify([sp_track_to_dict(t) for t in res.json().get('tracks', {}).get('items', [])])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/soundcloud/search')
def soundcloud_search():
    q = request.args.get('q', '')
    if not q:
        return jsonify({'error': 'No query'}), 400
    try:
        res = requests.get(f'{SC_API}/search/tracks',
            params={'q': q, 'limit': 20, 'client_id': SC_CLIENT_ID},
            headers={'Accept': 'application/json; charset=utf-8'},
            timeout=5
        )
        return jsonify([sc_track_to_dict(t) for t in res.json().get('collection', [])])
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/artist/search')
def artist_search():
    q = request.args.get('q', '')
    if not q:
        return jsonify({'error': 'No query'}), 400

    result = {'spotify': None, 'soundcloud': None, 'tracks': []}

    # Spotify artist
    try:
        token = get_spotify_token()
        res = requests.get('https://api.spotify.com/v1/search',
            headers={'Authorization': f'Bearer {token}'},
            params={'q': q, 'type': 'artist', 'limit': 1},
            timeout=5
        )
        artists = res.json().get('artists', {}).get('items', [])
        if artists:
            a = artists[0]
            result['spotify'] = {
                'id': a['id'], 'name': a['name'],
                'cover': a['images'][0]['url'] if a.get('images') else None,
                'followers': a.get('followers', {}).get('total', 0),
                'genres': a.get('genres', [])[:3],
            }
            top = requests.get(f"https://api.spotify.com/v1/artists/{a['id']}/top-tracks",
                headers={'Authorization': f'Bearer {token}'},
                params={'market': 'US'},
                timeout=5
            )
            for t in top.json().get('tracks', [])[:10]:
                result['tracks'].append(sp_track_to_dict(t))
    except Exception as e:
        print(f'[artist] spotify error: {e}')

    # SoundCloud artist
    try:
        res = requests.get(f'{SC_API}/search/users',
            params={'q': q, 'limit': 1, 'client_id': SC_CLIENT_ID},
            headers={'Accept': 'application/json; charset=utf-8'},
            timeout=5
        )
        users = res.json().get('collection', [])
        if users:
            u = users[0]
            result['soundcloud'] = {
                'id': u['id'], 'name': u.get('username', ''),
                'cover': (u.get('avatar_url') or '').replace('-large', '-t300x300') or None,
                'followers': u.get('followers_count', 0),
            }
            tracks_res = requests.get(f"{SC_API}/users/{u['id']}/tracks",
                params={'limit': 10, 'client_id': SC_CLIENT_ID},
                headers={'Accept': 'application/json; charset=utf-8'},
                timeout=5
            )
            for t in tracks_res.json().get('collection', []):
                result['tracks'].append(sc_track_to_dict(t))
    except Exception as e:
        print(f'[artist] sc error: {e}')

    return jsonify(result)

@app.route('/import-playlist')
def import_playlist():
    url = request.args.get('url', '').strip()
    if not url:
        return jsonify({'error': 'No URL'}), 400

    if 'spotify.com' in url and 'playlist/' in url:
        try:
            playlist_id = url.split('playlist/')[1].split('?')[0].split('&')[0].strip()
            token = get_spotify_token()
            res = requests.get(f'https://api.spotify.com/v1/playlists/{playlist_id}',
                headers={'Authorization': f'Bearer {token}'},
                params={'fields': 'name,images,tracks.items(track(id,name,artists,album,duration_ms,preview_url,external_urls))'},
                timeout=10
            )
            data = res.json()
            if 'error' in data:
                return jsonify({'error': data['error']['message']}), 400
            tracks = []
            for item in data.get('tracks', {}).get('items', []):
                t = item.get('track')
                if t:
                    tracks.append(sp_track_to_dict(t))
            return jsonify({
                'name': data.get('name', 'Spotify Playlist'),
                'cover': data['images'][0]['url'] if data.get('images') else None,
                'tracks': tracks,
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    elif 'soundcloud.com' in url:
        try:
            res = requests.get(f'{SC_API}/resolve',
                params={'url': url, 'client_id': SC_CLIENT_ID},
                headers={'Accept': 'application/json; charset=utf-8'},
                timeout=10
            )
            data = res.json()
            tracks_data = data.get('tracks', data.get('collection', []))
            if not tracks_data:
                return jsonify({'error': 'Not a playlist or no tracks'}), 400
            tracks = [sc_track_to_dict(t) for t in tracks_data]
            return jsonify({
                'name': data.get('title', 'SoundCloud Playlist'),
                'cover': (data.get('artwork_url') or '').replace('-large', '-t300x300') or None,
                'tracks': tracks,
            })
        except Exception as e:
            return jsonify({'error': str(e)}), 500

    return jsonify({'error': 'Unsupported platform. Use Spotify or SoundCloud link'}), 400

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
