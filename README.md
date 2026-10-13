# TTS RSS

Turn web articles (or any text) into a private podcast feed, read aloud by
[ElevenLabs](https://elevenlabs.io), that you can subscribe to in Pocket Casts or any
other podcast app.

Everything runs on your laptop. The server only needs SSH access and a web server that
serves static files: no code runs there and it never sees your API key.

```
tts-rss add <url> ──► extract article text ──► ElevenLabs ──► MP3
                                                               │ ssh
                      server: audio/*.mp3, episodes.json, feed.xml ◄──┘
                                       │ nginx (basic auth)
                                  Pocket Casts
```

## Install

```sh
uv tool install git+https://github.com/bm371613/TTS-RSS
# or, from a checkout:
uv tool install .
```

Copy `config.example.toml` to `~/.config/tts-rss/config.toml` and fill it in. The API key
can come from `ELEVENLABS_API_KEY` instead of the file.

## Usage

```sh
tts-rss add https://example.com/some-article       # extract, confirm cost, publish
tts-rss add https://example.com/some-article --dry-run > article.txt   # just see the text
tts-rss add article.txt --title "Some article" --link https://example.com/some-article
pbpaste | tts-rss add - --title "Notes"           # text from stdin
tts-rss add ... --lang pl                          # override language detection
tts-rss list                                       # published episodes
tts-rss rebuild                                    # regenerate feed.xml, e.g. after
                                                   # changing the feed title in the config
```

`add` shows the character count (what ElevenLabs bills) and asks before generating; `-y`
skips the question. To fix up badly extracted text, use `--dry-run` to save it, edit the
file, and add the file instead.

Language: text that is (almost) entirely Polish is read with the `pl` voice, everything
else with the `en` voice.

The generated MP3 is kept in `~/.cache/tts-rss/`. If the upload fails, publish it later
without paying again: `tts-rss add <same source> --audio ~/.cache/tts-rss/<file>.mp3`.

## Server layout

```
<server.path>/
  feed.xml          podcast feed (subscribe to <base_url>/feed.xml)
  episodes.json     episode list, the source of truth for feed.xml
  audio/*.mp3       episodes; file names include a random part, so they are not guessable
```

Example Nginx location with basic auth (create the password file with
`htpasswd -c /etc/nginx/tts.htpasswd <user>`):

```nginx
location /tts/ {
    alias /var/www/tts/;
    auth_basic "TTS RSS";
    auth_basic_user_file /etc/nginx/tts.htpasswd;
    location ~ /episodes\.json$ { deny all; }
}
```

## Pocket Casts

Pocket Casts accepts credentials embedded in the feed URL. Submit
`https://user:password@example.org/tts/feed.xml` at <https://pocketcasts.com/submit> and
choose **Private**, so it never appears in search. Use only letters and digits in the
password; special characters are known to cause trouble. See
[Pocket Casts: password protected feeds](https://support.pocketcasts.com/knowledge-base/password-protected-podcasts/).

Pocket Casts officially calls basic auth "sometimes works". If the feed loads but
episodes do not download, set `media_base_url` with the credentials in the config and run
`tts-rss rebuild`.

## Development

```sh
uv sync
uv run pytest
uv run ruff check . && uv run black --check .
```
