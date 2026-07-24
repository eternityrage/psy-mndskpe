"""
Robust Instagram Reel & Story Uploader via Meta Graph API v21.0
Supports container creation, status checking, and media publishing.
"""
import os, sys, time, json, requests, pathlib, subprocess, base64

def mask(s):
    return f"{s[:10]}...{s[-4:]}" if s and len(s) > 10 else "MISSING"

def upload_video_to_github(video_path_obj):
    repo_full = os.getenv('GITHUB_REPOSITORY')
    if not repo_full:
        raise ValueError("GITHUB_REPOSITORY env var missing")
    owner, repo = repo_full.split('/')
    token = os.getenv('GITHUB_TOKEN')
    
    with open(video_path_obj, 'rb') as f:
        file_bytes = f.read()
    
    file_b64 = base64.b64encode(file_bytes).decode('ascii')
    filename = f"temp_ig_{video_path_obj.stem}_{int(time.time())}.mp4"
    remote_path = f"output/{filename}"
    branch = "main"
    
    h = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json'}
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{remote_path}"
    
    put_r = requests.put(url, headers=h, json={
        'message': f'Temp IG upload {filename}',
        'content': file_b64,
        'branch': branch
    }, timeout=60)
    
    if put_r.status_code not in (200, 201):
        raise Exception(f"GitHub temp upload failed ({put_r.status_code}): {put_r.text[:300]}")
    
    raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{remote_path}"
    return raw_url, owner, repo, token, remote_path, branch

def delete_github_temp_file(owner, repo, token, remote_path, branch):
    try:
        h = {'Authorization': f'Bearer {token}', 'Accept': 'application/vnd.github+json'}
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{remote_path}"
        g_r = requests.get(url, headers=h, params={'ref': branch}, timeout=10)
        if g_r.status_code == 200:
            sha = g_r.json()['sha']
            requests.delete(url, headers=h, json={'message': 'Cleanup temp IG file', 'sha': sha, 'branch': branch}, timeout=10)
    except Exception:
        pass

def upload_to_instagram(video_path, caption="", is_story=False):
    media_type = 'STORIES' if is_story else 'REELS'
    print("\n" + "=" * 60)
    print(f"INSTAGRAM {media_type} UPLOAD (Graph API v21.0)")
    print("=" * 60)

    access_token = (os.getenv('INSTAGRAM_ACCESS_TOKEN') or 
                    os.getenv('IG_ACCESS_TOKEN') or 
                    os.getenv('FACEBOOK_ACCESS_TOKEN') or 
                    os.getenv('FB_ACCESS_TOKEN'))
    
    user_id = (os.getenv('INSTAGRAM_ACCOUNT_ID') or 
               os.getenv('IG_USER_ID'))

    if not access_token:
        print("[instagram] ⚠️ Skipping - missing access token")
        return {'status': 'skipped', 'reason': 'Missing access token', 'platform': 'instagram'}

    fb_page_id = os.getenv('FACEBOOK_PAGE_ID') or os.getenv('FB_PAGE_ID')
    if not user_id and fb_page_id:
        try:
            print(f"[instagram] User ID missing - querying Meta Graph API for Page {fb_page_id}...")
            ig_r = requests.get(
                f"https://graph.facebook.com/v21.0/{fb_page_id}?fields=instagram_business_account&access_token={access_token}",
                timeout=15
            )
            if ig_r.status_code == 200:
                acct = ig_r.json().get('instagram_business_account')
                if acct and acct.get('id'):
                    user_id = acct['id']
                    print(f"[instagram] Found Instagram Business Account ID: {user_id}")
        except Exception as e:
            print(f"[instagram] IG ID lookup error: {e}")

    if not user_id:
        print("[instagram] ⚠️ Skipping - no Instagram Business Account connected to this Page")
        return {'status': 'skipped', 'reason': 'No Instagram Business Account', 'platform': 'instagram'}

    print(f"[instagram] Account ID: {user_id}")
    print(f"[instagram] Access Token: {mask(access_token)}")

    video_path_obj = pathlib.Path(video_path)
    if not video_path_obj.exists():
        print(f"[instagram] ❌ Video file not found: {video_path}")
        return {'status': 'failed', 'error': 'Video file not found', 'platform': 'instagram'}

    print("[instagram] Step 1: Generating public video URL via GitHub Raw...")
    raw_url, owner, repo, gh_token, remote_path, branch = upload_video_to_github(video_path_obj)
    print(f"[instagram] Video URL: {raw_url}")

    try:
        print(f"[instagram] Step 2: Creating {media_type} container on Meta Graph API...")
        api_base = "https://graph.facebook.com/v21.0"
        params = {
            'media_type': 'STORIES' if is_story else 'REELS',
            'video_url': raw_url,
            'caption': caption[:2200] if caption else '',
            'access_token': access_token
        }
        if not is_story:
            params['share_to_feed'] = False

        c_res = requests.post(f"{api_base}/{user_id}/media", params=params, timeout=60)
        if c_res.status_code not in (200, 201):
            err = c_res.json().get('error', {}).get('message', c_res.text)
            raise Exception(f"Container creation failed: {err}")

        container_id = c_res.json().get('id')
        print(f"[instagram] ✅ Container Created: {container_id}")

        print("[instagram] Step 3: Waiting for video container processing...")
        time.sleep(15)

        print("[instagram] Step 4: Publishing Reel...")
        pub_res = requests.post(
            f"{api_base}/{user_id}/media_publish",
            params={'creation_id': container_id, 'access_token': access_token},
            timeout=60
        )

        if pub_res.status_code in (200, 201):
            media_id = pub_res.json().get('id', container_id)
            print(f"[instagram] ✅ SUCCESS! Media ID: {media_id}")
            print(f"INSTAGRAM: SUCCESS (ID: {media_id})")
            delete_github_temp_file(owner, repo, gh_token, remote_path, branch)
            return {'status': 'success', 'id': media_id, 'platform': 'instagram'}
        else:
            print(f"[instagram] Publish pending - retrying in 15s...")
            time.sleep(15)
            pub_res2 = requests.post(
                f"{api_base}/{user_id}/media_publish",
                params={'creation_id': container_id, 'access_token': access_token},
                timeout=60
            )
            if pub_res2.status_code in (200, 201):
                media_id = pub_res2.json().get('id', container_id)
                print(f"[instagram] ✅ SUCCESS! Media ID: {media_id}")
                print(f"INSTAGRAM: SUCCESS (ID: {media_id})")
                delete_github_temp_file(owner, repo, gh_token, remote_path, branch)
                return {'status': 'success', 'id': media_id, 'platform': 'instagram'}
            else:
                err = pub_res2.json().get('error', {}).get('message', pub_res2.text)
                raise Exception(f"Publish failed: {err}")

    except Exception as e:
        print(f"[instagram] ❌ Error: {e}")
        delete_github_temp_file(owner, repo, gh_token, remote_path, branch)
        return {'status': 'failed', 'error': str(e), 'platform': 'instagram'}
