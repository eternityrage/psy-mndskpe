import os
import subprocess
import tempfile
import requests
import time
import base64
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


def ensure_compatible_format(video_path):
    path = Path(video_path)
    temp_dir = Path(tempfile.gettempdir()) / "ig_convert"
    temp_dir.mkdir(parents=True, exist_ok=True)
    converted = temp_dir / f"converted_{path.stem}.mp4"

    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-select_streams', 'v:0',
             '-show_entries', 'stream=codec_name',
             '-of', 'default=noprint_wrappers=1:nokey=1', str(path)],
            capture_output=True, text=True, timeout=15
        )
        codec = result.stdout.strip() if result.returncode == 0 else ""
    except Exception:
        codec = ""

    if codec == "h264":
        print(f"[instagram] Video already H.264, no conversion needed")
        return str(path)

    print(f"[instagram] Converting video (codec: {codec or 'unknown'}) to H.264...")
    try:
        subprocess.run(
            ['ffmpeg', '-i', str(path), '-c:v', 'libx264', '-preset', 'fast',
             '-crf', '23', '-c:a', 'aac', '-movflags', '+faststart',
             '-y', str(converted)],
            capture_output=True, text=True, timeout=300
        )
        print(f"[instagram] Converted to: {converted}")
        return str(converted)
    except subprocess.TimeoutExpired:
        print(f"[instagram] Conversion timed out, using original")
        return str(path)
    except Exception as e:
        print(f"[instagram] Conversion failed ({e}), using original")
        return str(path)


def upload_resumable(api_base, user_id, access_token, media_type, caption, upload_path):
    """Try resumable upload method first."""
    file_size = Path(upload_path).stat().st_size

    print(f"[instagram] Step 1: Starting resumable upload session...")
    session_params = {
        'upload_type': 'resumable',
        'access_token': access_token,
        'media_type': media_type,
        'caption': caption,
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
        error_msg = upload_resp.text[:500]
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
    return media_id


def upload_via_url(api_base, user_id, access_token, media_type, caption, upload_path):
    """Fallback: upload via GitHub raw URL (old method)."""
    repo = os.environ.get('GITHUB_REPOSITORY')
    token = os.environ.get('GITHUB_TOKEN')
    if not repo or not token:
        raise Exception("GITHUB_REPOSITORY or GITHUB_TOKEN not set")

    print(f"[instagram] Fallback: uploading to GitHub raw content...")
    h = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json'}
    remote_path = 'output/temp/video.mp4'
    branch = 'main'

    with open(upload_path, 'rb') as f:
        content_b64 = base64.b64encode(f.read()).decode()

    r = requests.get(f'https://api.github.com/repos/{repo}/contents/{remote_path}', headers=h)
    sha = r.json().get('sha') if r.status_code == 200 else None

    data = {'message': f'temp video {int(time.time())}', 'content': content_b64, 'branch': branch}
    if sha:
        data['sha'] = sha

    r2 = requests.put(f'https://api.github.com/repos/{repo}/contents/{remote_path}', headers=h, json=data)
    if r2.status_code not in (200, 201):
        raise Exception(f"GitHub upload failed ({r2.status_code})")

    owner, name = repo.split('/')
    video_url = f'https://raw.githubusercontent.com/{owner}/{name}/{branch}/{remote_path}'
    print(f"[instagram] GitHub URL: {video_url}")

    print(f"[instagram] Creating {media_type} container via URL...")
    container_params = {'media_type': media_type, 'video_url': video_url, 'access_token': access_token}
    if not (media_type == 'STORIES'):
        container_params['caption'] = caption

    container_resp = requests.post(f"{api_base}/{user_id}/media", params=container_params, timeout=60)
    if container_resp.status_code != 200:
        error_msg = container_resp.json().get('error', {}).get('message', 'Unknown')
        raise Exception(f"Container creation failed: {error_msg}")

    container_id = container_resp.json().get('id')
    print(f"[instagram] Container: {container_id}")

    print(f"[instagram] Processing...")
    max_wait = 180
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

    print(f"[instagram] Publishing...")
    publish_resp = requests.post(f"{api_base}/{user_id}/media_publish", params={
        'creation_id': container_id, 'access_token': access_token
    }, timeout=60)
    if publish_resp.status_code != 200:
        error_msg = publish_resp.json().get('error', {}).get('message', 'Unknown')
        raise Exception(f"Publish failed: {error_msg}")

    media_id = publish_resp.json().get('id')
    print(f"[instagram] SUCCESS! Media ID: {media_id}")

    # Cleanup temp file from GitHub
    h2 = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json'}
    r_clean = requests.get(f'https://api.github.com/repos/{repo}/contents/{remote_path}', headers=h2)
    if r_clean.status_code == 200:
        sha_clean = r_clean.json()['sha']
        requests.delete(f'https://api.github.com/repos/{repo}/contents/{remote_path}',
                        headers=h2, json={'message': 'cleanup', 'sha': sha_clean, 'branch': branch})

    return media_id


def upload_to_instagram(video_path, caption, is_story=False):
    media_type = 'STORIES' if is_story else 'REELS'

    video_path_obj = Path(video_path)
    if not video_path_obj.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    duration = get_video_duration(video_path_obj)
    if duration:
        print(f"[instagram] Video duration: {duration:.1f}s")
        max_story_duration = 61.0
        if is_story and duration > max_story_duration:
            print(f"[instagram] Skipping Stories upload — video is {duration:.1f}s (max {max_story_duration:.0f}s)")
            return {'status': 'skipped', 'reason': f'Video too long for Stories ({duration:.1f}s > {max_story_duration:.0f}s)', 'platform': 'instagram'}
    else:
        print("[instagram] Could not determine video duration, proceeding anyway")

    converted_path = ensure_compatible_format(video_path_obj)

    print("\n" + "=" * 60)
    print(f"INSTAGRAM {media_type} UPLOAD (Resumable + URL Fallback)")
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
                            user_id = ig_id
                else:
                    print(f"[instagram] IG account fetch failed")
            else:
                print(f"[instagram] Page fetch failed")
        except Exception as e:
            print(f"[instagram] IG ID fetch error: {e}")

    if not user_id:
        print("[instagram] Skipping - no user ID")
        return {'status': 'skipped', 'reason': 'Missing credentials', 'platform': 'instagram'}

    print(f"[instagram] Credentials loaded")

    upload_path = Path(converted_path)
    file_size_mb = upload_path.stat().st_size / (1024 * 1024)
    print(f"[instagram] Video: {converted_path} ({file_size_mb:.2f} MB)")

    caption_limited = caption[:2200] if len(caption) > 2200 else caption
    print(f"[instagram] Caption: {len(caption_limited)} chars")

    api_base = "https://graph.facebook.com/v21.0"

    # Try resumable first, fall back to URL method
    try:
        media_id = upload_resumable(api_base, user_id, access_token, media_type, caption_limited, upload_path)
        return {'id': media_id, 'platform': 'instagram', 'status': 'success'}
    except Exception as e:
        error_str = str(e)
        print(f"[instagram] Resumable method failed: {error_str[:100]}")
        print(f"[instagram] Falling back to URL-based upload method...")
        try:
            media_id = upload_via_url(api_base, user_id, access_token, media_type, caption_limited, upload_path)
            return {'id': media_id, 'platform': 'instagram', 'status': 'success'}
        except Exception as e2:
            print(f"[instagram] URL method also failed: {e2}")
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
