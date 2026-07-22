import os, requests, time, subprocess, tempfile, base64
from pathlib import Path
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path, override=True)

def get_dur(p):
    try:
        r=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(p)],capture_output=True,text=True,timeout=30)
        if r.returncode==0 and r.stdout.strip(): return float(r.stdout.strip())
    except: pass
    return None

def compress(p):
    path=Path(p); out=Path(tempfile.gettempdir())/"ig_out"/f"cmp_{path.stem}.mp4"
    out.parent.mkdir(parents=True,exist_ok=True)
    sz_mb=path.stat().st_size/1048576
    if sz_mb<20: print(f"[ig] No compression ({sz_mb:.0f}MB)"); return str(path)
    for crf in [23, 26, 28, 30]:
        print(f"[ig] Compress CRF{crf}...")
        subprocess.run(['ffmpeg','-i',str(path),'-c:v','libx264','-preset','medium','-crf',str(crf),'-vf','scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2','-c:a','aac','-b:a','128k','-movflags','+faststart','-y',str(out)],capture_output=True,text=True,timeout=300)
        ns=out.stat().st_size/1048576
        print(f"[ig] CRF{crf}: {ns:.0f}MB")
        if ns*1.37<25: return str(out)
    return str(out)

def upload_to_instagram(video_path, caption, is_story=False):
    media_type='STORIES' if is_story else 'REELS'
    print(f"\nINSTAGRAM {media_type} UPLOAD (GitHub URL)")
    at=os.getenv('INSTAGRAM_ACCESS_TOKEN') or os.getenv('FACEBOOK_ACCESS_TOKEN')
    uid=os.getenv('INSTAGRAM_ACCOUNT_ID') or os.getenv('IG_USER_ID')
    if not at or not uid: return {'status':'skipped'}
    if at.startswith('EAAM'):
        try:
            me=requests.get(f"https://graph.facebook.com/me?fields=id,name&access_token={at}",timeout=10).json()
            ig=requests.get(f"https://graph.facebook.com/{me['id']}?fields=instagram_business_account&access_token={at}",timeout=10).json()
            if ig.get('instagram_business_account'): uid=ig['instagram_business_account']['id']
        except: pass
    p=Path(video_path)
    if not p.exists(): raise FileNotFoundError(str(p))
    dur=get_dur(p)
    if dur:
        print(f"[ig] Duration: {dur:.0f}s")
        if is_story and dur>61: print(f"[ig] Skipping Stories"); return {'status':'skipped','reason':'duration'}
    compressed=compress(p); cp=Path(compressed)
    sz=cp.stat().st_size; print(f"[ig] Final: {cp.name} ({sz/1048576:.0f}MB)")
    cap=caption[:2200] if len(caption)>2200 else caption

    # API 1: Upload to GitHub
    repo=os.environ.get('GITHUB_REPOSITORY'); token=os.environ.get('GITHUB_TOKEN')
    if not repo or not token: raise Exception("No GITHUB_TOKEN")
    rp='output/temp/ig_video.mp4'; h={'Authorization':f'Bearer {token}','Accept':'application/vnd.github+json'}
    with open(cp,'rb') as f: b64=base64.b64encode(f.read()).decode()
    r=requests.get(f'https://api.github.com/repos/{repo}/contents/{rp}',headers=h)
    sha=r.json().get('sha') if r.status_code==200 else None
    data={'message':f'ig {int(time.time())}','content':b64,'branch':'main'}
    if sha: data['sha']=sha
    r2=requests.put(f'https://api.github.com/repos/{repo}/contents/{rp}',headers=h,json=data,timeout=120)
    if r2.status_code not in (200,201): raise Exception(f"GitHub upload failed")
    o,n=repo.split('/')
    vurl=f'https://raw.githubusercontent.com/{o}/{n}/main/{rp}'
    print(f"[ig] URL: {vurl}")

    # API 2: Create container
    base="https://graph.facebook.com/v21.0"
    cr=requests.post(f"{base}/{uid}/media",params={'media_type':media_type,'video_url':vurl,'caption':cap,'access_token':at},timeout=60)
    if cr.status_code not in (200,201): raise Exception(f"Container failed")
    cid=cr.json().get('id')
    print(f"[ig] Container: {cid}")

    # No polling - wait fixed time for Instagram to download
    wait_time=90 if media_type!='STORIES' else 60
    print(f"[ig] Waiting {wait_time}s for processing (no polling)...")
    time.sleep(wait_time)

    # API 3: Publish (try once, retry once if fails)
    for attempt in range(2):
        pp=requests.post(f"{base}/{uid}/media_publish",params={'creation_id':cid,'access_token':at},timeout=60)
        if pp.status_code==200:
            mid=pp.json().get('id')
            print(f"[ig] SUCCESS! Media ID: {mid}")
            # Cleanup GitHub temp file
            requests.delete(f'https://api.github.com/repos/{repo}/contents/{rp}',headers=h,json={'message':'cleanup','sha':sha,'branch':'main'})
            return {'id':mid,'status':'success'}
        print(f"[ig] Publish attempt {attempt+1} failed, retrying in 30s...")
        time.sleep(30)
    raise Exception("Publish failed")

if __name__=='__main__':
    f=Path('final_video.mp4')
    if f.exists():
        try: print(upload_to_instagram(str(f),"Test"))
        except Exception as e: print(f"Failed: {e}")