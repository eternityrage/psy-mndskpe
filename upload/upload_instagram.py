import os
import subprocess
import tempfile
import requests
import time
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path, override=True)


def get_video_duration(video_path):
    try:
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


def reencode_for_ig(video_path):
    path = Path(video_path)
    out = Path(tempfile.gettempdir()) / "ig_enc" / f"ig_{path.stem}.mp4"
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        r = subprocess.run(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
                           '-show_entries', 'stream=codec_name',
                           '-of', 'default=noprint_wrappers=1:nokey=1', str(path)],
                          capture_output=True, text=True, timeout=15)
        codec = r.stdout.strip()
        size_mb = path.stat().st_size / (1024 * 1024)
        if codec == "h264" and size_mb < 50:
            print("[instagram] Video already compatible, skipping re-encode")
            return str(path)
    except Exception:
        pass
    print("[instagram] Re-encoding for Instagram compatibility...")
    try:
        subprocess.run(['ffmpeg', '-i', str(path), '-c:v', 'libx264', '-preset', 'fast',
                       '-crf', '23', '-vf', 'scale=min(1080,iw):min(1920,ih):force_original_aspect_ratio=decrease',
                       '-c:a', 'aac', '-b:a', '128k', '-movflags', '+faststart', '-y', str(out)],
                      capture_output=True, text=True, timeout=300)
        print(f"[instagram] Re-encoded: {out.name}")
        return str(out)
    except Exception:
        return str(video_path)


def upload_to_instagram(video_path, caption, is_story=False):
    media_type = 'STORIES' if is_story else 'REELS'

    print("\n" + "=" * 60)
    print(f"INSTAGRAM {media_type} UPLOAD (Resumable Method)")
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
                print(f"[instagram] Facebook Page ID: {page_id}")
                ig_resp = requests.get(f"https://graph.facebook.com/{page_id}?fields=instagram_business_account&access_token={access_token}", timeout=10)
                if ig_resp.status_code == 200:
                    ig_account = ig_resp.json().get('instagram_business_account')
                    if ig_account:
                        ig_id = ig_account.get('id')
                        if ig_id != user_id:
                            print(f"[instagram] Found IG Business Account: {ig_id} (was: {user_id})")
                            user_id = ig_id
                    else:
                        print("[instagram] No Instagram Business Account connected to this Page")
                else:
                    print(f"[instagram] IG account fetch failed: {ig_resp.text[:200]}")
            else:
                print(f"[instagram] Page fetch failed: {me_resp.text[:200]}")
        except Exception as e:
            print(f"[instagram] IG ID fetch error: {e}")
    elif access_token.startswith('IGAA'):
        try:
            me_resp = requests.get(f"https://graph.facebook.com/me?fields=id,username&access_token={access_token}", timeout=10)
            if me_resp.status_code == 200:
                detected_id = me_resp.json().get('id')
                if detected_id and detected_id != user_id:
                    print(f"[instagram] Using detected ID: {detected_id}")
                    user_id = detected_id
        except Exception as e:
            print(f"[instagram] ID verify error: {e}")

    if not user_id:
        print("[instagram] Skipping - no user ID")
        return {'status': 'skipped', 'reason': 'Missing credentials', 'platform': 'instagram'}

    print(f"[instagram] Credentials loaded")

    video_path_obj = Path(video_path)
    if not video_path_obj.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    duration = get_video_duration(video_path_obj)
    if duration:
        print(f"[instagram] Video duration: {duration:.1f}s")
        if is_story and duration > 61.0:
            print(f"[instagram] Skipping Stories upload - video is {duration:.1f}s (max 61s)")
            return {'status': 'skipped', 'reason': f'Video too long for Stories', 'platform': 'instagram'}

    converted = reencode_for_ig(video_path_obj)
    upload_path = Path(converted)

    file_size = upload_path.stat().st_size
    file_size_mb = file_size / (1024 * 1024)
    print(f"[instagram] Video: {upload_path} ({file_size_mb:.2f} MB)")

    caption_limited = caption[:2200] if len(caption) > 2200 else caption
    print(f"[instagram] Caption: {len(caption_limited)} chars")

    try:
        api_base = "https://graph.facebook.com/v21.0"

        print(f"[instagram] Step 1: Starting resumable upload session...")
        session_params = {
            'upload_type': 'resumable',
            'access_token': access_token,
            'media_type': media_type,
            'caption': caption_limited,
            'file_size': file_size,
        }

        session_resp = requests.post(f"{api_base}/{user_id}/media", params=session_params, timeout=30)
        if session_resp.status_code != 200:
            error_msg = session_resp.json().get('error', {}).get('message', 'Unknown')
            raise Exception(f"Session creation failed: {error_msg}")

        session_data = session_resp.json()
        container_id = session_data.get('id')
        upload_uri = session_data.get('uri')
        print(f"[instagram] Container ID: {container_id}")
        print(f"[instagram] Upload URI: {upload_uri}")

        print(f"[instagram] Step 2: Uploading video binary directly...")
        with open(upload_path, 'rb') as f:
            video_data = f.read()

        upload_headers = {
            'Authorization': f'OAuth {access_token}',
            'offset': '0',
            'file_size': str(file_size),
            'Content-Type': 'application/octet-stream',
        }

        upload_resp = requests.post(upload_uri, headers=upload_headers, data=video_data, timeout=600)
        if upload_resp.status_code != 200:
            error_msg = upload_resp.text[:300]
            raise Exception(f"Binary upload failed ({upload_resp.status_code}): {error_msg}")
        print(f"[instagram] Binary upload complete!")

        print(f"[instagram] Step 3: Publishing immediately...")
        publish_resp = requests.post(f"{api_base}/{user_id}/media_publish", params={
            'creation_id': container_id,
            'access_token': access_token,
        }, timeout=60)

        if publish_resp.status_code != 200:
            error_msg = publish_resp.json().get('error', {}).get('message', 'Unknown')
            raise Exception(f"Publish failed: {error_msg}")

        media_id = publish_resp.json().get('id')
        print(f"[instagram] SUCCESS! Media ID: {media_id}")

        return {'id': media_id, 'platform': 'instagram', 'status': 'success'}

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
