# Download maniger

A download manager for me and my family. One Windows PC at home does the downloading; everyone controls it from a web page on their phone (Android or iPhone) or computer, with a history of what was downloaded.

- **Web page:** https://kbs7s.github.io/download-maiger/ : paste a link, watch progress, see the family history, and save finished files to your phone.
- **Engine on the PC:** [aria2](https://github.com/aria2/aria2) for normal files (zip, exe, photos, audio, torrents, anything with a link), [yt-dlp](https://github.com/yt-dlp/yt-dlp) and ffmpeg for video sites, and a small helper (`engine/bridge.py`) that the web page talks to. It keeps one shared history in `engine/history.json`.
- Advanced: the helper also forwards `/jsonrpc` to aria2, so [AriaNg](https://github.com/mayswind/AriaNg) can connect to the same address too.

## Setup on the Windows PC (one time)

1. On this repo's GitHub page, click **Code → Download ZIP**, and unzip it somewhere permanent, for example `C:\DownloadManiger`.
2. Open the `engine` folder and double-click **`setup.bat`**.
   - If Windows says "Windows protected your PC", click **More info → Run anyway**.
   - It downloads aria2, yt-dlp, ffmpeg and a small private copy of Python (about 210 MB in total) into `engine\bin`.
   - It creates a **secret token** and shows it. It is also saved in `engine\MY-SECRET.txt`. Keep it private: anyone with it can control the downloads.
   - It asks whether to start automatically with Windows. Say **Y** if the PC is usually on.
3. Double-click **`start.bat`**. Keep that window open (minimize it). Closing it stops the engine.
4. On the PC, open https://kbs7s.github.io/download-maiger/, tap **Settings**, and enter address `http://localhost:6801`, the secret token, and your name.

Files are saved to `Downloads\DownloadManiger` in your Windows user folder.

### Other buttons in the `engine` folder

| File | What it does |
|---|---|
| `start.bat` | Starts the download engine and the helper |
| `stop.bat` | Stops it |
| `video.bat` | Paste a YouTube/Instagram/TikTok/Facebook link and download the video (up to 1080p, MP4) |
| `update.bat` | Updates yt-dlp. Run this if video downloads start failing |
| `setup.bat` | Run again any time; it keeps your secret token |

## Using it from phones (Android and iPhone)

The web page is on `https://kbs7s.github.io/download-maiger/`, but the engine is on the home PC. Browsers block an `https` page from talking to a plain `http` address on your PC, and phones on mobile data can't reach the home PC at all. The fix we recommend is **Tailscale** (free for personal use):

1. Install Tailscale on the PC and on each family phone ([tailscale.com/download](https://tailscale.com/download)), and sign in with the same account (or invite family members to your Tailscale network).
2. In the Tailscale admin page, turn on **MagicDNS** and **HTTPS certificates** (DNS tab).
3. On the PC, open Command Prompt and run once:
   ```
   tailscale serve --bg 6801
   ```
   This gives the engine a secure address like `https://your-pc-name.your-tailnet.ts.net`, reachable only from your own devices, at home or away.
4. On each phone, open the web page, tap **Settings**, and enter that `https://...ts.net` address, the secret token, and the person's name.
5. Add it to the home screen: on iPhone, Safari **Share → Add to Home Screen**; on Android, Chrome **⋮ → Add to Home screen**. On Android you can then **Share** a link from YouTube or any app straight to "Downloads".

**Family profiles:** the first time each phone connects, it asks "Who is using this device?". Pick your name or add a new one. Every download shows who added it, and in **History** you can filter by person. Tap your name at the top to switch.

**Arabic:** tap **ع** at the top to switch to Arabic, and **EN** to switch back. Phones set to Arabic open in Arabic automatically.

**GitHub links (like DownGit):** paste a GitHub folder link (`github.com/user/repo/tree/branch/folder`) and the PC downloads just that folder and makes a zip. A repo link downloads the whole repo as a zip, and a file link downloads that file.

**Saving to a phone:** in **History**, tap **Save to this device** on a finished download to copy it from the PC to the phone.

The engine itself only listens on the PC (`localhost`), so it is never exposed to your home Wi-Fi or the internet directly; Tailscale is the only way in.

## Status

- [x] Step 1: Engine setup scripts (this folder)
- [x] Step 2: Web page on GitHub Pages, with download list, shared history and save-to-phone
- [x] Step 3: Family features: Arabic/English, family profiles with history per person, GitHub folder download (like DownGit)
- [ ] Step 4: Test videos, photos, audio, zip and exe files, then share with family
