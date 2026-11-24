# Download maniger

A download manager for me and my family that runs entirely in the browser. No PC, no server, no install: open the page on any phone (Android or iPhone) or computer, paste a link, and the file is saved straight to that device.

**Open it:** https://kbs7s.github.io/download-maiger/

## What it does

- **Paste one or more links** (one per line) and tap **Download**. Progress, speed and a Cancel button show while the page downloads.
- **Direct links** (zip, exe, apk, photos, PDF, MP3, MP4 files, …) are saved to the device.
  - If a website doesn't allow downloads from other pages, or the file is bigger than about 700 MB, the page hands the link to the browser's own downloader instead. The file still lands in your Downloads (on iPhone: the **Files** app), and History marks it "Browser download".
- **GitHub links (like DownGit):**
  - a folder link (`github.com/user/repo/tree/branch/folder`) downloads just that folder as one zip, built in the browser,
  - a file link (`.../blob/...`) downloads that file,
  - a repo link (`github.com/user/repo`) downloads the whole repo as a zip.
  - GitHub allows 60 folder lookups per hour per network without signing in.
- **Video links** (YouTube, Pinterest, Instagram, TikTok…) open in cobalt.tools to save the video (see below).
- **History** of everything downloaded on this device, with search, filter by person, Download again, Copy link and Remove.
- **Family profiles:** the first time, the page asks "Who is using this device?". Pick a name or add one; each download records who added it. Tap the name at the top to switch.
- **Arabic / English:** tap **ع** at the top for Arabic (right-to-left), **EN** to go back. Devices set to Arabic open in Arabic.
- **Add to home screen:** iPhone: Safari **Share → Add to Home Screen**. Android: Chrome **⋮ → Add to Home screen**. On Android you can then **Share** a link from another app straight to "Downloads".

## What it can't do

- **Video pages** like YouTube, Pinterest, Instagram, TikTok and Facebook hide the real video file, so the page can't save them by itself. Instead it opens them in [cobalt.tools](https://cobalt.tools), a free website that saves the video to your device: the link is filled in and saving starts automatically. History keeps a **Download with cobalt** button for each video link. cobalt is a third-party service; if it's down or a site is unsupported, those videos won't download.
- **Torrents:** magnet links are passed to a torrent app if one is installed.
- History and profiles are stored on each device (in the browser), not shared between devices.

## Telegram bot

There is also a Telegram bot (in [`bot/`](bot/README.md)) that downloads YouTube, Pinterest, Instagram, TikTok and other videos, and sends them back in the chat, up to 2 GB. It runs on a free Oracle Cloud server, not a home PC. Setup steps (in Arabic) are in [bot/README.md](bot/README.md). In the page's History, video links have a **Send to Telegram bot** button that shares the link to the bot.

## How it works

Everything is one static page (`index.html`) on GitHub Pages. Downloads use the browser's `fetch` and are saved with a download link. GitHub folders are listed with the GitHub API and zipped with [JSZip](https://stuk.github.io/jszip/) (`lib/jszip.min.js`, MIT). History and settings live in the browser's local storage. Nothing is sent anywhere except to the site you're downloading from.

Earlier versions used a home Windows PC with aria2 and yt-dlp. That code is in the git history (`engine/` folder) if video downloads are ever wanted again.
