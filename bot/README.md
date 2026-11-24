# بوت تلكرام: مدير التنزيلات

تدز للبوت رابط من يوتيوب أو بنترست أو إنستغرام أو تيك توك أو فيسبوك أو X، أو أي رابط ملف. يسألك تريده **🎬 فيديو** لو **🎵 صوت MP3** لو **🖼 صور / ملف**، وبعدين يرجعلك الملف بالمحادثة. يشتغل 24 ساعة على سيرفر Oracle Cloud المجاني، فما تحتاج حاسبة البيت.

- ينزل فيديوهات لحد **2 كيكا**، بجودة لحد 1080p وبصيغة MP4 تشتغل على كل الموبايلات.
- البوت **للعائلة فقط**: أول واحد يدز `/start` يصير المدير، وهو يضيف الباقين.
- `/history` يعرض آخر تنزيلاتك.
- برنامج yt-dlp يتحدث لحاله كل يوم.

---

## الخطوات (مرة وحدة، حدود 30 دقيقة)

### 1) سوّي البوت بالتلكرام
1. افتح **@BotFather** بالتلكرام ودز `/newbot`.
2. اختار اسم، مثلاً `Download maniger`، وبعدها اسم مستخدم ينتهي بـ `bot`، مثلاً `karar_dl_bot`.
3. ينطيك **توكن** شكله `123456789:ABC...`. احفظه وما تنطيه لأحد.

### 2) خذ api_id و api_hash
هذني يخلون البوت يدز ملفات كبيرة لحد 2 كيكا.
1. افتح https://my.telegram.org وسجّل برقم موبايلك.
2. ادخل **API development tools** واملأ أي اسم للتطبيق.
3. انسخ **api_id** (أرقام) و **api_hash**.

### 3) سوّي سيرفر Oracle Cloud المجاني
1. سجّل بـ https://www.oracle.com/cloud/free/. يطلب بطاقة للتحقق بس، وحساب Always Free ما ينسحب منه شي.
2. من القائمة: **Compute → Instances → Create instance**.
3. **Image**: اختار **Ubuntu 22.04** أو **24.04**.
4. **Shape**: اضغط Change shape، واختار **Ampere (VM.Standard.A1.Flex)**، وحط 2 OCPU و 12 GB. هذا ضمن المجاني.
   - إذا طلع "Out of capacity"، جرب بعد ساعة، أو اختار **VM.Standard.E2.1.Micro** (هم مجاني بس أضعف).
5. **SSH keys**: اختار **Generate a key pair** ونزّل المفتاح الخاص (private key)، أو اتركه وتستخدم Cloud Shell.
6. اضغط **Create** وانتظر لحد ما يصير **Running**.

### 4) نصّب البوت بأمر واحد
1. ادخل للسيرفر:
   - **الأسهل:** من صفحة الـ Instance اضغط **Cloud Shell** (فوق يمين، أيقونة `>_`)، واكتب:
     `ssh -i <ملف المفتاح> ubuntu@<Public IP>`
   - أو من أي حاسبة: `ssh -i key.pem ubuntu@<Public IP>`
2. الصق هذا الأمر:
   ```
   curl -fsSL https://raw.githubusercontent.com/kbs7s/download-maiger/main/bot/install.sh | bash
   ```
3. يسألك عن **التوكن** و **api_id** و **api_hash**، الصقهن.
4. انتظر حدود 3 دقائق لحد ما تطلع ✅.

### 5) شغّل البوت وأضف العائلة
1. افتح البوت بالتلكرام ودز `/start`. انت أول واحد، فتصير **المدير** 👑.
2. كل فرد من العائلة يدز `/start` للبوت، والبوت يرد عليه برقمه.
3. انت تدز للبوت `/adduser 123456789` (رقمه). خلص، يگدر يستخدمه.
   - `/users` يعرض المسموح لهم، و `/removeuser 123` يحذف واحد.

---

## إذا صارت مشكلة

- **يوتيوب يكول "Sign in to confirm you're not a bot":** يوتيوب أحياناً يحظر السيرفرات السحابية. الحل تصدّر ملف **cookies.txt** من متصفح مسجّل بيوتيوب (بإضافة "Get cookies.txt LOCALLY")، وتحطه بالسيرفر بمسار `~/download-maiger/bot/data/cookies.txt`. بعدها ضيف هذا السطر لملف `~/download-maiger/bot/.env`:
  ```
  COOKIES_FILE=/data/cookies.txt
  ```
  وبعدين: `cd ~/download-maiger/bot && sudo docker compose up -d`
- **تشوف السجل:** `cd ~/download-maiger/bot && sudo docker compose logs -f bot`
- **تحدّث البوت:** نفس أمر التنصيب. يحتفظ بإعداداتك.
- **توقف البوت:** `cd ~/download-maiger/bot && sudo docker compose down`

## كيف يشتغل (للمطورين)

- `bot.py`: python-telegram-bot 21، وينزّل بـ yt-dlp (فيديو أو MP3 بـ ffmpeg) وبـ gallery-dl للصور، ويحفظ السجل والمستخدمين بـ SQLite في `data/bot.db`.
- `docker-compose.yml`: يشغّل البوت ومعاه [telegram-bot-api](https://github.com/tdlib/telegram-bot-api) محلي بوضع `--local`. البوت يعطيه مسار الملف على القرص (`/data/...`) بدل ما يرفعه، وهذا يسمح بملفات لحد 2000 MB.
- البوت يستخدم polling، فما يحتاج يفتح أي منفذ (port) بالسيرفر.
