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
        print(f"[ig] Compressing {sz_mb:.0f}MB -> CRF{crf}...")
        subprocess.run(['ffmpeg','-i',str(path),'-c:v','libx264','-preset','medium','-crf',str(crf),'-vf','scale=1080:1920:force_original_aspect_ratio=decrease,pad=1080:1920:(ow-iw)/2:(oh-ih)/2','-c:a','aac','-b:a','128k','-movflags','+faststart','-y',str(out)],capture_output=True,text=True,timeout=300)
        ns=out.stat().st_size/1048576; b64=ns*1.37
        print(f"[ig] CRF{crf}: {ns:.0f}MB (b64 ~{b64:.0f}MB)")
        if b64<50: return str(out)
    return str(out)

def upload_git(cp,repo,token):
    rp='output/temp/ig_video.mp4'; h={'Authorization':f'Bearer {token}','Accept':'application/vnd.github+json'}
    with open(cp,'rb') as f: b64=base64.b64encode(f.read()).decode()
    r=requests.get(f'https://api.github.com/repos/{repo}/contents/{rp}',headers=h)
    sha=r.json().get('sha') if r.status_code==200 else None
    data={'message':f'ig {int(time.time())}','content':b64,'branch':'main'}
    if sha: data['sha']=sha
    r2=requests.put(f'https://api.github.com/repos/{repo}/contents/{rp}',headers=h,json=data,timeout=120)
    if r2.status_code not in (200,201): raise Exception(f"GitHub: {r2.status_code} {r2.text[:80]}")
    o,n=repo.split('/'); return f'https://raw.githubusercontent.com/{o}/{n}/main/{rp}'

def publish(uid,at,vurl,cap,media_type):
    base="https://graph.facebook.com/v21.0"
    p={'media_type':media_type,'video_url':vurl,'access_token':at}
    if media_type!='STORIES': p['caption']=cap
    cr=requests.post(f"{base}/{uid}/media",params=p,timeout=60)
    if cr.status_code not in (200,201): raise Exception(f"Container: {cr.text[:200]}")
    cid=cr.json().get('id'); print(f"[ig] Container: {cid}")
    waited=0
    while waited<300:
        sr=requests.get(f"{base}/{cid}",params={'fields':'status_code,status','access_token':at},timeout=30).json()
        sc=sr.get('status_code') or sr.get('status','UNKNOWN'); print(f"[ig] Status: {sc} ({waited}s)")
        if sc in ('FINISHED','FINISH'): break
        elif sc=='ERROR': raise Exception(sr.get('error_message','?'))
        time.sleep(30); waited+=30
    if waited>=300: raise Exception("Timed out")
    pp=requests.post(f"{base}/{uid}/media_publish",params={'creation_id':cid,'access_token':at},timeout=60)
    if pp.status_code!=200: raise Exception(f"Publish: {pp.text[:200]}")
    mid=pp.json().get('id'); print(f"[ig] SUCCESS! Media ID: {mid}"); return mid

def upload_to_instagram(video_path, caption, is_story=False):
    media_type='STORIES' if is_story else 'REELS'
    print("\n"+"="*60); print(f"INSTAGRAM {media_type} UPLOAD"); print("="*60)
    at=os.getenv('INSTAGRAM_ACCESS_TOKEN') or os.getenv('FACEBOOK_ACCESS_TOKEN')
    uid=os.getenv('INSTAGRAM_ACCOUNT_ID') or os.getenv('IG_USER_ID')
    print(f"[ig] Token: {'SET' if at else 'MISSING'}")
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
    cap=caption[:2200] if len(caption)>2200 else caption; print(f"[ig] Caption: {len(cap)} chars")

    for attempt in range(2):
        try:
            print(f"[ig] Resumable attempt {attempt+1}...")
            sp=requests.post(f"https://graph.facebook.com/v21.0/{uid}/media",params={'upload_type':'resumable','access_token':at,'media_type':media_type,'caption':cap,'file_size':sz},timeout=30)
            if sp.status_code!=200: raise Exception(sp.json().get('error',{}).get('message','?'))
            d=sp.json()
            with open(cp,'rb') as f: data=f.read()
            up=requests.post(d['uri'],headers={'Authorization':f'OAuth {at}','offset':'0','file_size':str(sz),'Content-Type':'application/octet-stream'},data=data,timeout=600)
            if up.status_code==200:
                pp=requests.post(f"https://graph.facebook.com/v21.0/{uid}/media_publish",params={'creation_id':d['id'],'access_token':at},timeout=60)
                if pp.status_code==200: mid=pp.json()['id']; print(f"[ig] SUCCESS! Media ID: {mid}"); return {'id':mid,'status':'success'}
            raise Exception("Upload failed")
        except Exception as e: print(f"[ig] Resumable {attempt+1}: {str(e)[:50]}")

    repo=os.environ.get('GITHUB_REPOSITORY'); token=os.environ.get('GITHUB_TOKEN')
    if repo and token:
        try:
            print(f"[ig] GitHub URL...")
            vurl=upload_git(cp,repo,token); print(f"[ig] URL: {vurl}")
            mid=publish(uid,at,vurl,cap,media_type)
            return {'id':mid,'status':'success'}
        except Exception as e: print(f"[ig] GitHub: {str(e)[:60]}")
    raise Exception("All methods failed")

if __name__=='__main__':
    f=Path('final_video.mp4')
    if f.exists():
        try: print(upload_to_instagram(str(f),"Test"))
        except Exception as e: print(f"Failed: {e}")