import os, requests, subprocess, time
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path, override=True)

def get_video_duration(video_path):
    try:
        r = subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(video_path)],capture_output=True,text=True,timeout=30)
        if r.returncode == 0 and r.stdout.strip():
            return float(r.stdout.strip())
    except: pass
    return None

def upload_to_instagram(video_path, caption, is_story=False):
    media_type = 'STORIES' if is_story else 'REELS'
    print("\n" + "="*60)
    print(f"INSTAGRAM {media_type} UPLOAD (Resumable Method)")
    print("="*60)

    access_token = os.getenv('INSTAGRAM_ACCESS_TOKEN') or os.getenv('FACEBOOK_ACCESS_TOKEN')
    user_id = os.getenv('INSTAGRAM_ACCOUNT_ID') or os.getenv('IG_USER_ID')

    def mask(s): return f"{s[:10]}...{s[-4:]}" if s and len(s)>10 else ("PLACEHOLDER" if s=="***" else "MISSING")
    print(f"[instagram] User ID Provided: {user_id}")
    print(f"[instagram] Access Token: {mask(access_token)}")

    if not access_token:
        print("[instagram] Skipping - no token")
        return {'status':'skipped','reason':'Missing credentials','platform':'instagram'}

    if access_token.startswith('EAAM'):
        print("[instagram] EAAM token detected, resolving Instagram Business Account ID...")
        try:
            me = requests.get(f"https://graph.facebook.com/me?fields=id,name&access_token={access_token}",timeout=10)
            if me.status_code==200:
                pid = me.json().get('id')
                ig = requests.get(f"https://graph.facebook.com/{pid}?fields=instagram_business_account&access_token={access_token}",timeout=10)
                if ig.status_code==200:
                    acct = ig.json().get('instagram_business_account')
                    if acct: user_id = acct.get('id')
        except: pass

    if not user_id:
        print("[instagram] Skipping - no user ID")
        return {'status':'skipped','reason':'Missing credentials','platform':'instagram'}

    print(f"[instagram] Credentials loaded")

    p = Path(video_path)
    if not p.exists():
        raise FileNotFoundError(f"Video not found: {video_path}")

    dur = get_video_duration(p)
    if dur:
        print(f"[instagram] Video duration: {dur:.1f}s")
        if is_story and dur > 61.0:
            print(f"[instagram] Skipping Stories upload - video is {dur:.1f}s (max 61s)")
            return {'status':'skipped','reason':'Video too long for Stories','platform':'instagram'}

    sz = p.stat().st_size
    print(f"[instagram] Video: {p} ({sz/1024/1024:.2f} MB)")
    cap = caption[:2200] if len(caption)>2200 else caption
    print(f"[instagram] Caption: {len(cap)} chars")

    api_base = "https://graph.facebook.com/v21.0"
    try:
        print(f"[instagram] Step 1: Starting resumable upload session...")
        sp = requests.post(f"{api_base}/{user_id}/media",params={'upload_type':'resumable','access_token':access_token,'media_type':media_type,'caption':cap,'file_size':sz},timeout=30)
        if sp.status_code!=200: raise Exception(f"Session failed: {sp.json().get('error',{}).get('message','Unknown')}")
        d = sp.json()
        cid, uri = d.get('id'), d.get('uri')
        print(f"[instagram] Container ID: {cid}")
        print(f"[instagram] Upload URI: {uri}")

        print(f"[instagram] Step 2: Uploading video binary directly...")
        with open(p,'rb') as f: data = f.read()
        up = requests.post(uri,headers={'Authorization':f'OAuth {access_token}','offset':'0','file_size':str(sz),'Content-Type':'application/octet-stream'},data=data,timeout=600)
        if up.status_code!=200: raise Exception(f"Binary upload failed ({up.status_code})")
        print(f"[instagram] Binary upload complete!")

        print(f"[instagram] Step 3: Publishing immediately...")
        pp = requests.post(f"{api_base}/{user_id}/media_publish",params={'creation_id':cid,'access_token':access_token},timeout=60)
        if pp.status_code!=200: raise Exception(f"Publish failed: {pp.json().get('error',{}).get('message','Unknown')}")
        mid = pp.json().get('id')
        print(f"[instagram] SUCCESS! Media ID: {mid}")
        return {'id':mid,'platform':'instagram','status':'success'}
    except Exception as e:
        print(f"[instagram] ERROR: {e}")
        raise

if __name__=='__main__':
    f=Path('final_video.mp4')
    if f.exists():
        try: print(upload_to_instagram(str(f),"Test"))
        except Exception as e: print(f"Failed: {e}")
