import os
import requests
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path, override=True)


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

    file_size = video_path_obj.stat().st_size
    file_size_mb = file_size / (1024 * 1024)
    print(f"[instagram] Video: {video_path} ({file_size_mb:.2f} MB)")

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
        with open(video_path_obj, 'rb') as f:
            video_data = f.read()

        upload_headers = {
            'Authorization': f'OAuth {access_token}',
            'offset': '0',
            'file_size': str(file_size),
            'Content-Type': 'application/octet-stream',
        }

        upload_resp = requests.post(upload_uri, headers=upload_headers, data=video_data, timeout=300)
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
