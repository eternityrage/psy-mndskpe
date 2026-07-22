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

    file_size_mb = video_path_obj.stat().st_size / (1024 * 1024)
    print(f"[instagram] Video: {video_path} ({file_size_mb:.2f} MB)")

    caption_limited = caption[:2200] if len(caption) > 2200 else caption
    print(f"[instagram] Caption: {len(caption_limited)} chars")

    api_base = "https://graph.facebook.com/v21.0"

    try:
        print(f"[instagram] Step 1: Uploading to temporary hosting...")
        with open(video_path_obj, 'rb') as f:
            upload_resp = requests.post(
                'https://catbox.moe/user/api.php',
                data={'reqtype': 'fileupload'},
                files={'fileToUpload': (video_path_obj.name, f)},
                timeout=120
            )
        if upload_resp.status_code != 200:
            raise Exception(f"Host upload failed: {upload_resp.status_code}")

        video_url = upload_resp.text.strip()
        print(f"[instagram] Video URL: {video_url}")

        print(f"[instagram] Step 2: Creating {media_type} container...")
        container_params = {'media_type': media_type, 'video_url': video_url, 'access_token': access_token}
        if media_type != 'STORIES':
            container_params['caption'] = caption_limited

        container_resp = requests.post(f"{api_base}/{user_id}/media", params=container_params, timeout=60)
        if container_resp.status_code != 200:
            error_msg = container_resp.json().get('error', {}).get('message', 'Unknown')
            raise Exception(f"Container creation failed: {error_msg}")

        container_id = container_resp.json().get('id')
        print(f"[instagram] Container: {container_id}")

        print(f"[instagram] Step 3: Processing video...")
        max_wait = 210
        waited = 0
        while waited < max_wait:
            status_resp = requests.get(f"{api_base}/{container_id}", params={
                'fields': 'status_code,status', 'access_token': access_token
            }, timeout=30)
            status_data = status_resp.json()
            status_code = status_data.get('status_code') or status_data.get('status', 'UNKNOWN')
            print(f"[instagram] Status: {status_code} (waited {waited}s)")
            if status_code == 'FINISHED':
                print(f"[instagram] Processing complete!")
                break
            elif status_code == 'ERROR':
                error_msg = status_data.get('error_message', 'Video processing failed')
                raise Exception(f"{error_msg}")
            time.sleep(30)
            waited += 30

        if waited >= max_wait:
            raise Exception("Video processing timed out")

        print(f"[instagram] Step 4: Publishing...")
        publish_resp = requests.post(f"{api_base}/{user_id}/media_publish", params={
            'creation_id': container_id, 'access_token': access_token
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
