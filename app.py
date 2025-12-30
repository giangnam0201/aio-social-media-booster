#!/usr/bin/env python3
# zefame_all_platforms_safe.py  –  drop-in replacement with offline fallback
import requests, sys, json, uuid, time, os, argparse
import concurrent.futures
from datetime import datetime
from colorama import init, Fore, Style

init(autoreset=True)
os.system('cls' if os.name == 'nt' else 'clear')

API_CONFIG  = "https://zefame-free.com/api_free.php?action=config"
LOG_FILE    = "zefame.log"
CONFIG_FILE = "zefame_config.json"          # local fallback
HEADERS     = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                             "AppleWebKit/537.36 (KHTML, like Gecko) "
                             "Chrome/120.0 Safari/537.36"}

# ---------- helpers ----------
def log(msg):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(f"{datetime.now():%F %T}  {msg}\n")

def save_local(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

def load_local():
    if os.path.isfile(CONFIG_FILE):
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return json.load(f)
    return None

def get_config(retries=3):
    # 1. try remote
    for attempt in range(1, retries+1):
        try:
            r = requests.get(API_CONFIG, headers=HEADERS, timeout=15)
            if r.status_code == 200 and r.text.strip():
                cfg = r.json()
                if cfg.get("success"):
                    save_local(cfg)
                    return cfg
        except Exception as e:
            print(f"{Fore.YELLOW}[WARN]{Style.RESET_ALL} remote config attempt {attempt} failed: {e}")
            time.sleep(2 ** attempt)

    # 2. fall back to local file
    local = load_local()
    if local:
        print(f"{Fore.YELLOW}[WARN]{Style.RESET_ALL} using cached config")
        return local

    # 3. nothing works – die gracefully
    print(f"{Fore.RED}Config unreachable and no local copy found.{Style.RESET_ALL}")
    sys.exit(1)

CFG = get_config()
if not CFG.get("success"):
    print(f"{Fore.RED}Invalid config{Style.RESET_ALL}")
    sys.exit(1)
PLATFORMS = CFG["data"]

# ---------- pretty names ----------
PRETTY = {
    "tiktok": "TikTok",
    "instagram": "Instagram",
    "twitter": "Twitter",
    "facebook": "Facebook",
    "youtube": "YouTube",
    "telegram": "Telegram"
}

# ---------- what each service needs ----------
NEEDS_VIDEO_ID = {"tiktok"}

# ---------- worker ----------
# ---------- slow-server safe ----------
# ---------- debug-friendly ----------
# ---------- Cloudflare-proof ----------
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://zefame-free.com/",
    "Origin": "https://zefame-free.com"
})

def safe_post(url, data, retries=5, first_timeout=30):
    for attempt in range(1, retries+1):
        try:
            print(".", end="", flush=True)
            # GET once to pick up CF cookie
            if not SESSION.cookies:
                SESSION.get("https://zefame-free.com", timeout=10)
            r = SESSION.post(url, data=data, timeout=first_timeout + attempt*5)
            log(f"attempt {attempt}  status={r.status_code}  body={r.text[:150]}")
            return r
        except Exception as e:
            log(f"POST attempt {attempt} exception: {e}")
            time.sleep(2 ** attempt)
    return None

# ---------- main ----------
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--platform", help="tiktok / instagram / twitter / facebook / youtube / telegram")
    parser.add_argument("--link1", help="profile / channel / page URL")
    parser.add_argument("--link2", help="video / post / tweet URL (when needed)")
    args = parser.parse_args()

    # 1. choose platform
    if args.platform and args.platform.lower() in PLATFORMS:
        plat_key = args.platform.lower()
    else:
        print(f"{Fore.CYAN}Available platforms:{Style.RESET_ALL}")
        for k in PLATFORMS:
            print(f"  - {Fore.GREEN}{PRETTY[k]}{Style.RESET_ALL}")
        plat_key = input("\nPick platform: ").strip().lower()
        if plat_key not in PLATFORMS:
            print(f"{Fore.RED}Invalid{Style.RESET_ALL}")
            sys.exit(1)

    services = PLATFORMS[plat_key]["services"]
    need_vid = plat_key in NEEDS_VIDEO_ID

    # 2. collect links
    profile_url = args.link1 or input("Enter profile / channel / page URL: ").strip()
    video_url   = args.link2 or (input("Enter video / post / tweet URL (leave empty if N/A): ").strip() if need_vid else "")

    # 3. parse video ID only when necessary
    video_id = ""
    if need_vid and video_url:
        video_id = parse_video_id(plat_key, video_url)
        if not video_id:
            print(f"{Fore.RED}Could not parse video ID{Style.RESET_ALL}")
            sys.exit(1)
        print(f"{Fore.GREEN}Video ID: {video_id}{Style.RESET_ALL}")

    # 4. show services
    print(f"\n{Fore.CYAN}Services for {PRETTY[plat_key]}{Style.RESET_ALL}")
    for svc in services:
        st = f"{Fore.GREEN}[ON]{Style.RESET_ALL}" if svc["available"] else f"{Fore.RED}[OFF]{Style.RESET_ALL}"
        print(f"  - {svc.get('name') or svc['id']}  {st}  {svc['description']}")

    print(f"\n{Fore.YELLOW}Starting booster (Ctrl+C to stop){Style.RESET_ALL}")

    # 5. worker
    # ---------- worker (verbose) ----------
    def worker(svc):
        name = svc.get("name") or str(svc["id"])
        if not svc["available"]:
            print(f"{Fore.RED}[SKIP]{Style.RESET_ALL} {name} unavailable")
            return

        while True:
            try:
                # pick link
                if any(k in name.lower() for k in ("member", "abonné", "followers")):
                    link = profile_url
                else:
                    link = video_url or profile_url

                payload = {
                    "action": "order",
                    "service": svc["id"],
                    "link": link,
                    "uuid": str(uuid.uuid4())
                }
                if need_vid and video_id:
                    payload["videoId"] = video_id

                print(f"{Fore.CYAN}[TRY]{Style.RESET_ALL} {name}  →  {link}")
                r = safe_post("https://zefame-free.com/api_free.php?action=order", payload)
                print("")  # newline after dots
                if r is None:                       # total failure
                    print(f"{Fore.YELLOW}[FAIL]{Style.RESET_ALL} {name}  no HTTP reply")
                    time.sleep(60); continue

                if r.status_code != 200:            # server talked, but refused
                    print(f"{Fore.RED}[HTTP {r.status_code}]{Style.RESET_ALL} {name}  {r.text[:100]}")
                    log(f"{name} HTTP-{r.status_code}: {r.text}")
                    time.sleep(60); continue

                try:
                    res = r.json()
                except Exception as e:
                    print(f"{Fore.RED}[BAD JSON]{Style.RESET_ALL} {name}  body={r.text[:100]}")
                    log(f"{name} bad json: {r.text}")
                    time.sleep(60)
                    continue

                if res.get("success"):
                    print(f"{Fore.GREEN}[OK]{Style.RESET_ALL} {name}  response={res}")
                    wait = res.get("data", {}).get("nextAvailable")
                    sleep = float(wait) - time.time() if wait and float(wait) > time.time() else 300
                    print(f"{Fore.BLUE}[SLEEP]{Style.RESET_ALL} {name}  {sleep:.0f}s")
                    time.sleep(sleep)
                else:
                    msg = res.get("message", "unknown error")
                    print(f"{Fore.YELLOW}[NOK]{Style.RESET_ALL} {name}  {msg}")
                    log(f"{name} server msg: {msg}")
                    time.sleep(300)

            except KeyboardInterrupt:
                break
            except Exception as e:
                log(f"{name} exception: {e}")
                print(f"{Fore.RED}[ERR]{Style.RESET_ALL} {name}  {e}")
                time.sleep(60)

    # 6. run
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(services)) as ex:
        futures = [ex.submit(worker, s) for s in services]
        try:
            concurrent.futures.wait(futures)
        except KeyboardInterrupt:
            print(f"\n{Fore.YELLOW}Stopped by user{Style.RESET_ALL}")

if __name__ == "__main__":
    main()