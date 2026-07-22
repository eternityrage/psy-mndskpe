import os, requests, time, subprocess, tempfile, base64
from pathlib import Path
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(dotenv_path=env_path, override=True)

def get_dur(p):
    try:
        r = subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(p)],capture_output=True,text=True,timeout=30)
        if r.returncode==0 and r.stdout.strip(): return float(r.stdout.strip())
    except: pass
    return None

def compress(p):
    path = Path(p)
    out = Path(tempfile.gettempdir()) / "ig_out" / f"cmp_{path.stem}.mp4"
    out.parent.mkdir(parents=True,exist_ok=True)
    sz_mb = path.stat().st_size / 1048576
    if sz_mb < 25:
        print(f"[ig] Video already {sz_mb:.0f}MB, skipping compress")
        return str(path)
    print(f"[ig] Compressing {sz_mb:.0f}MB -> target <25MB...")
    try:
        subprocess.run(['ffmpeg','-i',str(path),'-c:v','libx264','-preset','fast','-crf','28','-vf','scale=720:1280:force_original_aspect_ratio=decrease,pad=720:1280:(ow-iw)/2:(oh-ih)/2','-c:a','aac','-b:a','64k','-movflags','+faststart','-y',str(out)],capture_output=True,text=True,timeout=300)
        ns = out.stat().st_size/1048576
        print(f"[ig] Compressed to {ns:.0f}MB")
        return str(out)
    except Exception as e:
        print(f"[ig] Compress failed: {e}, using original")
        return str(p)

def upload_to_instagram(video_path, caption, is_story=False):
    media_type = 'STORIES' if is_story else 'REELS'
    print("\n"+ "="*60)
    print(f"INSTAGRAM {media_type} UPLOAD")
    print("="*60)
    at = os.getenv('INSTAGRAM_ACCESS_TOKEN') or os.getenv('FACEBOOK_ACCESS_TOKEN')
    uid = os.getenv('INSTAGRAM_ACCOUNT_ID') or os.getenv('IG_USER_ID')
    print(f"[ig] Token: {'SET' if at else 'MISSING'} | User: {uid}")
    if not at or not uid: return {'status':'skipped','platform':'instagram'}
    if at.startswith('EAAM'):
        try:
            me=requests.get(f"https://graph.facebook.com/me?fields=id,name&access_token={at}",timeout=10).json()
            pid=me.get('id')
            ig=requests.get(f"https://graph.facebook.com/{pid}?fields=instagram_business_account&access_token={at}",timeout=10).json()
            acct=ig.get('instagram_business_account')
            if acct: uid=acct.get('id')
        except: pass
    p=Path(video_path)
    if not p.exists(): raise FileNotFoundError(str(p))
    dur=get_dur(p)
    if dur:
        print(f"[ig] Duration: {dur:.0f}s")
        if is_story and dur>61:
            print(f"[ig] Skipping Stories ({dur:.0f}s > 61s)")
            return {'status':'skipped','reason':'duration','platform':'instagram'}
    compressed=compress(p)
    cp=Path(compressed)
    sz=cp.stat().st_size
    print(f"[ig] Video: {cp.name} ({sz/1048576:.0f}MB)")
    cap=caption[:2200] if len(caption)>2200 else caption
    print(f"[ig] Caption: {len(cap)} chars")

    # Method 1: Try resumable first
    try:
        print(f"[ig] Method 1: Resumable upload...")
        sp=requests.post(f"https://graph.facebook.com/v21.0/{uid}/media",params={'upload_type':'resumable','access_token':at,'media_type':media_type,'caption':cap,'file_size':sz},timeout=30)
        if sp.status_code!=200: raise Exception(sp.json().get('error',{}).get('message','?'))
        d=sp.json()
        uri=d.get('uri')
        print(f"[ig] Upload URI: {uri}")
        with open(cp,'rb') as f: data=f.read()
        up=requests.post(uri,headers={'Authorization':f'OAuth {at}','offset':'0','file_size':str(sz),'Content-Type':'application/octet-stream'},data=data,timeout=600)
        if up.status_code==200:
            pp=requests.post(f"https://graph.facebook.com/v21.0/{uid}/media_publish",params={'creation_id':d.get('id'),'access_token':at},timeout=60)
            if pp.status_code==200:
                mid=pp.json().get('id')
                print(f"[ig] SUCCESS! Media ID: {mid}")
                return {'id':mid,'platform':'instagram','status':'success'}
        raise Exception(f"Binary upload failed ({up.status_code})")
    except Exception as e:
        print(f"[ig] Resumable failed: {str(e)[:80]}")
    
    # Method 2: GitHub URL method
    try:
        print(f"[ig] Method 2: GitHub URL upload...")
        repo=os.environ.get('GITHUB_REPOSITORY')
        token=os.environ.get('GITHUB_TOKEN')
        if not repo or not token: raise Exception("No GITHUB_TOKEN")
        rp='output/temp/ig_video.mp4'
        branch='main'
        h={'Authorization':f'Bearer {token}','Accept':'application/vnd.github+json'}
        with open(cp,'rb') as f: b64=base64.b64encode(f.read()).decode()
        r=requests.get(f'https://api.github.com/repos/{repo}/contents/{rp}',headers=h)
        sha=r.json().get('sha') if r.status_code==200 else None
        data={'message':f'ig video {int(time.time())}','content':b64,'branch':branch}
        if sha: data['sha']=sha
        r2=requests.put(f'https://api.github.com/repos/{repo}/contents/{rp}',headers=h,json=data)
        if r2.status_code not in (200,201): raise Exception(f"GitHub upload failed ({r2.status_code})")
        owner,name=repo.split('/')
        vurl=f'https://raw.githubusercontent.com/{owner}/{name}/{branch}/{rp}'
        print(f"[ig] URL: {vurl}")
        cp2={'media_type':media_type,'video_url':vurl,'access_token':at}
        if media_type!='STORIES': cp2['caption']=cap
        cr=requests.post(f"https://graph.facebook.com/v21.0/{uid}/media",params=cp2,timeout=60)
        if cr.status_code not in (200,201): raise Exception(f"Container failed: {cr.json().get('error',{}).get('message','?')}")
        cid=cr.json().get('id')
        print(f"[ig] Container: {cid}")
        waited=0
        while waited<180:
            sr=requests.get(f"https://graph.facebook.com/v21.0/{cid}",params={'fields':'status_code','access_token':at},timeout=30).json()
            sc=sr.get('status_code','UNKNOWN')
            print(f"[ig] Status: {sc} ({waited}s)")
            if sc=='FINISHED': break
            elif sc=='ERROR': raise Exception(sr.get('error_message','?'))
            time.sleep(30); waited+=30
        if waited>=180: raise Exception("Timed out")
        pp=requests.post(f"https://graph.facebook.com/v21.0/{uid}/media_publish",params={'creation_id':cid,'access_token':at},timeout=60)
        if pp.status_code!=200: raise Exception(f"Publish failed")
        mid=pp.json().get('id')
        print(f"[ig] SUCCESS! Media ID: {mid}")
        # Cleanup
        requests.delete(f'https://api.github.com/repos/{repo}/contents/{rp}',headers=h,json={'message':'cleanup','sha':sha,'branch':branch})
        return {'id':mid,'platform':'instagram','status':'success'}
    except Exception as e:
        print(f"[ig] GitHub URL method failed: {str(e)[:100]}")
        raise

if __name__=='__main__':
    f=Path('final_video.mp4')
    if f.exists():
        try: print(upload_to_instagram(str(f),"Test"))
        except Exception as e: print(f"Failed: {e}")