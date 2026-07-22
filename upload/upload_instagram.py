import os
import requests
import time
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path, override=True)


def get_video_duration(video_path):
    try:
        import subprocess
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
             '-of', 'default=noprint_wrappers=1:nokey=1', str(video_path)],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except Exception:
        pass
    return None


def upload_to_hosting(video_path):
    """Try multiple hosting providers."""
    path = Path(video_path)
    with open(path, 'rb') as f:
        file_data = f.read()
    fname = path.name

    # Try 1: temp.sh (no API key needed)
    try:
        resp = requests.post('https://temp.sh/upload', files={'file': (fname, file_data)}, timeout=120)
        if resp.status_code == 200:
            url = resp.text.strip()
            if url:
                return url
    except Exception:
        pass

    # Try 2: file.io
    try:
        resp = requests.post('https://file.io', files={'file': (fname, file_data)}, timeout=120)
        if resp.status_code == 200:
            data = resp.json()
            if data.get('success'):
                return data['link']
    except Exception:
        pass

    # Try 3: 0x0.st
    try:
        resp = requests.post('https://0x0.st', files={'file': (fname, file_data)}, timeout=120)
        if resp.status_code == 200:
            url = resp.text.strip()
            if url:
                return url
    except Exception:
        pass

    raise Exception("All hosting providers failed")


def upload_to_instagram(video_path, caption, is_story=False):
    media_type = 'STORIES' if is_story else 'REELS'

    print("\n" + "=" * 60)
    print(f"INSTAGRAM {media_type} UPLOAD (URL Method)")
    print("=" * 60)

    access_token = os.getenv('INSTAGRAM_ACCESS_TOKEN') or os.getenv('FACEBOOK_ACCESS_TOKEN')
    user_id = os.getenv('INSTAGRAM_ACCOUNT_ID') or os.getenv('IG_USER_ID')

    def mask(s):
        return f"{s[:10]}...{s[-4:]}" if s and len(s) > 10 else ("PLACEHOLDER" if s == "***" else "MISSING")

    print(f"[instagram] User ID Provided: {user_id}")
    print(f"[instagram] Access Token: {mask(access_token)}")

    if not access_token:
        print("[instagram] Skipping - no token")
        return {'status': 'skipped', 'reason': 'Missing credentials', 'platform': 'instagram'}

    if access_token.startswith('EAAM'):
        print("[instagram] EAAM token detected, resolving Instagram Business Account ID...")
        try:
            me_resp = requests.get(f"https://graph.facebook.com/me?fields=id,name&access_token={access_token}", timeout=10)
            if me_resp.status_code == 200:
                page_id = me_resp.json().get('id')
                ig_resp = requests.get(f"https://graph.facebook.com/{page_id}?fields=instagram_business_account&access_token={access_token}", timeout=10)
                if ig_resp.status_code == 200:
                    ig_account = ig_resp.json().get('instagram_business_account')
                    if ig_account:
                        ig_id = ig_account.get('id')
                        if ig_id != user_id:
                            user_id = ig_id
        except Exception:
            pass

    if not user_id:
        print("[instagram] Skipping - no user ID")
        return {'status': 'skipped', 'reason': 'Missing credentials', 'platform': 'instagram'}

    video_path_obj = Path(video_path)
    if not video_path_obj.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    duration = get_video_duration(video_path_obj)
    if duration:
        print(f"[instagram] Video duration: {duration:.1f}s")
        if is_story and duration > 61.0:
            print(f"[instagram] Skipping Stories upload - video is {duration:.1f}s (max 61s)")
            return {'status': 'skipped', 'reason': f'Video too long for Stories', 'platform': 'instagram'}

    file_size_mb = video_path_obj.stat().st_size / (1024 * 1024)
    print(f"[instagram] Video: {video_path} ({file_size_mb:.2f} MB)")
    caption_limited = caption[:2200] if len(caption) > 2200 else caption
    print(f"[instagram] Caption: {len(caption_limited)} chars")

    api_base = "https://graph.facebook.com/v21.0"

    try:
        print(f"[instagram] Step 1: Uploading to hosting...")
        video_url = upload_to_hosting(video_path_obj)
        print(f"[instagram] Video URL: {video_url}")

        for platform in ['instagram', 'facebook']:
            current_token = access_token
            current_id = user_id
            current_base = api_base

            if platform == 'facebook':
                fb_token = os.getenv('FACEBOOK_ACCESS_TOKEN') or access_token
                fb_id = os.getenv('FACEBOOK_PAGE_ID')
                if not fb_id:
                    print("[instagram] Skipping Facebook - no page ID")
                    continue
                current_token = fb_token
                current_id = fb_id
                current_base = api_base

            print(f"[instagram] Creating {media_type} container...")
            params = {'media_type': media_type, 'video_url': video_url, 'access_token': current_token}
            if media_type != 'STORIES':
                params['caption'] = caption_limited

            resp = requests.post(f"{current_base}/{current_id}/media", params=params, timeout=60)
            if resp.status_code != 200:
                print(f"[instagram] Container failed ({platform}): {resp.text[:200]}")
                continue

            cid = resp.json().get('id')
            print(f"[instagram] Container ({platform}): {cid}")

            max_wait = 210
            waited = 0
            while waited < max_wait:
                s = requests.get(f"{current_base}/{cid}", params={'fields': 'status_code,status', 'access_token': current_token}, timeout=30).json()
                sc = s.get('status_code') or s.get('status', 'UNKNOWN')
                print(f"[instagram] ({platform}) Status: {sc} ({waited}s)")
                if sc == 'FINISHED':
                    break
                elif sc == 'ERROR':
                    raise Exception(f"{s.get('error_message', 'Processing failed')}")
                time.sleep(30)
                waited += 30

            if waited >= max_wait:
                raise Exception("Processing timed out")

            p = requests.post(f"{current_base}/{current_id}/media_publish", params={'creation_id': cid, 'access_token': current_token}, timeout=60)
            if p.status_code == 200:
                mid = p.json().get('id')
                print(f"[instagram] SUCCESS ({platform})! Media ID: {mid}")
            else:
                print(f"[instagram] Publish failed ({platform}): {p.text[:200]}")

        return {'status': 'success', 'platform': 'instagram'}

    except Exception as e:
        print(f"[instagram] ERROR: {e}")
        raise


if __name__ == '__main__':
    video_file = Path('final_video.mp4')
    if video_file.exists():
        try:
            result = upload_to_instagram(str(video_file), "Test")
            print(f"Result: {result}")
        except Exception as e:
            print(f"Failed: {e}")
    else:
        print(f"Video not found: {video_file}")
