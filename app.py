import tkinter as tk
from tkinter import font as tkfont
import threading
import json
import time
import re
import queue
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
import ctypes
import pyperclip
import os
import sys
import subprocess
import tempfile

# ── Version ───────────────────────────────────────────────────
APP_VERSION = "1.0.0"

# ── Auto-updater ──────────────────────────────────────────────
# Point these at YOUR GitHub repo (owner/repo).
# The updater checks the latest GitHub Release for a newer version tag
# and downloads the new EXE from the release assets automatically.
GITHUB_REPO   = "DevYama/pls-donate-tracker"   # ← change this
UPDATE_ASSET  = "PLS-DONATE-Tracker.exe"              # asset name in the release

def _check_for_updates(on_update_found):
    """Run in a background thread. Calls on_update_found(latest_ver, download_url) if newer."""
    try:
        url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
        req = urllib.request.Request(url, headers={"User-Agent": "PLS-DONATE-Tracker"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        latest_tag = data.get("tag_name", "").lstrip("v")
        if not latest_tag:
            return
        # Simple semver comparison
        def ver_tuple(v):
            try: return tuple(int(x) for x in v.split("."))
            except: return (0,)
        if ver_tuple(latest_tag) > ver_tuple(APP_VERSION):
            # Find the EXE asset download URL
            for asset in data.get("assets", []):
                if asset.get("name", "").lower() == UPDATE_ASSET.lower():
                    on_update_found(latest_tag, asset["browser_download_url"])
                    return
    except Exception:
        pass  # Silently ignore network errors


def _do_update(download_url, app_ref):
    """Download the new EXE and swap it in, then restart."""
    try:
        app_ref.root.after(0, lambda: app_ref.show_toast("⬇️  Downloading update…"))
        exe_path = sys.executable if getattr(sys, "frozen", False) else None
        if not exe_path:
            return  # Only works when running as .exe

        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".exe")
        os.close(tmp_fd)

        req = urllib.request.Request(download_url, headers={"User-Agent": "PLS-DONATE-Tracker"})
        with urllib.request.urlopen(req, timeout=60) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            with open(tmp_path, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total:
                        pct = int(downloaded / total * 100)
                        app_ref.root.after(0, lambda p=pct: app_ref.show_toast(f"⬇️  Updating… {p}%"))

        # Write a tiny bat launcher that replaces the old exe after we exit
        bat = tempfile.NamedTemporaryFile(delete=False, suffix=".bat", mode="w")
        bat.write(f"""@echo off
timeout /t 2 /nobreak >nul
move /y "{tmp_path}" "{exe_path}"
start "" "{exe_path}"
del "%~f0"
""")
        bat.flush(); bat.close()
        subprocess.Popen(["cmd", "/c", bat.name], creationflags=0x08000000)
        app_ref.root.after(0, app_ref.root.destroy)
    except Exception as e:
        app_ref.root.after(0, lambda: app_ref.show_toast(f"⚠️  Update failed: {e}"))


def _prompt_update(latest_ver, download_url, app_ref):
    """Show a non-blocking update banner inside the app."""
    def _show():
        try:
            banner = tk.Frame(app_ref.root, bg="#1a1a0a", cursor="hand2")
            banner.place(relx=0, rely=0, relwidth=1, height=32)
            msg = tk.Label(banner,
                text=f"  🚀  v{latest_ver} available — click to update (auto-restarts)  ✕",
                bg="#1a1a0a", fg="#ffb730",
                font=("Consolas", 8, "bold"), cursor="hand2")
            msg.pack(side="left", padx=4)

            def _start_update(e=None):
                banner.destroy()
                threading.Thread(target=_do_update, args=(download_url, app_ref), daemon=True).start()

            def _dismiss(e=None):
                banner.destroy()

            msg.bind("<Button-1>", _start_update)
            # Small ✕ dismiss button
            close_btn = tk.Label(banner, text="✕", bg="#1a1a0a", fg="#707088",
                                 font=("Consolas", 9, "bold"), cursor="hand2", padx=8)
            close_btn.pack(side="right")
            close_btn.bind("<Button-1>", _dismiss)
        except Exception:
            pass
    app_ref.root.after(0, _show)

# ── Roblox username: 3-20 chars, alphanumeric + underscore ───
_ROBLOX_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_]{1,18}[A-Za-z0-9]$|^[A-Za-z0-9]{3}$')

# Common noise words to skip
_NOISE = {
    # Basic words
    'pls','please','donate','me','the','and','for','you','him','her','them','all',
    'can','give','get','has','have','will','would','could','should','but','not',
    'sub','like','liked','subbed','notify','notif','tysm','tysmmmmm','lol','bro',
    'yes','yep','nope','just','more','robux','had','want','if','i','u','ur',
    'gamble','user','name','my','its','join','play','go','do','did','does',
    'he','she','it','we','they','his','hers','hi','hello','hey','ok','okay',
    'come','came','already','now','here','there','when','what','how','why','who',
    'gg','rip','omg','wow','lmao','bruh','nah','yeah','true','false','wait',
    'still','well','then','than','that','this','these','those','with','from',
    'about','into','onto','upon','over','under','after','before','since','until',
    'face','hand','planet','emoji','red','blue','green','orange','pink','yellow',
    'droopy','eyes','smiling','waving','ring','purple',
    # Social media & platforms (big false-positive source)
    'discord','roblox','tiktok','youtube','twitter','instagram','twitch','facebook',
    'reddit','snapchat','telegram','whatsapp','spotify','netflix','minecraft',
    'fortnite','xbox','playstation','nintendo','steam','epic','https','http',
    'www','com','net','org','io','gg','link','click','bio','profile','channel',
    # Roblox game / chat terms
    'bloxburg','adopt','brookhaven','obby','gamepass','gamelink','starcode',
    'catalog','avatar','outfit','robuxfree','freerobux','hack','script','exploit',
    'executor','pastebin','mediafire','linkvertise','bitly',
    # Donation / money talk
    'donate','donated','donating','donation','pay','paid','payment','fund',
    'booth','stand','goal','target','total','amount','gems','coins','cash',
    # Chat filler
    'type','chat','msg','message','send','sent','said','say','told','tell',
    'watch','watching','live','stream','streaming','video','clip','shorts',
    'follow','followed','following','support','supporter','love','loved',
    'thanks','thank','thx','tysm','ty','np','welcome','yw','sure','cool',
    'nice','good','great','best','worst','bad','sad','mad','hype','lit',
    'fire','goat','pog','poggers','ez','gg','glhf','irl','afk','gtg','brb',
    'lmk','idk','idc','tbh','ngl','fr','frfr','no','yes','maybe','rn','btw',
    # Numbers / placeholders that pass the regex
    'abc','xyz','test','demo','fake','null','none','void','bot','auto',
    # Common English words that look like usernames
    'star','stars','king','queen','lord','god','pro','noob','noobs','clan',
    'team','crew','gang','squad','house','home','shop','store','world','land',
    'time','date','day','week','month','year','life','game','games','play',
    'win','won','lost','lose','lose','next','last','first','second','third',
    'new','old','big','small','long','short','fast','slow','high','low',
    'real','fake','true','official','main','backup','alt','acc','account',
    # ── ADDED: common English words frequently seen in chat ──
    'alright','aight','hello','helo','helo','howdy','greetings','salut',
    'wassup','whatsup','sup','wsp',
    'sorry','apologize','apologies','excuse',
    'congratulations','congrats','grats','gratz',
    'welcome','welcomed','welcoming',
    'enjoy','enjoyed','enjoying','enjoyable',
    'missed','missing','misses',
    'amazing','awesome','wonderful','fantastic','excellent','incredible','unbelievable',
    'beautiful','gorgeous','pretty','cute','adorable',
    'money','dollar','dollars','cash','bank','rich','poor',
    'people','person','everyone','anybody','somebody','nobody','someone','anyone',
    'thing','things','stuff','item','items','something','nothing','anything',
    'place','places','location','area','region','zone',
    'right','wrong','correct','incorrect','exact','exactly',
    'again','always','never','often','sometimes','usually','rarely',
    'today','tonight','tomorrow','yesterday','morning','evening','afternoon','night',
    'ready','prepared','waiting','pending','done','finished','complete','completed',
    'look','looks','looking','see','seen','show','shows','showing',
    'work','works','working','worked','worker',
    'make','makes','making','made','create','creates','creating','created',
    'find','finds','finding','found','search','searches','searching',
    'know','knows','knowing','knew','understand','understood',
    'think','thinks','thinking','thought','believe','believes','believed',
    'feel','feels','feeling','felt',
    'need','needs','needing','needed','require','requires','required',
    'help','helps','helping','helped','helper','assist','assists','assisted',
    'start','starts','starting','started','begin','begins','began','begun',
    'stop','stops','stopping','stopped','end','ends','ending','ended',
    'open','opens','opening','opened','close','closes','closing','closed',
    'keep','keeps','keeping','kept','hold','holds','holding','held',
    'move','moves','moving','moved','run','runs','running','ran',
    'back','front','left','right','top','bottom','side','middle','center',
    'away','around','inside','outside','above','below','between',
    'much','many','some','few','less','least','most','more','enough',
    'only','even','every','each','both','either','neither','another','other',
    'same','different','similar','like','unlike',
    'also','too','very','really','quite','rather','pretty','fairly',
    'maybe','perhaps','probably','definitely','certainly','absolutely',
    'actually','basically','literally','honestly','seriously','obviously',
    'please','thankyou','thanku','tyvm','tyvmm',
    'later','soon','quick','quickly','slowly','fast','finally','almost',
    'whole','half','part','full','empty',
    'free','paid','cost','price','worth','value',
    'number','numbers','count','total','average','percent',
    'channel','channels','video','videos','stream','streams','clip','clips',
    'comment','comments','reply','replies','post','posts','share','shares',
    'subscriber','subscribers','viewer','viewers','member','members',
    'notification','notifications','bell','subscribe','unsubscribe',
    'random','randomly','chance','luck','lucky','unlucky',
    'serious','seriously','calm','calmly','loud','quiet','silent',
    'special','normal','regular','weird','strange','odd','unusual',
    'important','useful','useless','pointless','meaningless',
    'public','private','secret','hidden','visible','invisible',
    'simple','easy','hard','difficult','complex','complicated',
    'possible','impossible','allowed','forbidden','banned',
    'laugh','laughing','laughed','cry','crying','cried','scream','screaming',
    'run','running','walk','walking','jump','jumping','sit','sitting',
    'read','reading','write','writing','draw','drawing',
    'eat','eating','drink','drinking','sleep','sleeping',
    'win','winning','lose','losing','fight','fighting','kill','killing',
    'buy','buying','sell','selling','trade','trading','spend','spending',
    'add','added','remove','removed','delete','deleted','clear','cleared',
    'update','updated','upgrade','upgraded','download','downloaded',
    'connect','connected','disconnect','disconnected','join','joined','leave','left',
    'change','changed','switch','switched','swap','swapped','replace','replaced',
    'check','checked','verify','verified','confirm','confirmed','approve','approved',
    'block','blocked','report','reported','mute','muted','kick','kicked',
    # concatenated chat phrases (mashed-together words)
    'thanksyou','thankyouman','thanksyouman','thanksman','thanksmate',
    'niceone','nicework','goodjob','goodwork','wellplayed','welldone',
    'sorryman','sorrybro','noproblem','noprob','noproblemo',
    'ohwell','nevermind','dontworry','dontcare','idonotcare',
    'letsgoo','letsgo','comeon','comeone','hurryup','hurry',
    'shutup','shutit','begone','getlost','goaway',
    'ohman','ohboy','ohno','ohnoo','ohnooo',
    'hahaha','hahah','haha','hihi','huhu','hoho','hehe',
    'byebye','goodbye','goodnight','goodmorning','goodafternoon',
    'ohwow','ohgosh','omgosh','omgggg','omgomg',
    'plsdonate','pleasedonate','donatemepls','donatemeplease',
    'iloveyou','iloveu','iluvu','loveyou','loveu',
}

# Detects spam-stretched words: 3+ consecutive identical letters
_SPAM_STRETCH = re.compile(r'(.)\1{2,}', re.IGNORECASE)

# Common English prefixes/suffixes — if a token is ONLY made of these, it's a word not a username
_COMMON_WORD_PARTS = re.compile(
    r'^(thanks?|thank|hello|alright|alrite|aight|sorry|congrats?|welcome|enjoy|'
    r'miss|good|great|nice|love|hate|best|worst|cool|awesome|amazing|wow|omg|'
    r'bye|goodbye|night|morning|hey|sup|wassup|whats?up|please|help|need|want|'
    r'give|take|get|got|put|let|make|look|see|know|think|feel|try|use|go|come|'
    r'back|done|wait|stop|start|end|open|close|yes|yep|nah|nope|okay|sure|'
    r'right|wrong|same|diff|next|last|only|also|even|just|very|too|more|less|'
    r'much|many|some|few|any|all|both|each|every|no|not|nor|but|and|or|so|yet|'
    r'man|bro|dude|mate|guys?|people|person|someone|anyone|everyone|nobody|'
    r'thing|stuff|stuff|item|place|area|time|day|week|month|year|life|world|'
    r'game|play|win|lose|run|walk|jump|read|write|eat|drink|sleep|buy|sell)+$',
    re.IGNORECASE
)


def _is_common_english_word(tok):
    """
    Returns True if the token looks like a plain English word / chat phrase
    rather than a Roblox username.
    Catches:
      - Pure dictionary words: alright, hello, sorry, thanks
      - Mashed phrases: thanksyouman, niceone, goodjob
      - Repeated-letter spam: wwwwww, hahaha, hihi
    """
    lc = tok.lower()

    # Already in noise set
    if lc in _NOISE:
        return True

    # All same letter repeated (wwwww, aaaaaaa)
    if len(set(lc)) == 1:
        return True

    # Matches the common-word-parts mega-regex (pure English morpheme soup)
    if _COMMON_WORD_PARTS.match(lc):
        return True

    # Heuristic: token is all alpha, no digits/underscore, and looks like
    # concatenated common words (e.g. "thanksyouman").
    # We do a greedy left-to-right word segmentation using a compact common-words set.
    if tok.isalpha() and len(tok) >= 8:
        if _is_concatenated_words(lc):
            return True

    return False


# Compact set of very common English words for the segmenter
_COMMON_WORDS = {
    'a','an','the','and','or','but','if','in','on','at','to','for','of','with',
    'is','are','was','were','be','been','being','have','has','had','do','does',
    'did','will','would','could','should','may','might','shall','must','can',
    'not','no','nor','so','yet','both','either','neither','than','then','else',
    'when','where','why','how','what','who','which','that','this','these','those',
    'i','me','my','we','us','our','you','ur','your','he','him','his','she','her',
    'it','its','they','them','their',
    'go','get','got','give','gave','take','took','make','made','see','saw',
    'come','came','run','ran','say','said','know','knew','think','thought',
    'feel','felt','want','need','like','love','hate','help','work','play',
    'look','find','keep','let','put','set','try','ask','tell','show','move',
    'back','up','down','out','off','over','under','again','here','there',
    'now','just','also','very','too','more','most','less','only','even',
    'still','already','always','never','often','maybe','really','actually',
    'thank','thanks','sorry','please','hello','hey','hi','bye','yes','yeah',
    'okay','ok','sure','right','wrong','good','bad','cool','nice','great',
    'well','man','bro','dude','mate','guys','omg','wow','lol','lmao',
    'pls','sub','donate','money','free','new','old','big','small','long','short',
    'time','day','life','world','game','wait','stop','done','start','end',
    'alright','aight','sup','wassup','welcome','enjoy','miss','congrats',
    'you','man','your','mine','ours','same','much','many','some','few',
    'every','each','another','other','both',
}


def _is_concatenated_words(lc):
    """
    Greedy left-to-right check: can the token be fully decomposed into
    common English words of length >= 2?
    e.g. 'thanksyouman' -> 'thanks' + 'you' + 'man' -> True
         'Andreiy0021'  -> can't decompose -> False
    """
    n = len(lc)
    # dp[i] = True if lc[:i] can be segmented into common words
    dp = [False] * (n + 1)
    dp[0] = True
    for i in range(1, n + 1):
        for j in range(max(0, i - 18), i):  # max word len ~18
            if dp[j] and lc[j:i] in _COMMON_WORDS and (i - j) >= 2:
                dp[i] = True
                break
    return dp[n]


def _is_spam_token(tok):
    """Return True if the token looks like a spammed/stretched chat word, not a username."""
    # Has 3+ consecutive identical letters: DONOOOOO, YOOOO, WASSAPPP
    if _SPAM_STRETCH.search(tok):
        return True
    # All-caps and longer than 8 chars with no digits/underscore = shouted word
    if tok.isupper() and len(tok) > 8 and tok.isalpha():
        return True
    # More than 45% of characters are the same letter (tightened from 55%)
    if len(tok) >= 5:
        freq = max(tok.lower().count(c) for c in set(tok.lower()) if c.isalpha())
        if freq / len(tok) > 0.45:
            return True
    # All same character repeated (wwwwww, aaaaaaa)
    if len(tok) >= 3 and len(set(tok.lower())) == 1:
        return True
    return False


def extract_roblox_names(text):
    """
    Smart extraction of Roblox usernames from raw chat messages.

    Handles real-world PLS DONATE patterns:
      💲arjuman_cr7💲           -> arjuman_cr7
      ❗❗MegaHunter_Rolex❗❗    -> MegaHunter_Rolex
      22riko8😱😭               -> 22riko8
      "the user: Tovanday_1"   -> Tovanday_1
      "pls hinokami7829 pls me"-> hinokami7829
      Andreiy0021 x15 (spam)   -> Andreiy0021 (deduped)
    Rejects:
      DONOOOOO, YOOOOO, WASSAPPPPP, hellowzzz, ROBUXXX, hiii
      alright, hello, thanksyouman, wwwwwwwwwww
    """
    results = []
    seen = set()

    # Explicit "the user: X" / "user: X" patterns
    for m in re.finditer(r'(?:the\s+)?user[:\s]+([A-Za-z0-9_]{3,20})', text, re.IGNORECASE):
        name = m.group(1).strip('_')
        lc = name.lower()
        if (lc not in seen and _ROBLOX_RE.match(name)
                and lc not in _NOISE and not _is_spam_token(name)
                and not _is_common_english_word(name)):
            seen.add(lc)
            results.append(name)

    # Pre-filter: strip URLs so tokens like "discord", "https", "tiktok.com" are removed
    text = re.sub(r'https?://\S+', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'\S+\.(com|net|org|io|gg|tv|co)\S*', ' ', text, flags=re.IGNORECASE)

    # Strip emojis/symbols but keep alphanumerics, underscores, spaces
    cleaned = re.sub(r'[^\w\s]', ' ', text, flags=re.UNICODE)
    for tok in cleaned.split():
        tok = tok.strip('_')
        if not tok:
            continue
        lc = tok.lower()
        if lc in seen or lc in _NOISE:
            continue
        if not _ROBLOX_RE.match(tok):
            continue
        if tok.isdigit():
            continue
        # Skip very short all-letter tokens (too noisy)
        if len(tok) <= 3 and tok.isalpha():
            continue
        # Skip spammed/stretched tokens
        if _is_spam_token(tok):
            continue
        # Skip plain English words and mashed chat phrases
        if _is_common_english_word(tok):
            continue
        seen.add(lc)
        results.append(tok)

    return results


# ── Data ─────────────────────────────────────────────────────
usernames   = []
deleted_set = set()
banned_set  = {}   # lc -> {'name', 'type': 'ban'|'timeout', 'until': float|None}
messages    = []
data_lock   = threading.Lock()

# ── Roblox API validation ─────────────────────────────────────
# Queue of (name, is_mod, is_member, from_author) waiting for API check
_validate_queue  = queue.Queue()
# Cache: lc -> True (valid) / False (invalid) — avoids re-checking same name
_valid_cache     = {}
_valid_cache_lock = threading.Lock()
# Names currently pending API check (so we don't add them to usernames list yet)
_pending_set     = set()
_pending_lock    = threading.Lock()

# ── HTTP server ───────────────────────────────────────────────
class ChatHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/chat':
            length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(length)
            try:
                msg = json.loads(body)
                if not msg.get('usernames'):
                    msg['usernames'] = extract_roblox_names(msg.get('text', ''))
                with data_lock:
                    messages.append(msg)
                    if len(messages) > 1000:
                        messages.pop(0)
            except:
                pass
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def log_message(self, *args):
        pass

def run_server():
    HTTPServer(('localhost', 7842), ChatHandler).serve_forever()


# ── Roblox batch username validator ──────────────────────────
def _roblox_validate_batch(names):
    """
    POST up to 100 names to Roblox API.
    Returns set of lowercase names that are VALID (exist on Roblox).
    """
    if not names:
        return set()
    try:
        payload = json.dumps({
            "usernames": list(names),
            "excludeBannedUsers": False
        }).encode()
        req = urllib.request.Request(
            "https://users.roblox.com/v1/usernames/users",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read())
        return {entry["requestedUsername"].lower() for entry in data.get("data", [])}
    except Exception:
        return set()


def _validation_worker(app_ref):
    """
    Background thread: drains _validate_queue in batches of up to 100,
    calls Roblox API, then schedules UI updates on the main thread.
    Waits up to 1.5s to accumulate a batch before firing.
    """
    while True:
        batch = {}   # lc -> (original_name, is_mod, is_member, from_author)
        try:
            item = _validate_queue.get(timeout=60)
            name, is_mod, is_member, from_author = item
            lc = name.lower()
            batch[lc] = (name, is_mod, is_member, from_author)
        except queue.Empty:
            continue

        deadline = time.time() + 1.5
        while len(batch) < 100:
            remaining = deadline - time.time()
            if remaining <= 0:
                break
            try:
                item = _validate_queue.get(timeout=remaining)
                name, is_mod, is_member, from_author = item
                lc = name.lower()
                batch[lc] = (name, is_mod, is_member, from_author)
            except queue.Empty:
                break

        to_check = {}
        with _valid_cache_lock:
            for lc, info in batch.items():
                if lc in _valid_cache:
                    if _valid_cache[lc]:
                        name, is_mod, is_member, from_author = info
                        try:
                            app_ref.root.after(0, lambda n=name, m=is_mod, mb=is_member,
                                               fa=from_author: app_ref._confirm_username(n, m, mb, fa))
                        except Exception:
                            pass
                else:
                    to_check[lc] = info

        if not to_check:
            continue

        valid_lcs = _roblox_validate_batch(list(to_check.keys()))

        with _valid_cache_lock:
            for lc in to_check:
                _valid_cache[lc] = (lc in valid_lcs)

        with _pending_lock:
            for lc in to_check:
                _pending_set.discard(lc)

        for lc in to_check:
            name, is_mod, is_member, from_author = to_check[lc]
            if lc in valid_lcs:
                try:
                    app_ref.root.after(0, lambda n=name, m=is_mod, mb=is_member,
                                       fa=from_author: app_ref._confirm_username(n, m, mb, fa))
                except Exception:
                    pass
            else:
                try:
                    app_ref.root.after(0, lambda n=name: app_ref._reject_username(n))
                except Exception:
                    pass

# ── Settings persistence ──────────────────────────────────────
import json as _json, os as _os

_SETTINGS_FILE = _os.path.join(_os.path.expanduser('~'), '.plsdonate_settings.json')

_DEFAULT_SETTINGS = {
    'accent_color':   '#00f0a8',
    'bg_color':       '#080810',
    'surface_color':  '#0f0f1a',
    'text_color':     '#eeeef8',
    'danger_color':   '#ff4d6a',
    'purple_color':   '#b89cff',
    'font_family':    'Consolas',
    'chat_font_size': 9,
    'username_font_size': 9,
    'show_player_icons': True,
    'reduce_lag':     False,
    'chat_autoscroll': True,
    'show_timestamps': True,
    'compact_rows':   False,
    'row_hover_highlight': True,
    'avatar_size':    38,
    'window_opacity': 1.0,
    'username_highlight_donated': True,
}

def _load_settings():
    try:
        with open(_SETTINGS_FILE, 'r') as f:
            d = _json.load(f)
            out = dict(_DEFAULT_SETTINGS)
            out.update(d)
            return out
    except Exception:
        return dict(_DEFAULT_SETTINGS)

def _save_settings(s):
    try:
        with open(_SETTINGS_FILE, 'w') as f:
            _json.dump(s, f, indent=2)
    except Exception:
        pass

_SETTINGS = _load_settings()

# ── Colours ───────────────────────────────────────────────────
def _reload_colors():
    global BG, SURFACE, SURFACE2, SURFACE3, BORDER, BORDER2
    global ACCENT, ACCENT_DIM, ACCENT2, ACCENT3, DANGER, DANGER_DIM
    global TEXT, DIM, MUTED, PURPLE, COPIED_BG, COPIED_FG
    global MOD_COLOR, MEMBER_COLOR, BANNED_BG, SEL_BG, ROW_HOVER
    S = _SETTINGS
    BG           = S.get('bg_color',      '#080810')
    SURFACE      = S.get('surface_color', '#0f0f1a')
    SURFACE2     = '#141420'
    SURFACE3     = '#1c1c2e'
    BORDER       = '#252538'
    BORDER2      = '#32324a'
    ACCENT       = S.get('accent_color',  '#00f0a8')
    ACCENT_DIM   = '#00a372'
    ACCENT2      = '#7c6aff'
    ACCENT3      = '#ffb730'
    DANGER       = S.get('danger_color',  '#ff4d6a')
    DANGER_DIM   = '#7a1826'
    TEXT         = S.get('text_color',    '#eeeef8')
    DIM          = '#707088'
    MUTED        = '#3a3a52'
    PURPLE       = S.get('purple_color',  '#b89cff')
    COPIED_BG    = '#0a1428'
    COPIED_FG    = '#56b4ff'
    MOD_COLOR    = '#ffcc00'
    MEMBER_COLOR = '#d0b4ff'
    BANNED_BG    = '#160810'
    SEL_BG       = '#0a2218'
    ROW_HOVER    = '#1c1c2e'

_reload_colors()

_FONT_OPTIONS = [
    ('Consolas',        'Consolas — Monospace (Default)'),
    ('Courier New',     'Courier New — Classic Mono'),
    ('Lucida Console',  'Lucida Console — Compact'),
    ('Segoe UI',        'Segoe UI — Modern Clean'),
    ('Trebuchet MS',    'Trebuchet MS — Rounded'),
    ('Verdana',         'Verdana — Wide & Clear'),
    ('Arial',           'Arial — Simple Sans'),
    ('Tahoma',          'Tahoma — Tight & Neat'),
    ('Georgia',         'Georgia — Serif Elegant'),
    ('Calibri',         'Calibri — Office Friendly'),
]

# Avatar palette: (circle_bg, text_fg)
_AV_PALETTE = [
    ('#3b1fa8', '#c4b5fd'),  # electric violet
    ('#0f3d6e', '#7dd3fc'),  # deep ocean blue
    ('#064e3b', '#34d399'),  # neon emerald
    ('#7c2d12', '#fb923c'),  # burnt orange
    ('#831843', '#f9a8d4'),  # hot pink
    ('#0e4258', '#22d3ee'),  # neon cyan
    ('#1a4a1a', '#86efac'),  # neon lime
    ('#5b0f0f', '#fca5a5'),  # crimson
    ('#1e1b6e', '#818cf8'),  # indigo glow
    ('#134e4a', '#2dd4bf'),  # teal
    ('#4a3000', '#fbbf24'),  # gold
    ('#3d0a5c', '#e879f9'),  # fuchsia neon
    ('#003333', '#00f0a8'),  # mint
    ('#2a0a0a', '#ff6b8a'),  # rose
]

def _av_colors(name):
    h = sum(ord(c) * (i + 1) for i, c in enumerate(name.lower()))
    return _AV_PALETTE[h % len(_AV_PALETTE)]

def _initials(name):
    """2-char initials smart-extracted from Roblox username."""
    name = name.strip('_')
    parts = re.split(r'[_]', name)
    parts = [p for p in parts if p and p[0].isalpha()]
    if len(parts) >= 2:
        return (parts[0][0] + parts[1][0]).upper()
    alpha = [c for c in name if c.isalpha()]
    if len(alpha) >= 2:
        return (alpha[0] + alpha[1]).upper()
    return (name[0] + (name[1] if len(name) > 1 else '')).upper()


# ── App ───────────────────────────────────────────────────────
class App:
    def __init__(self, root):
        self.root = root
        self.root.title('PLS DONATE Tracker')
        self.root.geometry('420x720')
        self.root.minsize(320, 200)
        self.root.configure(bg=BG)
        self.root.resizable(True, True)
        self.always_on_top = True
        self.root.attributes('-topmost', True)

        self.last_msg_index  = 0
        self.username_frames = {}
        self.username_labels = {}
        self.username_colors = {}
        self.selected        = set()
        self.copied_set      = set()
        self.dup_count       = 0
        self.msg_count       = 0
        self.username_count  = 0
        self._hwnd           = None
        self._toast_after    = None
        self.pending_frames  = {}
        self.pending_labels  = {}

        self.build_ui()
        self.poll_messages()

    # ── WinAPI ───────────────────────────────────────────────
    def _get_hwnd(self):
        if not self._hwnd:
            try:
                self._hwnd = self.root.winfo_id() or None
            except Exception:
                pass
        return self._hwnd

    def set_always_on_top(self, on):
        self.root.attributes('-topmost', on)
        try:
            hwnd = self._get_hwnd()
            if hwnd:
                ctypes.windll.user32.SetWindowPos(
                    hwnd, -1 if on else -2, 0, 0, 0, 0, 0x0013)
        except Exception:
            pass

    # ── Build UI ─────────────────────────────────────────────
    def build_ui(self):
        topbar = tk.Frame(self.root, bg=SURFACE, height=40)
        topbar.pack(fill='x', side='top')
        topbar.pack_propagate(False)

        tk.Frame(topbar, bg=ACCENT, width=4).pack(side='left', fill='y')

        logo_frame = tk.Frame(topbar, bg=SURFACE)
        logo_frame.pack(side='left', padx=(8, 3), pady=4)
        tk.Label(logo_frame, text='PLS', bg=SURFACE, fg=ACCENT,
                 font=('Consolas', 11, 'bold')).pack(side='left')
        tk.Label(logo_frame, text='/', bg=SURFACE, fg=MUTED,
                 font=('Consolas', 10)).pack(side='left')
        tk.Label(logo_frame, text='DONATE', bg=SURFACE, fg=TEXT,
                 font=('Consolas', 11, 'bold')).pack(side='left')

        tk.Frame(topbar, bg=BORDER, width=1).pack(side='left', fill='y', padx=5, pady=8)

        self.pill_var = tk.StringVar(value='⬤  WAITING')
        self.pill_lbl = tk.Label(topbar, textvariable=self.pill_var,
                                  bg=SURFACE, fg=ACCENT3,
                                  font=('Consolas', 7, 'bold'),
                                  padx=5, pady=2)
        self.pill_lbl.pack(side='left', padx=1)

        bf = tk.Frame(topbar, bg=SURFACE)
        bf.pack(side='right', padx=6)
        self.pin_btn = tk.Button(bf, text='📌', bg=SURFACE2, fg=ACCENT3,
                                  font=('Consolas', 8), relief='flat', bd=0,
                                  cursor='hand2', activebackground=BORDER,
                                  activeforeground=ACCENT3, padx=5, pady=2,
                                  command=self.toggle_pin)
        self.pin_btn.pack(side='left', padx=1)
        self._mkbtn(bf, '↩', PURPLE, self.restore_deleted).pack(side='left', padx=1)
        self._mkbtn(bf, '⟳', DANGER, self.reset_session).pack(side='left', padx=1)
        self._mkbtn(bf, '⧉ All', ACCENT, self.copy_all).pack(side='left', padx=1)

        tk.Frame(self.root, bg=ACCENT, height=1).pack(fill='x')
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill='x')

        self.banner = tk.Label(self.root,
            text='⚠  Open YouTube chat  →  Popout chat  →  auto-reads',
            bg='#141008', fg=ACCENT3, font=('Consolas', 7), pady=4)
        self.banner.pack(fill='x')

        tab_bar = tk.Frame(self.root, bg=SURFACE, height=34)
        tab_bar.pack(fill='x')
        tab_bar.pack_propagate(False)
        self.tab_btns = {}
        for tid, lbl in [('tracker', '  👤  Tracker  '), ('ban', '  🔨  Ban List  '), ('settings', '  ⚙  Settings  '), ('credits', '  ✨  Credits  ')]:
            b = tk.Button(tab_bar, text=lbl,
                          bg=BG      if tid == 'tracker' else SURFACE,
                          fg=ACCENT  if tid == 'tracker' else DIM,
                          font=('Consolas', 8, 'bold'), relief='flat', bd=0,
                          cursor='hand2', pady=6,
                          activebackground=BG, activeforeground=ACCENT,
                          command=lambda t=tid: self.switch_tab(t))
            b.pack(side='left')
            self.tab_btns[tid] = b
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill='x')

        self.page_frame = tk.Frame(self.root, bg=BG)
        self.page_frame.pack(fill='both', expand=True)
        self.pages = {}
        self._build_tracker_page()
        self._build_ban_page()
        self._build_settings_page()
        self._build_credits_page()
        self.switch_tab('tracker')

        tk.Frame(self.root, bg=BORDER, height=1).pack(fill='x', side='bottom')
        stats = tk.Frame(self.root, bg=SURFACE, height=24)
        stats.pack(fill='x', side='bottom')
        stats.pack_propagate(False)
        self.stat_vars = {}
        tk.Frame(stats, bg=ACCENT2, width=3).pack(side='left', fill='y')
        for key, label, col in [
            ('total',   'Users',    ACCENT),
            ('deleted', 'Del',      DIM),
            ('dups',    'Dups',     DIM),
            ('msgs',    'Msgs',     PURPLE),
            ('banned',  'Ban',      DANGER),
        ]:
            sep = tk.Frame(stats, bg=BORDER, width=1)
            sep.pack(side='left', fill='y', pady=6, padx=6)
            v = tk.StringVar(value='0')
            self.stat_vars[key] = v
            tk.Label(stats, textvariable=v, bg=SURFACE, fg=col,
                     font=('Consolas', 8, 'bold')).pack(side='left', padx=(0, 2))
            tk.Label(stats, text=label, bg=SURFACE, fg=MUTED,
                     font=('Consolas', 7)).pack(side='left', padx=(0, 4))
        self.status_lbl = tk.Label(stats, text='Waiting for chat...', bg=SURFACE,
                                    fg=MUTED, font=('Consolas', 7))
        self.status_lbl.pack(side='right', padx=12)

        self.toast_lbl = tk.Label(self.root, text='', bg=SURFACE3, fg=ACCENT,
                                   font=('Consolas', 9, 'bold'), relief='flat', bd=0,
                                   padx=14, pady=6)

    def _build_tracker_page(self):
        page = tk.Frame(self.page_frame, bg=BG)
        self.pages['tracker'] = page

        # ── Toolbar row 1: select + actions ──
        toolbar = tk.Frame(page, bg=SURFACE2, height=30)
        toolbar.pack(fill='x', side='top')
        toolbar.pack_propagate(False)
        tk.Frame(toolbar, bg=BORDER, width=1).pack(side='left', fill='y', pady=3)
        tk.Label(toolbar, text='SEL:', bg=SURFACE2, fg=MUTED,
                 font=('Consolas', 7)).pack(side='left', padx=(6, 1))
        self._mktool(toolbar, 'All',  self.select_all).pack(side='left', padx=1, pady=3)
        self._mktool(toolbar, 'None', self.deselect_all).pack(side='left', padx=1, pady=3)
        tk.Frame(toolbar, bg=BORDER, width=1).pack(side='left', fill='y', pady=4, padx=4)
        self._mktool(toolbar, '⧉ Copy Sel', self.copy_selected, fg=ACCENT).pack(side='left', padx=1, pady=3)
        self._mktool(toolbar, '🗑 Del Sel',  self.delete_selected, fg=DANGER).pack(side='left', padx=1, pady=3)
        self._mktool(toolbar, '🗑 Del ALL',  self.delete_all,      fg=DANGER).pack(side='left', padx=1, pady=3)

        # ── Toolbar row 2: view toggles ──
        toolbar2 = tk.Frame(page, bg=SURFACE3, height=28)
        toolbar2.pack(fill='x', side='top')
        toolbar2.pack_propagate(False)
        tk.Label(toolbar2, text=' VIEW:', bg=SURFACE3, fg=MUTED,
                 font=('Consolas', 7)).pack(side='left', padx=(6, 2))
        self.users_toggle_btn = self._mktool(
            toolbar2, '👤 Hide Users', self.toggle_users_panel, fg=ACCENT)
        self.users_toggle_btn.pack(side='left', padx=2, pady=2)
        self.chat_toggle_btn = self._mktool(
            toolbar2, '💬 Hide Chat', self.toggle_chat_panel, fg=PURPLE)
        self.chat_toggle_btn.pack(side='left', padx=2, pady=2)

        # Layout mode toggle (thin vs wide)
        self._layout_mode = 'thin'  # 'thin' = vertical stack, 'wide' = side by side
        self.layout_mode_btn = self._mktool(
            toolbar2, '⇔ Wide', self.toggle_layout_mode, fg=ACCENT3)
        self.layout_mode_btn.pack(side='right', padx=6, pady=2)

        tk.Frame(page, bg=BORDER, height=1).pack(fill='x')

        # ── Main vertical split area ──────────────────────────
        self._users_panel_visible = True
        self._chat_panel_visible  = True

        main = tk.Frame(page, bg=BG)
        main.pack(fill='both', expand=True)
        self._main_frame = main

        # ── Top panel (usernames) ─────────────────────────────
        left = tk.Frame(main, bg=BG)
        self.left_panel = left
        left.pack(side='top', fill='both', expand=True)

        lh = tk.Frame(left, bg=SURFACE, height=36)
        lh.pack(fill='x')
        lh.pack_propagate(False)
        tk.Frame(lh, bg=ACCENT, width=3).pack(side='left', fill='y')
        tk.Label(lh, text=' USERNAMES', bg=SURFACE, fg=ACCENT,
                 font=('Consolas', 9, 'bold')).pack(side='left', padx=(8, 4))
        self.u_count_lbl = tk.Label(lh, text='0', bg='#0a2218', fg=ACCENT,
                                     font=('Consolas', 8, 'bold'), padx=6, pady=1)
        self.u_count_lbl.pack(side='left')
        # Legend on right of header
        leg = tk.Frame(lh, bg=SURFACE)
        leg.pack(side='right', padx=10)
        for sym, col, label in [('🔨', MOD_COLOR, 'mod'), ('★', MEMBER_COLOR, 'mbr'), ('✔', COPIED_FG, 'copied')]:
            tk.Label(leg, text=sym, bg=SURFACE, fg=col, font=('Consolas', 8)).pack(side='left')
            tk.Label(leg, text=label, bg=SURFACE, fg=MUTED, font=('Consolas', 7)).pack(side='left', padx=(0, 6))

        tk.Frame(left, bg=BORDER, height=1).pack(fill='x')

        uc = tk.Frame(left, bg=BG)
        uc.pack(fill='both', expand=True)
        self.u_scroll = tk.Scrollbar(uc, bg=SURFACE2, troughcolor=BG,
                                      activebackground=BORDER, relief='flat', width=6)
        self.u_scroll.pack(side='right', fill='y')
        self.u_canvas = tk.Canvas(uc, bg=BG, highlightthickness=0,
                                   yscrollcommand=self.u_scroll.set)
        self.u_canvas.pack(side='left', fill='both', expand=True)
        self.u_scroll.config(command=self.u_canvas.yview)
        self.u_list_frame = tk.Frame(self.u_canvas, bg=BG)
        self.u_cwin = self.u_canvas.create_window((0, 0), window=self.u_list_frame, anchor='nw')
        self.u_list_frame.bind('<Configure>',
            lambda e: self.u_canvas.configure(scrollregion=self.u_canvas.bbox('all')))
        self.u_canvas.bind('<Configure>',
            lambda e: self.u_canvas.itemconfig(self.u_cwin, width=e.width))
        self.u_canvas.bind('<MouseWheel>',
            lambda e: self.u_canvas.yview_scroll(-1*(e.delta//120), 'units'))
        self.u_list_frame.bind('<MouseWheel>',
            lambda e: self.u_canvas.yview_scroll(-1*(e.delta//120), 'units'))

        self.u_empty_lbl = tk.Label(self.u_list_frame,
            text='\n👤\n\nUsernames from chat\nappear here automatically',
            bg=BG, fg=MUTED, font=('Consolas', 9), justify='center')
        self.u_empty_lbl.pack(pady=40)

        # Divider between panels — orientation depends on layout mode
        self._users_divider = tk.Frame(main, bg=BORDER, height=1)
        self._users_divider.pack(side='top', fill='x')

        # ── Bottom/right panel (live chat) ────────────────────
        right = tk.Frame(main, bg=BG)
        self.right_panel = right
        right.pack(side='top', fill='both', expand=True)

        rh = tk.Frame(right, bg=SURFACE, height=36)
        rh.pack(fill='x')
        rh.pack_propagate(False)
        tk.Frame(rh, bg=PURPLE, width=3).pack(side='left', fill='y')
        tk.Label(rh, text=' LIVE CHAT', bg=SURFACE, fg=PURPLE,
                 font=('Consolas', 9, 'bold')).pack(side='left', padx=(8, 4))
        self.c_count_lbl = tk.Label(rh, text='0', bg='#110a28', fg=PURPLE,
                                     font=('Consolas', 8, 'bold'), padx=6, pady=1)
        self.c_count_lbl.pack(side='left')
        self._mktool(rh, 'Clear', self.clear_chat, fg=MUTED).pack(side='right', padx=8, pady=4)

        tk.Frame(right, bg=BORDER, height=1).pack(fill='x')
        cc = tk.Frame(right, bg=BG)
        cc.pack(fill='both', expand=True)
        self.c_scroll = tk.Scrollbar(cc, bg=SURFACE2, troughcolor=BG,
                                      activebackground=BORDER, relief='flat', width=6)
        self.c_scroll.pack(side='right', fill='y')
        self.c_text = tk.Text(cc, bg=BG, fg=DIM, font=('Consolas', 9),
                               relief='flat', bd=0, wrap='word', state='disabled',
                               yscrollcommand=self.c_scroll.set, cursor='arrow',
                               selectbackground=SURFACE3, padx=6, pady=4)
        self.c_text.pack(side='left', fill='both', expand=True)
        self.c_scroll.config(command=self.c_text.yview)
        self.c_text.tag_config('author',        foreground=ACCENT3,      font=('Consolas', 8, 'bold'))
        self.c_text.tag_config('author_mod',    foreground=MOD_COLOR,    font=('Consolas', 8, 'bold'))
        self.c_text.tag_config('author_member', foreground=MEMBER_COLOR, font=('Consolas', 8, 'bold'))
        self.c_text.tag_config('time',          foreground=MUTED,        font=('Consolas', 7))
        self.c_text.tag_config('time_mod',      foreground='#7a5c00',    font=('Consolas', 7))
        self.c_text.tag_config('time_member',   foreground='#5a3d7a',    font=('Consolas', 7))
        self.c_text.tag_config('hl',            foreground=ACCENT,       font=('Consolas', 9, 'bold'),
                                                background='#062014')
        self.c_text.tag_config('msg',           foreground=DIM,          font=('Consolas', 9))
        self.c_text.tag_config('msg_mod',       foreground='#b08a30',    font=('Consolas', 9))
        self.c_text.tag_config('msg_member',    foreground='#8a6ab0',    font=('Consolas', 9))
        self.c_text.tag_config('badge_mod',     foreground='#3d2000',    background=MOD_COLOR,
                                                font=('Consolas', 6, 'bold'))
        self.c_text.tag_config('badge_member',  foreground='#1a0840',    background=MEMBER_COLOR,
                                                font=('Consolas', 6, 'bold'))
        self.c_text.bind('<MouseWheel>',
            lambda e: self.c_text.yview_scroll(-1*(e.delta//120), 'units'))

    def _build_ban_page(self):
        page = tk.Frame(self.page_frame, bg=BG)
        self.pages['ban'] = page

        bh = tk.Frame(page, bg=SURFACE, height=38)
        bh.pack(fill='x')
        bh.pack_propagate(False)
        tk.Frame(bh, bg=DANGER, width=3).pack(side='left', fill='y')
        tk.Label(bh, text=' BANNED / TIMED OUT', bg=SURFACE, fg=DANGER,
                 font=('Consolas', 9, 'bold')).pack(side='left', padx=(8,3), pady=6)
        self.ban_count_lbl = tk.Label(bh, text='0', bg=DANGER_DIM, fg=DANGER,
                                       font=('Consolas', 8, 'bold'), padx=6, pady=1)
        self.ban_count_lbl.pack(side='left', padx=2)
        self._mksmall(bh, 'Clear All', self.clear_bans, fg=DANGER).pack(side='right', padx=8, pady=4)
        tk.Frame(page, bg=BORDER, height=1).pack(fill='x')

        af = tk.Frame(page, bg=SURFACE2, pady=8)
        af.pack(fill='x')
        tk.Label(af, text='Username:', bg=SURFACE2, fg=DIM,
                 font=('Consolas', 8)).pack(side='left', padx=(12,4))
        self.ban_entry = tk.Entry(af, bg=SURFACE, fg=TEXT, insertbackground=TEXT,
                                   font=('Consolas', 9), relief='flat', width=20,
                                   highlightthickness=1, highlightbackground=BORDER,
                                   highlightcolor=ACCENT)
        self.ban_entry.pack(side='left', padx=4, ipady=3)
        self.ban_entry.bind('<Return>', lambda e: self.add_ban())
        tk.Label(af, text='Type:', bg=SURFACE2, fg=DIM,
                 font=('Consolas', 8)).pack(side='left', padx=(10,4))
        self.ban_type_var = tk.StringVar(value='ban')
        for val, col in [('ban','Ban'), ('timeout','Timeout')]:
            tk.Radiobutton(af, text=col, variable=self.ban_type_var, value=val,
                           bg=SURFACE2, fg=DANGER if val=='ban' else ACCENT3,
                           selectcolor=SURFACE, activebackground=SURFACE2,
                           font=('Consolas', 8),
                           command=self._toggle_timeout_entry).pack(side='left', padx=2)
        self.timeout_frame = tk.Frame(af, bg=SURFACE2)
        self.timeout_frame.pack(side='left', padx=4)
        tk.Label(self.timeout_frame, text='mins:', bg=SURFACE2, fg=DIM,
                 font=('Consolas', 8)).pack(side='left', padx=2)
        self.timeout_entry = tk.Entry(self.timeout_frame, bg=SURFACE, fg=TEXT,
                                       insertbackground=TEXT, font=('Consolas', 9),
                                       relief='flat', width=5,
                                       highlightthickness=1, highlightbackground=BORDER,
                                       highlightcolor=ACCENT)
        self.timeout_entry.insert(0, '10')
        self.timeout_entry.pack(side='left', ipady=3)
        self.timeout_frame.pack_forget()
        self._mkbtn(af, '+ Add', DANGER, self.add_ban).pack(side='left', padx=10)
        tk.Frame(page, bg=BORDER, height=1).pack(fill='x')

        bc = tk.Frame(page, bg=BG)
        bc.pack(fill='both', expand=True)
        bscroll = tk.Scrollbar(bc, bg=SURFACE2, troughcolor=BG,
                                activebackground=BORDER, relief='flat', width=6)
        bscroll.pack(side='right', fill='y')
        self.ban_canvas = tk.Canvas(bc, bg=BG, highlightthickness=0,
                                     yscrollcommand=bscroll.set)
        self.ban_canvas.pack(side='left', fill='both', expand=True)
        bscroll.config(command=self.ban_canvas.yview)
        self.ban_list_frame = tk.Frame(self.ban_canvas, bg=BG)
        self.ban_cwin = self.ban_canvas.create_window(
            (0,0), window=self.ban_list_frame, anchor='nw')
        self.ban_list_frame.bind('<Configure>',
            lambda e: self.ban_canvas.configure(scrollregion=self.ban_canvas.bbox('all')))
        self.ban_canvas.bind('<Configure>',
            lambda e: self.ban_canvas.itemconfig(self.ban_cwin, width=e.width))
        self.ban_canvas.bind('<MouseWheel>',
            lambda e: self.ban_canvas.yview_scroll(-1*(e.delta//120), 'units'))
        self.ban_empty_lbl = tk.Label(self.ban_list_frame,
            text='\n🔨\n\nNo banned users\nAdd usernames above to block them',
            bg=BG, fg=MUTED, font=('Consolas', 9), justify='center')
        self.ban_empty_lbl.pack(pady=40)
        self.ban_frames = {}

    # ── Settings page ─────────────────────────────────────────
    def _build_settings_page(self):
        import tkinter.colorchooser as cc
        page = tk.Frame(self.page_frame, bg=BG)
        self.pages['settings'] = page

        # scrollable container
        canvas = tk.Canvas(page, bg=BG, highlightthickness=0)
        scr = tk.Scrollbar(page, bg=SURFACE2, troughcolor=BG,
                           activebackground=BORDER, relief='flat', width=6,
                           command=canvas.yview)
        canvas.configure(yscrollcommand=scr.set)
        scr.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        inner = tk.Frame(canvas, bg=BG)
        cwin = canvas.create_window((0, 0), window=inner, anchor='nw')
        canvas.bind('<Configure>', lambda e: canvas.itemconfig(cwin, width=e.width))

        def _scroll_settings(e):
            canvas.yview_scroll(-1 * (e.delta // 120), 'units')

        def _bind_all_scroll(widget):
            try:
                widget.bind('<MouseWheel>', _scroll_settings)
            except Exception:
                pass
            for child in widget.winfo_children():
                _bind_all_scroll(child)

        canvas.bind('<MouseWheel>', _scroll_settings)

        def _on_inner_resize(e):
            canvas.configure(scrollregion=canvas.bbox('all'))
            _bind_all_scroll(inner)

        inner.bind('<Configure>', _on_inner_resize)

        S = _SETTINGS  # live reference

        def _gap(h=10):
            tk.Frame(inner, bg=BG, height=h).pack(fill='x')

        def _section(title, color=ACCENT, icon=''):
            f = tk.Frame(inner, bg=SURFACE)
            f.pack(fill='x', padx=14, pady=(12, 2))
            tk.Frame(f, bg=color, width=3).pack(side='left', fill='y')
            tk.Label(f, text=f'  {icon}  {title}' if icon else f'  {title}',
                     bg=SURFACE, fg=color, font=('Consolas', 9, 'bold'), pady=7).pack(side='left')

        def _card(parent=inner):
            outer = tk.Frame(parent, bg=BORDER2, padx=1, pady=1)
            outer.pack(fill='x', padx=14, pady=2)
            card = tk.Frame(outer, bg=SURFACE3)
            card.pack(fill='both', expand=True)
            body = tk.Frame(card, bg=SURFACE3)
            body.pack(fill='both', expand=True, padx=14, pady=10)
            return body

        def _row(parent, label, widget_fn):
            r = tk.Frame(parent, bg=SURFACE3)
            r.pack(fill='x', pady=3)
            tk.Label(r, text=label, bg=SURFACE3, fg=TEXT,
                     font=(_SETTINGS.get('font_family','Consolas'), 8), width=26, anchor='w').pack(side='left')
            widget_fn(r)
            return r

        # ─── HEADER ──────────────────────────────────────────────
        hero = tk.Frame(inner, bg=SURFACE2)
        hero.pack(fill='x')
        tk.Frame(hero, bg=ACCENT, height=3).pack(fill='x')
        tk.Label(hero, text='⚙  SETTINGS & CUSTOMIZATION', bg=SURFACE2, fg=ACCENT,
                 font=('Consolas', 11, 'bold'), pady=12).pack()
        tk.Label(hero, text='Personalise your tracker — changes apply live',
                 bg=SURFACE2, fg=DIM, font=('Consolas', 8), pady=2).pack()
        tk.Frame(hero, bg=ACCENT2, height=2).pack(fill='x')

        _gap(4)

        # ─── COLOUR CUSTOMIZATION ────────────────────────────────
        _section('COLOURS', ACCENT, '🎨')

        _colour_swatches = {}  # key -> Label widget showing current colour

        def _colour_row(parent, label, key):
            r = tk.Frame(parent, bg=SURFACE3)
            r.pack(fill='x', pady=4)
            tk.Label(r, text=label, bg=SURFACE3, fg=TEXT,
                     font=('Consolas', 8), width=28, anchor='w').pack(side='left')
            swatch = tk.Label(r, text='  ██  ', bg=S.get(key, '#ffffff'),
                               fg=S.get(key, '#ffffff'), font=('Consolas', 9),
                               relief='flat', cursor='hand2', padx=4, pady=3)
            swatch.pack(side='left', padx=(0, 8))
            val_lbl = tk.Label(r, text=S.get(key, '#ffffff'), bg=SURFACE3, fg=DIM,
                                font=('Consolas', 8))
            val_lbl.pack(side='left')
            _colour_swatches[key] = (swatch, val_lbl)

            def pick(k=key, sw=swatch, vl=val_lbl):
                import tkinter.colorchooser as _cc
                cur = S.get(k, '#080810')
                result = _cc.askcolor(color=cur, title=f'Pick colour — {k}')
                if result and result[1]:
                    hexc = result[1]
                    S[k] = hexc
                    sw.config(bg=hexc, fg=hexc)
                    vl.config(text=hexc)
                    _save_settings(S)
                    self.show_toast(f'🎨 {label} → {hexc}  (restart to apply fully)')

            swatch.bind('<Button-1>', lambda e, fn=pick: fn())
            return r

        colour_card = _card()
        _colour_row(colour_card, 'Accent / Highlight',   'accent_color')
        _colour_row(colour_card, 'Background',            'bg_color')
        _colour_row(colour_card, 'Surface / Panels',      'surface_color')
        _colour_row(colour_card, 'Text',                  'text_color')
        _colour_row(colour_card, 'Danger / Bans',         'danger_color')
        _colour_row(colour_card, 'Purple / Chat',         'purple_color')

        tk.Label(colour_card,
                 text='💡 Click any colour swatch to open the colour wheel picker',
                 bg=SURFACE3, fg=MUTED, font=('Consolas', 7), pady=3).pack(anchor='w')

        def _reset_colours():
            for key in ('accent_color','bg_color','surface_color','text_color','danger_color','purple_color'):
                S[key] = _DEFAULT_SETTINGS[key]
                sw, vl = _colour_swatches[key]
                sw.config(bg=S[key], fg=S[key])
                vl.config(text=S[key])
            _save_settings(S)
            self.show_toast('🎨 Colours reset to defaults — restart to apply')

        tk.Button(colour_card, text='↩  Reset Colours to Default',
                  bg=SURFACE2, fg=MUTED, font=('Consolas', 8), relief='flat', bd=0,
                  cursor='hand2', activebackground=BORDER2, activeforeground=TEXT,
                  padx=8, pady=4, command=_reset_colours).pack(anchor='w', pady=(6, 0))

        _gap(4)

        # ─── FONT SETTINGS ───────────────────────────────────────
        _section('FONTS', ACCENT2, '🔤')
        font_card = _card()

        # Font family picker
        font_lbl_row = tk.Frame(font_card, bg=SURFACE3)
        font_lbl_row.pack(fill='x', pady=4)
        tk.Label(font_lbl_row, text='Font Family', bg=SURFACE3, fg=TEXT,
                 font=('Consolas', 8), width=20, anchor='w').pack(side='left')

        self._font_var = tk.StringVar(value=S.get('font_family', 'Consolas'))
        font_preview = tk.Label(font_card, text='AaBbCc  123  PLS DONATE',
                                 bg=SURFACE2, fg=ACCENT, pady=6,
                                 font=(S.get('font_family','Consolas'), 11, 'bold'))
        font_preview.pack(fill='x', pady=(0, 6))

        def _set_font(fam):
            S['font_family'] = fam
            self._font_var.set(fam)
            font_preview.config(font=(fam, 11, 'bold'))
            _save_settings(S)
            self.show_toast(f'🔤 Font → {fam}  (restart to apply fully)')

        for fam, desc in _FONT_OPTIONS:
            fr = tk.Frame(font_card, bg=SURFACE3, cursor='hand2')
            fr.pack(fill='x', pady=1)
            rb = tk.Radiobutton(fr, text='', variable=self._font_var, value=fam,
                                bg=SURFACE3, fg=ACCENT, selectcolor=BG,
                                activebackground=SURFACE3, command=lambda f=fam: _set_font(f))
            rb.pack(side='left')
            name_lbl = tk.Label(fr, text=fam, bg=SURFACE3, fg=TEXT,
                                 font=(fam, 9, 'bold'), width=16, anchor='w')
            name_lbl.pack(side='left')
            tk.Label(fr, text=desc.split('—')[1].strip() if '—' in desc else '',
                     bg=SURFACE3, fg=DIM, font=('Consolas', 7)).pack(side='left', padx=4)
            fr.bind('<Button-1>', lambda e, f=fam: _set_font(f))
            name_lbl.bind('<Button-1>', lambda e, f=fam: _set_font(f))

        _gap(6)

        # Font size sliders
        size_row = tk.Frame(font_card, bg=SURFACE3)
        size_row.pack(fill='x', pady=6)
        for label, key, lo, hi in [
            ('Chat font size',     'chat_font_size',     7, 14),
            ('Username font size', 'username_font_size', 7, 14),
        ]:
            sr = tk.Frame(size_row, bg=SURFACE3)
            sr.pack(side='left', expand=True, fill='x', padx=6)
            tk.Label(sr, text=label, bg=SURFACE3, fg=TEXT,
                     font=('Consolas', 7)).pack(anchor='w')
            size_val = tk.Label(sr, text=str(S.get(key, 9)), bg=SURFACE3, fg=ACCENT,
                                 font=('Consolas', 9, 'bold'))
            size_val.pack(anchor='w')
            def _make_size_handler(k, vl):
                def handler(v):
                    S[k] = int(float(v))
                    vl.config(text=str(S[k]))
                    _save_settings(S)
                return handler
            sl = tk.Scale(sr, from_=lo, to=hi, orient='horizontal',
                          bg=SURFACE3, fg=DIM, troughcolor=SURFACE2,
                          highlightthickness=0, relief='flat', sliderlength=14,
                          command=_make_size_handler(key, size_val))
            sl.set(S.get(key, 9))
            sl.pack(fill='x')

        _gap(4)

        # ─── CHAT APPEARANCE ─────────────────────────────────────
        _section('LIVE CHAT APPEARANCE', PURPLE, '💬')
        chat_card = _card()

        _toggle_vars = {}

        def _toggle_row(parent, label, key, desc=''):
            var = tk.BooleanVar(value=bool(S.get(key, True)))
            _toggle_vars[key] = var
            r = tk.Frame(parent, bg=SURFACE3)
            r.pack(fill='x', pady=3)
            def _on_toggle(k=key, v=var):
                S[k] = v.get()
                _save_settings(S)
                self.show_toast(f'{"✅" if v.get() else "❌"} {label} — {"ON" if v.get() else "OFF"}')
            cb = tk.Checkbutton(r, text=label, variable=var, bg=SURFACE3, fg=TEXT,
                                 selectcolor=BG, activebackground=SURFACE3,
                                 activeforeground=ACCENT, font=('Consolas', 8),
                                 cursor='hand2', command=_on_toggle)
            cb.pack(side='left')
            if desc:
                tk.Label(r, text=desc, bg=SURFACE3, fg=MUTED, font=('Consolas', 7)).pack(side='left', padx=6)

        _toggle_row(chat_card, 'Show Player Icons (Avatars)',     'show_player_icons',
                    '— initials avatar beside each message')
        _toggle_row(chat_card, 'Auto-scroll to latest message',   'chat_autoscroll',
                    '— keeps chat pinned to bottom')
        _toggle_row(chat_card, 'Show message timestamps',         'show_timestamps',
                    '— HH:MM beside each chat line')
        _toggle_row(chat_card, 'Highlight detected usernames',    'username_highlight_donated',
                    '— bright highlight on matched names')

        _gap(4)

        # ─── USERNAME LIST APPEARANCE ────────────────────────────
        _section('USERNAME LIST APPEARANCE', ACCENT3, '👤')
        user_card = _card()

        _toggle_row(user_card, 'Compact rows (smaller padding)',   'compact_rows',
                    '— fit more users on screen')
        _toggle_row(user_card, 'Row hover highlight',              'row_hover_highlight',
                    '— glow when hovering a username row')

        _gap(4)

        # Avatar size slider
        av_row = tk.Frame(user_card, bg=SURFACE3)
        av_row.pack(fill='x', pady=6)
        tk.Label(av_row, text='Avatar / Icon size', bg=SURFACE3, fg=TEXT,
                 font=('Consolas', 8)).pack(side='left', padx=(0, 8))
        av_val = tk.Label(av_row, text=str(S.get('avatar_size', 38))+'px',
                           bg=SURFACE3, fg=ACCENT, font=('Consolas', 8, 'bold'))
        av_val.pack(side='left')
        def _av_handler(v):
            S['avatar_size'] = int(float(v))
            av_val.config(text=f'{S["avatar_size"]}px')
            _save_settings(S)
        av_sl = tk.Scale(user_card, from_=24, to=56, orient='horizontal',
                          bg=SURFACE3, fg=DIM, troughcolor=SURFACE2,
                          highlightthickness=0, relief='flat', sliderlength=14,
                          command=_av_handler)
        av_sl.set(S.get('avatar_size', 38))
        av_sl.pack(fill='x', pady=(2, 0))
        tk.Label(user_card, text='Controls the circular icon size shown next to usernames',
                 bg=SURFACE3, fg=MUTED, font=('Consolas', 7)).pack(anchor='w')

        _gap(4)

        # ─── WINDOW & PERFORMANCE ────────────────────────────────
        _section('WINDOW & PERFORMANCE', DANGER, '⚡')
        perf_card = _card()

        # Opacity slider
        op_lbl_r = tk.Frame(perf_card, bg=SURFACE3)
        op_lbl_r.pack(fill='x', pady=3)
        tk.Label(op_lbl_r, text='Window Opacity', bg=SURFACE3, fg=TEXT,
                 font=('Consolas', 8), width=20, anchor='w').pack(side='left')
        op_val_lbl = tk.Label(op_lbl_r, text=f'{int(S.get("window_opacity",1.0)*100)}%',
                               bg=SURFACE3, fg=ACCENT, font=('Consolas', 8, 'bold'))
        op_val_lbl.pack(side='left')
        def _op_handler(v):
            val = round(float(v) / 100, 2)
            S['window_opacity'] = val
            op_val_lbl.config(text=f'{int(val*100)}%')
            try: self.root.attributes('-alpha', val)
            except: pass
            _save_settings(S)
        op_sl = tk.Scale(perf_card, from_=30, to=100, orient='horizontal',
                          bg=SURFACE3, fg=DIM, troughcolor=SURFACE2,
                          highlightthickness=0, relief='flat', sliderlength=14,
                          command=_op_handler)
        op_sl.set(int(S.get('window_opacity', 1.0) * 100))
        op_sl.pack(fill='x', pady=(0, 6))

        # Reduce lag toggle
        lag_var = tk.BooleanVar(value=bool(S.get('reduce_lag', False)))
        _toggle_vars['reduce_lag'] = lag_var
        lag_frame = tk.Frame(perf_card, bg='#1a0a0a', relief='flat', bd=0)
        lag_frame.pack(fill='x', pady=4)
        tk.Frame(lag_frame, bg=DANGER, width=3).pack(side='left', fill='y')
        lag_body = tk.Frame(lag_frame, bg='#1a0a0a')
        lag_body.pack(side='left', fill='x', padx=10, pady=8)
        def _on_lag_toggle():
            S['reduce_lag'] = lag_var.get()
            _save_settings(S)
            if lag_var.get():
                self.show_toast('⚡ Reduce Lag ON — minimal animations, faster polling')
            else:
                self.show_toast('⚡ Reduce Lag OFF — full visual experience')
        tk.Checkbutton(lag_body, text='⚡  REDUCE LAG MODE',
                        variable=lag_var, bg='#1a0a0a', fg=DANGER,
                        selectcolor='#0a0505', activebackground='#1a0a0a',
                        activeforeground=DANGER, font=('Consolas', 9, 'bold'),
                        cursor='hand2', command=_on_lag_toggle).pack(anchor='w')
        tk.Label(lag_body,
                 text='Disables hover effects, reduces UI redraws and\n'
                      'animation overhead. Best for low-end PCs during streams.',
                 bg='#1a0a0a', fg='#b04040', font=('Consolas', 7), justify='left').pack(anchor='w')

        _gap(4)

        # ─── APPLY / SAVE ─────────────────────────────────────────
        _section('SAVE SETTINGS', ACCENT, '💾')
        save_card = _card()

        def _apply_and_save():
            _save_settings(S)
            # Apply opacity immediately
            try: self.root.attributes('-alpha', S.get('window_opacity', 1.0))
            except: pass
            self.show_toast('✅ Settings saved!  Restart the app to apply all colour & font changes.')

        def _reset_all():
            import tkinter.messagebox as mb
            if not mb.askyesno('Reset All Settings',
                               'Reset ALL settings to defaults?\nThis cannot be undone.'):
                return
            _SETTINGS.clear()
            _SETTINGS.update(_DEFAULT_SETTINGS)
            _save_settings(_SETTINGS)
            self.show_toast('↩ All settings reset — please restart the app')

        btn_r = tk.Frame(save_card, bg=SURFACE3)
        btn_r.pack(fill='x')
        tk.Button(btn_r, text='  💾  Save & Apply Settings  ',
                  bg=ACCENT, fg='#080810', font=('Consolas', 10, 'bold'), relief='flat', bd=0,
                  cursor='hand2', activebackground=ACCENT_DIM, activeforeground='#080810',
                  padx=14, pady=8, command=_apply_and_save).pack(side='left', padx=(0, 10))
        tk.Button(btn_r, text='↩  Reset All to Defaults',
                  bg=SURFACE2, fg=MUTED, font=('Consolas', 8), relief='flat', bd=0,
                  cursor='hand2', activebackground=BORDER2, activeforeground=TEXT,
                  padx=10, pady=8, command=_reset_all).pack(side='left')

        tk.Label(save_card,
                 text='⚠  Some changes (colours, fonts) require an app restart to fully apply.\n'
                      '   Toggle options (lag mode, icons, etc.) apply immediately.',
                 bg=SURFACE3, fg=MUTED, font=('Consolas', 7), justify='left', pady=6).pack(anchor='w')

        _gap(20)

    def _build_credits_page(self):
        import webbrowser
        page = tk.Frame(self.page_frame, bg=BG)
        self.pages['credits'] = page

        # ── Scrollable container ──────────────────────────────
        canvas = tk.Canvas(page, bg=BG, highlightthickness=0)
        scr = tk.Scrollbar(page, bg=SURFACE2, troughcolor=BG,
                           activebackground=BORDER, relief='flat', width=6,
                           command=canvas.yview)
        canvas.configure(yscrollcommand=scr.set)
        scr.pack(side='right', fill='y')
        canvas.pack(side='left', fill='both', expand=True)
        inner = tk.Frame(canvas, bg=BG)
        cwin = canvas.create_window((0, 0), window=inner, anchor='nw')
        canvas.bind('<Configure>', lambda e: canvas.itemconfig(cwin, width=e.width))

        def _scroll_credits(e):
            canvas.yview_scroll(-1 * (e.delta // 120), 'units')

        def _bind_all_scroll_credits(widget):
            try:
                widget.bind('<MouseWheel>', _scroll_credits)
            except Exception:
                pass
            for child in widget.winfo_children():
                _bind_all_scroll_credits(child)

        canvas.bind('<MouseWheel>', _scroll_credits)

        def _on_credits_resize(e):
            canvas.configure(scrollregion=canvas.bbox('all'))
            _bind_all_scroll_credits(inner)

        inner.bind('<Configure>', _on_credits_resize)

        def _gap(h=12):
            tk.Frame(inner, bg=BG, height=h).pack(fill='x')

        # ── HERO BANNER ───────────────────────────────────────
        hero = tk.Frame(inner, bg=SURFACE2)
        hero.pack(fill='x')
        tk.Frame(hero, bg=ACCENT, height=3).pack(fill='x')
        hero_body = tk.Frame(hero, bg=SURFACE2)
        hero_body.pack(fill='x', padx=20, pady=16)
        tk.Label(hero_body, text='PLS DONATE', bg=SURFACE2, fg=ACCENT,
                 font=('Consolas', 20, 'bold')).pack(anchor='center')
        tk.Label(hero_body, text='TRACKER', bg=SURFACE2, fg=TEXT,
                 font=('Consolas', 16, 'bold')).pack(anchor='center')
        tk.Label(hero_body, text='v1.0.0  ·  by ItsYamaaaInc', bg=SURFACE2, fg=DIM,
                 font=('Consolas', 8)).pack(anchor='center', pady=(4, 0))
        tk.Frame(hero, bg=ACCENT2, height=2).pack(fill='x')

        _gap(18)

        # ── CREATOR CARD ──────────────────────────────────────
        outer = tk.Frame(inner, bg=ACCENT, padx=1, pady=1)
        outer.pack(fill='x', padx=18, pady=4)
        card = tk.Frame(outer, bg=SURFACE3)
        card.pack(fill='both', expand=True)
        tk.Frame(card, bg=ACCENT, width=3).pack(side='left', fill='y')
        card_body = tk.Frame(card, bg=SURFACE3)
        card_body.pack(side='left', fill='both', expand=True, padx=12, pady=12)

        row1 = tk.Frame(card_body, bg=SURFACE3)
        row1.pack(fill='x')
        tk.Label(row1, text='👑', bg=SURFACE3, font=('Segoe UI Emoji', 16)).pack(side='left', padx=(0, 8))
        info_col = tk.Frame(row1, bg=SURFACE3)
        info_col.pack(side='left')
        tk.Label(info_col, text='ItsYamaaaInc', bg=SURFACE3, fg=ACCENT,
                 font=('Consolas', 14, 'bold')).pack(anchor='w')
        tk.Label(info_col, text='Creator & Developer', bg=SURFACE3, fg=DIM,
                 font=('Consolas', 8)).pack(anchor='w')

        tk.Frame(card_body, bg=BG, height=8).pack(fill='x')
        tk.Frame(card_body, bg=BORDER, height=1).pack(fill='x')
        tk.Frame(card_body, bg=BG, height=8).pack(fill='x')

        tk.Label(card_body,
            text='Built this tool to make PLS DONATE streaming easier.\nAuto username detection, ban management, and more!',
            bg=SURFACE3, fg=TEXT, font=('Consolas', 8), justify='left', wraplength=340
        ).pack(anchor='w')

        tk.Frame(card_body, bg=BG, height=10).pack(fill='x')

        btn_row = tk.Frame(card_body, bg=SURFACE3)
        btn_row.pack(anchor='w')

        def copy_username():
            pyperclip.copy('ItsYamaaaInc')
            self.show_toast('✔ Copied "ItsYamaaaInc" — paste in PLS DONATE search!')

        def open_roblox_profile():
            import webbrowser
            webbrowser.open('https://www.roblox.com/users/8969916993/profile')

        tk.Button(btn_row,
            text='  💝  Support yama in PLS DONATE  ',
            bg=ACCENT, fg='#080810',
            font=('Consolas', 9, 'bold'), relief='flat', bd=0,
            cursor='hand2', activebackground=ACCENT_DIM,
            activeforeground='#080810', padx=10, pady=6,
            command=copy_username
        ).pack(side='left', padx=(0, 6))

        tk.Button(btn_row,
            text='🔗 Roblox Profile',
            bg=SURFACE2, fg=ACCENT,
            font=('Consolas', 8, 'bold'), relief='flat', bd=0,
            cursor='hand2', activebackground=BORDER2,
            activeforeground=ACCENT, padx=8, pady=6,
            command=open_roblox_profile
        ).pack(side='left')

        tk.Label(card_body,
            text='↑ Copies username · paste in PLS DONATE search to find & donate',
            bg=SURFACE3, fg=MUTED, font=('Consolas', 7)
        ).pack(anchor='w', pady=(4, 0))

        _gap(18)

        # ── VERSION LOG ───────────────────────────────────────
        vhdr = tk.Frame(inner, bg=SURFACE)
        vhdr.pack(fill='x', padx=18)
        tk.Frame(vhdr, bg=ACCENT3, width=3).pack(side='left', fill='y')
        tk.Label(vhdr, text='  📋  VERSION LOG', bg=SURFACE, fg=ACCENT3,
                 font=('Consolas', 9, 'bold'), pady=7).pack(side='left')

        _gap(4)

        _versions = [
            ('v1.0.0', 'Initial Release', ACCENT, [
                'Auto username extraction from YouTube chat',
                'Real-time Roblox API validation',
                'Smart noise filtering (skips common words)',
                'Ban & Timeout management system',
                'Copy username to clipboard instantly',
                'Always-on-top window mode',
                'Session stats: users, dups, messages, bans',
                'Wide / Thin layout toggle',
                'Panel show / hide toggles',
                'Restore deleted usernames',
                'Mod & Member color badges',
            ]),
        ]

        for ver, title, col, items in _versions:
            vouter = tk.Frame(inner, bg=col, padx=1, pady=1)
            vouter.pack(fill='x', padx=18, pady=3)
            vcard = tk.Frame(vouter, bg=SURFACE3)
            vcard.pack(fill='both', expand=True)
            tk.Frame(vcard, bg=col, width=3).pack(side='left', fill='y')
            vbody = tk.Frame(vcard, bg=SURFACE3)
            vbody.pack(side='left', fill='both', expand=True, padx=10, pady=8)
            vrow = tk.Frame(vbody, bg=SURFACE3)
            vrow.pack(fill='x')
            tk.Label(vrow, text=ver, bg='#0a2218', fg=col,
                     font=('Consolas', 9, 'bold'), padx=6, pady=1).pack(side='left')
            tk.Label(vrow, text=f'  {title}', bg=SURFACE3, fg=TEXT,
                     font=('Consolas', 9, 'bold')).pack(side='left')
            tk.Frame(vbody, bg=BG, height=6).pack(fill='x')
            for item in items:
                irow = tk.Frame(vbody, bg=SURFACE3)
                irow.pack(fill='x', pady=1)
                tk.Label(irow, text='›', bg=SURFACE3, fg=col,
                         font=('Consolas', 9, 'bold')).pack(side='left', padx=(0, 6))
                tk.Label(irow, text=item, bg=SURFACE3, fg=DIM,
                         font=('Consolas', 8), justify='left').pack(side='left', anchor='w')

        _gap(18)

        # ── HOW TO USE ────────────────────────────────────────
        hhdr = tk.Frame(inner, bg=SURFACE)
        hhdr.pack(fill='x', padx=18)
        tk.Frame(hhdr, bg=PURPLE, width=3).pack(side='left', fill='y')
        tk.Label(hhdr, text='  🎮  HOW TO USE', bg=SURFACE, fg=PURPLE,
                 font=('Consolas', 9, 'bold'), pady=7).pack(side='left')

        _gap(4)

        _steps = [
            ('1', 'Open YouTube & start your PLS DONATE stream'),
            ('2', 'Click ⊞ Popout Chat on your YouTube live chat'),
            ('3', 'Tracker auto-reads usernames from chat instantly'),
            ('4', 'Click any username to copy it to clipboard'),
            ('5', 'Paste into PLS DONATE search and send robux!'),
        ]
        houter = tk.Frame(inner, bg=PURPLE, padx=1, pady=1)
        houter.pack(fill='x', padx=18, pady=3)
        hcard = tk.Frame(houter, bg=SURFACE3)
        hcard.pack(fill='both', expand=True)
        tk.Frame(hcard, bg=PURPLE, width=3).pack(side='left', fill='y')
        hbody = tk.Frame(hcard, bg=SURFACE3)
        hbody.pack(side='left', fill='both', expand=True, padx=10, pady=10)
        for num, step in _steps:
            srow = tk.Frame(hbody, bg=SURFACE3)
            srow.pack(fill='x', pady=2)
            tk.Label(srow, text=num, bg='#110a28', fg=PURPLE,
                     font=('Consolas', 8, 'bold'), width=2, pady=1).pack(side='left', padx=(0, 8))
            tk.Label(srow, text=step, bg=SURFACE3, fg=TEXT,
                     font=('Consolas', 8)).pack(side='left', anchor='w')

        _gap(18)

        # ── FOOTER ────────────────────────────────────────────
        foot = tk.Frame(inner, bg=SURFACE2)
        foot.pack(fill='x')
        tk.Frame(foot, bg=BORDER, height=1).pack(fill='x')
        tk.Label(foot, text='Made with ❤ for the PLS DONATE community',
                 bg=SURFACE2, fg=MUTED, font=('Consolas', 7), pady=10).pack()
        tk.Frame(foot, bg=ACCENT2, height=2).pack(fill='x')
        _gap(8)

    # ── Avatar ────────────────────────────────────────────────
    def _make_avatar(self, parent, name, is_mod, is_member, row_bg):
        SIZE = _SETTINGS.get('avatar_size', 38)
        c = tk.Canvas(parent, width=SIZE, height=SIZE, bg=row_bg, highlightthickness=0)
        if is_mod:
            bg_col, fg_col, ring = '#5c2800', '#ffcc00', '#ffcc00'
            text, fnt = '🔨', ('Segoe UI Emoji', 13)
        elif is_member:
            bg_col, fg_col, ring = '#2a0a5c', '#d0b4ff', '#b89cff'
            text, fnt = '★', ('Consolas', 14, 'bold')
        else:
            bg_col, fg_col = _av_colors(name)
            ring = fg_col
            text = _initials(name)
            fnt  = ('Consolas', 11, 'bold')
        pad = 2
        c.create_oval(pad, pad, SIZE-pad, SIZE-pad, fill=bg_col, outline=ring, width=1)
        c.create_text(SIZE//2, SIZE//2+1, text=text, fill=fg_col, font=fnt)
        return c

    # ── Pending row ──────────────────────────────────────────
    def render_pending(self, name, is_mod=False, is_member=False, from_author=False):
        lc = name.lower()
        if lc in self.pending_frames:
            return

        if self.u_empty_lbl.winfo_ismapped():
            self.u_empty_lbl.pack_forget()

        PENDING_BG = '#0e0e18'
        wrapper = tk.Frame(self.u_list_frame, bg=BG, height=48)
        wrapper.pack(fill='x', padx=6, pady=2)
        wrapper.pack_propagate(False)
        tk.Frame(wrapper, bg=MUTED, width=3).pack(side='left', fill='y')
        row = tk.Frame(wrapper, bg=PENDING_BG)
        row.pack(side='left', fill='both', expand=True)

        SIZE = 38
        c = tk.Canvas(row, width=SIZE, height=SIZE, bg=PENDING_BG, highlightthickness=0)
        c.create_oval(2, 2, SIZE-2, SIZE-2, fill=MUTED, outline='')
        c.create_text(SIZE//2, SIZE//2+1, text='?', fill='#555570',
                      font=('Consolas', 12, 'bold'))
        c.pack(side='left', padx=(8, 6), pady=5)

        nf = tk.Frame(row, bg=PENDING_BG)
        nf.pack(side='left', fill='x', expand=True, pady=2)
        name_lbl = tk.Label(nf, text=name, bg=PENDING_BG, fg='#555570',
                             font=('Consolas', 10), anchor='w')
        name_lbl.pack(side='left')
        tk.Label(nf, text='  checking...  ', bg='#141420', fg=MUTED,
                 font=('Consolas', 6), pady=2).pack(side='left', padx=5)

        self.pending_frames[lc] = wrapper
        self.pending_labels[lc] = name_lbl
        self.u_canvas.update_idletasks()
        self._bind_scroll(wrapper)
        self.u_canvas.yview_moveto(1.0)

    def _confirm_username(self, name, is_mod=False, is_member=False, from_author=False):
        lc = name.lower()
        w = self.pending_frames.pop(lc, None)
        if w and w.winfo_exists():
            w.destroy()
        self.pending_labels.pop(lc, None)

        with data_lock:
            if lc in deleted_set:
                self.dup_count += 1
                self.stat_vars['dups'].set(str(self.dup_count))
                return
            if any(u['name'].lower() == lc for u in usernames):
                self.dup_count += 1
                self.stat_vars['dups'].set(str(self.dup_count))
                return
            if self.is_banned(lc):
                return
            usernames.append({'name': name, 'is_mod': is_mod,
                               'is_member': is_member, 'from_author': from_author})

        self.render_username(name, is_mod=is_mod, is_member=is_member,
                             from_author=from_author)
        if self.username_count > 0 and self.u_empty_lbl.winfo_ismapped():
            self.u_empty_lbl.pack_forget()

    def _reject_username(self, name):
        lc = name.lower()
        w = self.pending_frames.pop(lc, None)
        if w and w.winfo_exists():
            w.destroy()
        self.pending_labels.pop(lc, None)
        if (self.username_count == 0 and not self.pending_frames
                and not self.u_empty_lbl.winfo_ismapped()):
            self.u_empty_lbl.pack(pady=40)

    # ── Render username row ───────────────────────────────────
    def render_username(self, name, is_mod=False, is_member=False, from_author=False):
        if self.u_empty_lbl.winfo_ismapped():
            self.u_empty_lbl.pack_forget()

        lc = name.lower()
        row_bg = SURFACE2

        wrapper = tk.Frame(self.u_list_frame, bg=BG, height=48)
        wrapper.pack(fill='x', padx=6, pady=2)
        wrapper.pack_propagate(False)

        if is_mod:
            stripe_col = MOD_COLOR
        elif is_member:
            stripe_col = MEMBER_COLOR
        elif from_author:
            stripe_col = '#56b4ff'
        else:
            _, stripe_col = _av_colors(name)
        tk.Frame(wrapper, bg=stripe_col, width=3).pack(side='left', fill='y')

        row = tk.Frame(wrapper, bg=row_bg)
        row.pack(side='left', fill='both', expand=True)

        av = self._make_avatar(row, name, is_mod, is_member, row_bg)
        av.pack(side='left', padx=(8, 6), pady=5)

        nf = tk.Frame(row, bg=row_bg)
        nf.pack(side='left', fill='x', expand=True, pady=2)

        if is_mod:
            nc = MOD_COLOR; wt = 'bold'
        elif is_member:
            nc = MEMBER_COLOR; wt = 'bold'
        elif from_author:
            nc = '#56b4ff'; wt = 'normal'
        else:
            nc = TEXT; wt = 'normal'

        name_lbl = tk.Label(nf, text=name, bg=row_bg, fg=nc,
                             font=('Consolas', 10, wt), anchor='w', cursor='hand2')
        name_lbl.pack(side='left')

        if is_mod:
            tk.Label(nf, text='  MOD  ', bg='#3d2000', fg=MOD_COLOR,
                     font=('Consolas', 6, 'bold'), pady=2).pack(side='left', padx=5)
        elif is_member:
            tk.Label(nf, text='  MBR  ', bg='#1a0840', fg=MEMBER_COLOR,
                     font=('Consolas', 6, 'bold'), pady=2).pack(side='left', padx=5)
        elif from_author:
            tk.Label(nf, text='  AUTHOR  ', bg='#071828', fg='#56b4ff',
                     font=('Consolas', 6, 'bold'), pady=2).pack(side='left', padx=5)

        btn_frame = tk.Frame(row, bg=row_bg)
        btn_frame.pack(side='right', padx=6)

        copy_btn = tk.Button(btn_frame, text='⧉ Copy', bg=SURFACE3, fg=ACCENT,
                              font=('Consolas', 7, 'bold'), relief='flat', bd=0,
                              cursor='hand2', padx=6, pady=3,
                              activebackground=BORDER, activeforeground=ACCENT,
                              command=lambda n=name, r=row, nl=name_lbl,
                                             l=lc, ncc=nc: self.copy_single(n, r, nl, l, ncc))
        copy_btn.pack(side='left', padx=2)

        del_btn = tk.Button(btn_frame, text='✕', bg=SURFACE3, fg=MUTED,
                             font=('Consolas', 8, 'bold'), relief='flat', bd=0,
                             cursor='hand2', padx=6, pady=3,
                             activebackground=DANGER_DIM, activeforeground=DANGER,
                             command=lambda n=name, r=row, l=lc: self.del_username(n, r, l))
        del_btn.pack(side='left', padx=2)

        def _all(w):
            yield w
            for ch in w.winfo_children(): yield from _all(ch)

        def on_enter(e, r=row, w=wrapper):
            if lc not in self.selected and lc not in self.copied_set:
                for wid in _all(r):
                    try:
                        if isinstance(wid, tk.Canvas): wid.config(bg=ROW_HOVER)
                        elif not isinstance(wid, tk.Button): wid.config(bg=ROW_HOVER)
                    except: pass

        def on_leave(e, r=row):
            if lc not in self.selected and lc not in self.copied_set:
                for wid in _all(r):
                    try:
                        if isinstance(wid, tk.Canvas): wid.config(bg=row_bg)
                        elif not isinstance(wid, tk.Button): wid.config(bg=row_bg)
                    except: pass

        def toggle(e, r=row, l=lc, nl=name_lbl, ncc=nc):
            if l in self.selected:
                self.selected.discard(l)
                copied = l in self.copied_set
                new_bg = COPIED_BG if copied else SURFACE2
                for w in _all(r):
                    try:
                        if isinstance(w, tk.Canvas): w.config(bg=new_bg)
                        elif not isinstance(w, tk.Button): w.config(bg=new_bg)
                    except: pass
                nl.config(fg=COPIED_FG if copied else ncc)
            else:
                self.selected.add(l)
                for w in _all(r):
                    try:
                        if isinstance(w, tk.Canvas): w.config(bg=SEL_BG)
                        elif not isinstance(w, tk.Button): w.config(bg=SEL_BG)
                    except: pass

        for w in _all(row):
            if not isinstance(w, tk.Button):
                try:
                    w.bind('<Button-1>', toggle)
                    w.bind('<Enter>', on_enter)
                    w.bind('<Leave>', on_leave)
                except: pass

        self.username_frames[lc] = row
        self.username_labels[lc] = name_lbl
        self.username_colors[lc] = nc
        self.username_count += 1
        self.u_count_lbl.config(text=str(self.username_count))
        self.stat_vars['total'].set(str(self.username_count))
        self.u_canvas.update_idletasks()
        self._bind_scroll(wrapper)
        self.u_canvas.yview_moveto(1.0)

    def _bind_scroll(self, widget):
        def _scroll(e):
            self.u_canvas.yview_scroll(-1*(e.delta//120), 'units')
        try:
            widget.bind('<MouseWheel>', _scroll)
        except Exception:
            pass
        for child in widget.winfo_children():
            self._bind_scroll(child)

    def _mark_copied(self, lc, row, name_lbl, orig_color):
        self.copied_set.add(lc)
        if lc not in self.selected:
            def _all(w):
                yield w
                for ch in w.winfo_children(): yield from _all(ch)
            for w in _all(row):
                try:
                    if isinstance(w, tk.Canvas): w.config(bg=COPIED_BG)
                    elif not isinstance(w, tk.Button): w.config(bg=COPIED_BG)
                except: pass
            name_lbl.config(fg=COPIED_FG)

    # ── Ban logic ─────────────────────────────────────────────
    def _toggle_timeout_entry(self):
        if self.ban_type_var.get() == 'timeout':
            self.timeout_frame.pack(side='left', padx=4)
        else:
            self.timeout_frame.pack_forget()

    def add_ban(self):
        name = self.ban_entry.get().strip()
        if not name:
            self.show_toast('Enter a username first!')
            return
        lc = name.lower()
        bt = self.ban_type_var.get()
        until = None
        if bt == 'timeout':
            try:
                until = time.time() + float(self.timeout_entry.get()) * 60
            except:
                self.show_toast('Invalid timeout duration!')
                return
        banned_set[lc] = {'name': name, 'type': bt, 'until': until}
        self.ban_entry.delete(0, 'end')
        self._render_ban_row(lc)
        self._update_ban_count()
        self.show_toast(f'{"Timed out" if bt=="timeout" else "Banned"}: {name}')

    def _render_ban_row(self, lc):
        if lc in self.ban_frames:
            return
        entry = banned_set.get(lc)
        if not entry: return
        if self.ban_empty_lbl.winfo_ismapped():
            self.ban_empty_lbl.pack_forget()
        row = tk.Frame(self.ban_list_frame, bg=BANNED_BG, pady=1)
        row.pack(fill='x', padx=4, pady=2)
        ic = DANGER if entry['type'] == 'ban' else ACCENT3
        tk.Label(row, text='🔨' if entry['type']=='ban' else '⏱',
                 bg=BANNED_BG, fg=ic, font=('Segoe UI Emoji', 12)).pack(side='left', padx=(8,4), pady=4)
        tk.Label(row, text=entry['name'], bg=BANNED_BG, fg=TEXT,
                 font=('Consolas', 10, 'bold')).pack(side='left', fill='x', expand=True)
        tk.Label(row, text='BANNED' if entry['type']=='ban' else 'TIMEOUT',
                 bg=BANNED_BG, fg=ic, font=('Consolas', 7, 'bold')).pack(side='left', padx=6)
        if entry['type'] == 'timeout' and entry.get('until'):
            tl = tk.Label(row, text='', bg=BANNED_BG, fg=MUTED, font=('Consolas', 7))
            tl.pack(side='left', padx=4)
            self._update_timer(lc, tl)
        tk.Button(row, text='✕ Unban', bg=BANNED_BG, fg=MUTED,
                  font=('Consolas', 8), relief='flat', bd=0, cursor='hand2',
                  activebackground=BORDER, activeforeground=DANGER,
                  command=lambda l=lc, r=row: self._unban(l, r)).pack(side='right', padx=6, pady=4)
        self.ban_frames[lc] = row
        self.ban_canvas.update_idletasks()
        self.ban_canvas.yview_moveto(1.0)

    def _update_timer(self, lc, lbl):
        if not lbl.winfo_exists(): return
        e = banned_set.get(lc)
        if not e or not e.get('until'): return
        rem = e['until'] - time.time()
        if rem <= 0:
            self._unban(lc, self.ban_frames.get(lc))
            return
        lbl.config(text=f'{int(rem//60)}m {int(rem%60):02d}s left')
        self.root.after(1000, lambda: self._update_timer(lc, lbl))

    def _unban(self, lc, row):
        banned_set.pop(lc, None)
        self.ban_frames.pop(lc, None)
        if row and row.winfo_exists(): row.destroy()
        if not self.ban_frames: self.ban_empty_lbl.pack(pady=40)
        self._update_ban_count()
        self.show_toast('Unbanned!')

    def clear_bans(self):
        banned_set.clear()
        for r in list(self.ban_frames.values()):
            if r.winfo_exists(): r.destroy()
        self.ban_frames.clear()
        self.ban_empty_lbl.pack(pady=40)
        self._update_ban_count()
        self.show_toast('All bans cleared!')

    def _update_ban_count(self):
        n = len(banned_set)
        self.ban_count_lbl.config(text=str(n))
        self.stat_vars['banned'].set(str(n))

    def _cleanup_timeouts(self):
        now = time.time()
        for lc in [l for l, e in list(banned_set.items())
                   if e['type']=='timeout' and e.get('until') and e['until'] < now]:
            self._unban(lc, self.ban_frames.get(lc))
        self.root.after(5000, self._cleanup_timeouts)

    def is_banned(self, lc):
        e = banned_set.get(lc)
        if not e: return False
        if e['type']=='timeout' and e.get('until') and e['until'] < time.time():
            self._unban(lc, self.ban_frames.get(lc))
            return False
        return True

    # ── Polling & ingestion ───────────────────────────────────
    def poll_messages(self):
        with data_lock:
            new_msgs = messages[self.last_msg_index:]
            self.last_msg_index = len(messages)
        for msg in new_msgs:
            self.ingest(msg)
        if new_msgs:
            self.update_status('connected')
            self.banner.pack_forget()
        self.root.after(200, self.poll_messages)

    def ingest(self, msg):
        self.msg_count += 1
        self.stat_vars['msgs'].set(str(self.msg_count))

        author    = msg.get('author', '')
        text      = msg.get('text', '')
        ts        = msg.get('timestamp', '')[:19].replace('T', ' ')[11:]
        badges    = msg.get('badges', [])
        is_mod    = any('mod'    in b.lower() for b in badges)
        is_member = any('member' in b.lower() for b in badges)

        names = msg.get('usernames') or extract_roblox_names(text)

        candidates = list(names)
        if author and _ROBLOX_RE.match(author):
            alc = author.lower()
            if (alc not in _NOISE and len(author) >= 4
                    and alc not in {n.lower() for n in names}
                    and not _is_common_english_word(author)
                    and not _is_spam_token(author)):
                candidates.append(author)

        self.add_chat_msg(author, text, ts, names, is_mod=is_mod, is_member=is_member)

        seen_msg = set()
        for uname in candidates:
            lc = uname.lower()
            if lc in seen_msg: continue
            seen_msg.add(lc)
            from_author = (uname == author and uname not in names)
            if self.is_banned(lc): continue
            if lc in deleted_set: continue
            if any(u['name'].lower() == lc for u in usernames): continue

            with _valid_cache_lock:
                cached = _valid_cache.get(lc, None)

            if cached is True:
                with data_lock:
                    if not any(u['name'].lower() == lc for u in usernames):
                        usernames.append({'name': uname, 'is_mod': is_mod,
                                          'is_member': is_member, 'from_author': from_author})
                self.render_username(uname, is_mod=is_mod,
                                     is_member=is_member, from_author=from_author)
            elif cached is False:
                continue
            else:
                with _pending_lock:
                    if lc in _pending_set:
                        continue
                    _pending_set.add(lc)
                self.render_pending(uname, is_mod=is_mod,
                                    is_member=is_member, from_author=from_author)
                _validate_queue.put((uname, is_mod, is_member, from_author))

    def add_chat_msg(self, author, text, ts, names, is_mod=False, is_member=False):
        name_set = {n.lower() for n in names}
        if is_mod:
            atag, ttag, mtag = 'author_mod', 'time_mod', 'msg_mod'
            badge, badge_tag = ' 🔨MOD ', 'badge_mod'
        elif is_member:
            atag, ttag, mtag = 'author_member', 'time_member', 'msg_member'
            badge, badge_tag = ' ★MBR ', 'badge_member'
        else:
            atag, ttag, mtag = 'author', 'time', 'msg'
            badge, badge_tag = None, None

        self.c_text.config(state='normal')
        self.c_text.insert('end', (author or '?'), atag)
        if badge:
            self.c_text.insert('end', badge, badge_tag)
        self.c_text.insert('end', ' ', atag)
        if _SETTINGS.get('show_timestamps', True):
            self.c_text.insert('end', ts + '\n', ttag)
        else:
            self.c_text.insert('end', '\n', ttag)
        tokens = text.split(' ')
        for i, tok in enumerate(tokens):
            clean = ''.join(c for c in tok if c.isalnum() or c == '_').lower()
            self.c_text.insert('end', tok, 'hl' if clean in name_set else mtag)
            if i < len(tokens) - 1:
                self.c_text.insert('end', ' ', mtag)
        self.c_text.insert('end', '\n\n', mtag)
        if int(self.c_text.index('end-1c').split('.')[0]) > 1200:
            self.c_text.delete('1.0', '400.0')
        self.c_text.config(state='disabled')
        if _SETTINGS.get('chat_autoscroll', True):
            self.c_text.yview_moveto(1.0)
        self.c_count_lbl.config(
            text=str(max(0, self.c_text.get('1.0','end').count('\n\n') - 1)))

    # ── Misc ──────────────────────────────────────────────────
    def update_status(self, status):
        if status == 'connected':
            self.pill_var.set('⬤  LIVE')
            self.pill_lbl.config(fg=ACCENT, bg=SURFACE)
            self.status_lbl.config(text='⬤  Reading live chat...', fg=ACCENT)
        elif status == 'error':
            self.pill_var.set('⬤  ERROR')
            self.pill_lbl.config(fg=DANGER, bg=SURFACE)
        else:
            self.pill_var.set('⬤  WAITING')
            self.pill_lbl.config(fg=ACCENT3, bg=SURFACE)
            self.status_lbl.config(text='Waiting for YouTube popout chat...', fg=MUTED)

    def del_username(self, name, row, lc):
        deleted_set.add(lc)
        usernames[:] = [u for u in usernames if u['name'].lower() != lc]
        self.selected.discard(lc); self.copied_set.discard(lc)
        self.username_frames.pop(lc, None)
        self.username_labels.pop(lc, None)
        self.username_colors.pop(lc, None)
        try:
            wrapper = row.master
            if wrapper and wrapper.winfo_exists():
                wrapper.destroy()
            elif row.winfo_exists():
                row.destroy()
        except Exception:
            pass
        self.username_count = max(0, self.username_count - 1)
        self.u_count_lbl.config(text=str(self.username_count))
        self.stat_vars['total'].set(str(self.username_count))
        self.stat_vars['deleted'].set(str(len(deleted_set)))
        if self.username_count == 0: self.u_empty_lbl.pack(pady=40)
        self.show_toast('Deleted: ' + name)

    def restore_deleted(self):
        if not deleted_set:
            self.show_toast('Nothing to restore!'); return
        n = len(deleted_set); deleted_set.clear()
        self.stat_vars['deleted'].set('0')
        self.show_toast(f'Restored {n} username{"s" if n>1 else ""}')

    def reset_session(self):
        import tkinter.messagebox as mb
        if not mb.askyesno('Reset', 'Clear all usernames and chat?'): return
        usernames.clear(); deleted_set.clear()
        self.selected.clear(); self.copied_set.clear()
        self.username_frames.clear(); self.username_labels.clear(); self.username_colors.clear()
        self.username_count = self.dup_count = self.msg_count = self.last_msg_index = 0
        with data_lock: messages.clear()
        for w in self.u_list_frame.winfo_children(): w.destroy()
        self.u_empty_lbl = tk.Label(self.u_list_frame,
            text='\n👤\n\nSession cleared — waiting...',
            bg=BG, fg=MUTED, font=('Consolas', 9), justify='center')
        self.u_empty_lbl.pack(pady=40)
        self.c_text.config(state='normal'); self.c_text.delete('1.0','end')
        self.c_text.config(state='disabled')
        for k in self.stat_vars: self.stat_vars[k].set('0')
        self.u_count_lbl.config(text='0'); self.c_count_lbl.config(text='0')
        self.show_toast('Session cleared!')

    def copy_all(self):
        if not usernames:
            self.show_toast('No usernames yet!'); return
        try: pyperclip.copy('\n'.join(u['name'] for u in usernames))
        except:
            self.root.clipboard_clear()
            self.root.clipboard_append('\n'.join(u['name'] for u in usernames))
        for u in usernames:
            lc = u['name'].lower()
            row = self.username_frames.get(lc)
            nl  = self.username_labels.get(lc)
            nc  = self.username_colors.get(lc, TEXT)
            if row and row.winfo_exists() and nl:
                self._mark_copied(lc, row, nl, nc)
        self.show_toast(f'Copied {len(usernames)} usernames!')

    def copy_selected(self):
        sel = [u['name'] for u in usernames if u['name'].lower() in self.selected]
        if not sel:
            self.show_toast('No usernames selected!'); return
        try: pyperclip.copy('\n'.join(sel))
        except:
            self.root.clipboard_clear(); self.root.clipboard_append('\n'.join(sel))
        self.show_toast(f'Copied {len(sel)} selected!')

    def delete_selected(self):
        to_delete = list(self.selected)
        if not to_delete:
            self.show_toast('No usernames selected!'); return
        for lc in to_delete:
            row = self.username_frames.get(lc)
            if row and row.winfo_exists():
                wrapper = row.master
                wrapper.destroy()
            deleted_set.add(lc)
            self.username_frames.pop(lc, None)
            self.username_labels.pop(lc, None)
            self.username_colors.pop(lc, None)
            self.copied_set.discard(lc)
        usernames[:] = [u for u in usernames if u['name'].lower() not in deleted_set]
        n = len(to_delete)
        self.selected.clear()
        self.username_count = len(usernames)
        self.u_count_lbl.config(text=str(self.username_count))
        self.stat_vars['total'].set(str(self.username_count))
        self.stat_vars['deleted'].set(str(len(deleted_set)))
        if self.username_count == 0:
            self.u_empty_lbl.pack(pady=40)
        self.show_toast(f'Deleted {n} username{"s" if n > 1 else ""}')

    def copy_single(self, name, row, name_lbl, lc, orig_color):
        try: pyperclip.copy(name)
        except:
            self.root.clipboard_clear(); self.root.clipboard_append(name)
        self._mark_copied(lc, row, name_lbl, orig_color)
        self.show_toast('Copied: ' + name)

    def select_all(self):
        def _all(w):
            yield w
            for ch in w.winfo_children(): yield from _all(ch)
        for u in usernames:
            lc = u['name'].lower(); self.selected.add(lc)
            row = self.username_frames.get(lc)
            if row and row.winfo_exists():
                for w in _all(row):
                    try:
                        if isinstance(w, tk.Canvas): w.config(bg=SEL_BG)
                        elif not isinstance(w, tk.Button): w.config(bg=SEL_BG)
                    except: pass

    def deselect_all(self):
        def _all(w):
            yield w
            for ch in w.winfo_children(): yield from _all(ch)
        self.selected.clear()
        for lc, row in self.username_frames.items():
            if not row.winfo_exists(): continue
            copied = lc in self.copied_set
            new_bg = COPIED_BG if copied else SURFACE2
            nl = self.username_labels.get(lc); nc = self.username_colors.get(lc, TEXT)
            for w in _all(row):
                try:
                    if isinstance(w, tk.Canvas): w.config(bg=new_bg)
                    elif not isinstance(w, tk.Button): w.config(bg=new_bg)
                except: pass
            if nl: nl.config(fg=COPIED_FG if copied else nc)

    def clear_chat(self):
        self.c_text.config(state='normal'); self.c_text.delete('1.0','end')
        self.c_text.config(state='disabled'); self.c_count_lbl.config(text='0')

    def delete_all(self):
        if not usernames:
            self.show_toast('No usernames to delete!'); return
        import tkinter.messagebox as mb
        n = len(usernames)
        if not mb.askyesno('Delete All', f'Delete ALL {n} username{"s" if n>1 else ""}?\nThis cannot be undone (use Restore to recover).'):
            return
        for u in usernames:
            lc = u['name'].lower()
            deleted_set.add(lc)
            row = self.username_frames.get(lc)
            if row and row.winfo_exists():
                try: row.master.destroy()
                except: pass
        usernames.clear()
        self.username_frames.clear()
        self.username_labels.clear()
        self.username_colors.clear()
        self.selected.clear()
        self.copied_set.clear()
        self.username_count = 0
        self.u_count_lbl.config(text='0')
        self.stat_vars['total'].set('0')
        self.stat_vars['deleted'].set(str(len(deleted_set)))
        self.u_empty_lbl.pack(pady=40)
        self.show_toast(f'Deleted all {n} usernames!')

    def toggle_chat_panel(self):
        self._chat_panel_visible = not self._chat_panel_visible
        self._relayout_panels()

    def toggle_users_panel(self):
        self._users_panel_visible = not self._users_panel_visible
        self._relayout_panels()

    def toggle_layout_mode(self):
        if self._layout_mode == 'thin':
            self._layout_mode = 'wide'
            self.root.geometry('900x500')
            self.layout_mode_btn.config(text='⇕ Thin')
        else:
            self._layout_mode = 'thin'
            self.root.geometry('420x720')
            self.layout_mode_btn.config(text='⇔ Wide')
        self._relayout_panels()

    def _relayout_panels(self):
        """Re-pack panels and divider based on visibility flags and layout mode."""
        self.left_panel.pack_forget()
        self._users_divider.pack_forget()
        self.right_panel.pack_forget()

        # Reconfigure divider for orientation
        if self._layout_mode == 'wide':
            self._users_divider.config(width=1, height=0)
        else:
            self._users_divider.config(height=1, width=0)

        u = self._users_panel_visible
        c = self._chat_panel_visible
        wide = (self._layout_mode == 'wide')

        if u and c:
            if wide:
                self.left_panel.pack(side='left', fill='both', expand=True)
                self._users_divider.pack(side='left', fill='y')
                self.right_panel.pack(side='left', fill='both', expand=True)
            else:
                self.left_panel.pack(side='top', fill='both', expand=True)
                self._users_divider.pack(side='top', fill='x')
                self.right_panel.pack(side='top', fill='both', expand=True)
        elif u:
            side = 'left' if wide else 'top'
            self.left_panel.pack(side=side, fill='both', expand=True)
        elif c:
            side = 'left' if wide else 'top'
            self.right_panel.pack(side=side, fill='both', expand=True)

        self.users_toggle_btn.config(
            text='👤 Hide Users' if u else '👤 Show Users',
            fg=ACCENT if u else '#00f0a8',
            bg=SURFACE3 if u else '#0a2218')
        self.chat_toggle_btn.config(
            text='💬 Hide Chat' if c else '💬 Show Chat',
            fg=PURPLE if c else '#b89cff',
            bg=SURFACE3 if c else '#110a28')

    def toggle_pin(self):
        self.always_on_top = not self.always_on_top
        self.set_always_on_top(self.always_on_top)
        self.pin_btn.config(text='📌' if self.always_on_top else '📌✕',
                             fg=ACCENT3 if self.always_on_top else MUTED)
        self.show_toast(f'📌 Always on top — {"ON" if self.always_on_top else "OFF"}')

    def show_toast(self, msg):
        self.toast_lbl.config(text='  ' + msg + '  ')
        self.toast_lbl.place(relx=0.5, rely=0.95, anchor='center')
        if self._toast_after: self.root.after_cancel(self._toast_after)
        self._toast_after = self.root.after(2200, lambda: self.toast_lbl.place_forget())

    def switch_tab(self, tab):
        for p in self.pages.values(): p.pack_forget()
        self.pages[tab].pack(fill='both', expand=True)
        for tid, btn in self.tab_btns.items():
            if tid == tab:
                btn.config(bg=BG, fg=ACCENT)
            else:
                btn.config(bg=SURFACE, fg=DIM)

    def _mkbtn(self, parent, text, color, cmd):
        return tk.Button(parent, text=text, bg=SURFACE3, fg=color,
                         font=('Consolas', 8, 'bold'), relief='flat', bd=0,
                         cursor='hand2', activebackground=BORDER2,
                         activeforeground=color, padx=10, pady=4, command=cmd)

    def _mksmall(self, parent, text, cmd, fg=DIM):
        return tk.Button(parent, text=text, bg=SURFACE3, fg=fg,
                         font=('Consolas', 7, 'bold'), relief='flat', bd=0,
                         cursor='hand2', activebackground=BORDER2,
                         activeforeground=ACCENT, padx=6, pady=2, command=cmd)

    def _mktool(self, parent, text, cmd, fg=DIM):
        """Toolbar-style button — slightly taller than _mksmall, used in the action toolbar."""
        return tk.Button(parent, text=text, bg=SURFACE3, fg=fg,
                         font=('Consolas', 8, 'bold'), relief='flat', bd=0,
                         cursor='hand2', activebackground=BORDER2,
                         activeforeground=fg, padx=10, pady=3, command=cmd)


def main():
    threading.Thread(target=run_server, daemon=True).start()
    root = tk.Tk()
    app = App(root)
    threading.Thread(target=_validation_worker, args=(app,), daemon=True).start()
    root.after(200, lambda: app.set_always_on_top(True))
    root.after(600, lambda: app.set_always_on_top(True))
    root.after(300, lambda: root.attributes('-alpha', _SETTINGS.get('window_opacity', 1.0)))
    root.after(5000, app._cleanup_timeouts)
    # ── Auto-update check (3 s after launch, background thread) ──
    root.after(3000, lambda: threading.Thread(
        target=_check_for_updates,
        args=(lambda v, u: _prompt_update(v, u, app),),
        daemon=True
    ).start())
    root.mainloop()

if __name__ == '__main__':
    main()