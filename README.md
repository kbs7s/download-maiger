# Download maniger

A download manager for me and my family. One Windows PC at home does the downloading; everyone controls it from a web page on their phone (Android or iPhone) or computer, with a history of what was downloaded.

- **Engine (this step):** [aria2](https://github.com/aria2/aria2) for normal files (zip, exe, photos, audio, anything with a link), plus [yt-dlp](https://github.com/yt-dlp/yt-dlp) and ffmpeg for video sites.
- **Web page (next step):** a GitHub Pages site based on [AriaNg](https://github.com/mayswind/AriaNg): paste a link, watch progress, see history.

## Setup on the Windows PC (one time)

1. On this repo's GitHub page, click **Code → Download ZIP**, and unzip it somewhere permanent, for example `C:\DownloadManiger`.
2. Open the `engine` folder and double-click **`setup.bat`**.
   - If Windows says "Windows protected your PC", click **More info → Run anyway**.
   - It downloads aria2, yt-dlp and ffmpeg (about 200 MB in total) into `engine\bin`.
   - It creates a **secret token** and shows it. It is also saved in `engine\MY-SECRET.txt`. Keep it private: anyone with it can control the downloads.
   - It asks whether to start automatically with Windows. Say **Y** if the PC is usually on.
3. Double-click **`start.bat`**. Keep that window open (minimize it). Closing it stops the engine.

Files are saved to `Downloads\DownloadManiger` in your Windows user folder.

### Other buttons in the `engine` folder

| File | What it does |
|---|---|
| `start.bat` | Starts the download engine |
| `stop.bat` | Stops it |
| `video.bat` | Paste a YouTube/Instagram/TikTok/Facebook link and download the video (up to 1080p, MP4) |
| `update.bat` | Updates yt-dlp. Run this if video downloads start failing |
| `setup.bat` | Run again any time; it keeps your secret token |

## Using it from phones (Android and iPhone)

The web page will be on `https://kbs7s.github.io/...`, but the engine is on the home PC. Browsers block an `https` page from talking to a plain `http` address on your PC, and phones on mobile data can't reach the home PC at all. The fix we recommend is **Tailscale** (free for personal use):

1. Install Tailscale on the PC and on each family phone ([tailscale.com/download](https://tailscale.com/download)), and sign in with the same account (or invite family members to your Tailscale network).
2. In the Tailscale admin page, turn on **MagicDNS** and **HTTPS certificates** (DNS tab).
3. On the PC, open Command Prompt and run once:
   ```
   tailscale serve --bg 6800
   ```
   This gives the engine a secure address like `https://your-pc-name.your-tailnet.ts.net`, reachable only from your own devices, at home or away.
4. In the web page settings you'll enter that address and the secret token.

The engine itself only listens on the PC (`localhost`), so it is never exposed to your home Wi-Fi or the internet directly; Tailscale is the only way in.

## Status

- [x] Step 1: Engine setup scripts (this folder)
- [ ] Step 2: Web page on GitHub Pages (AriaNg-based), with download list and history
- [ ] Step 3: Family features: mobile layout, Arabic/English, history per person, GitHub folder download (like DownGit)
- [ ] Step 4: Test videos, photos, audio, zip and exe files, then share with family
