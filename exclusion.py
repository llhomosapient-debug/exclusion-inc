#!/usr/bin/env python3
"""Exclusion Inc: local AI terminal dashboard + llama.cpp client."""
from __future__ import annotations
import curses, hashlib, json, platform, re, shutil, subprocess, time, urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parent
CFG=json.loads((ROOT/'config/exclusion.json').read_text())
MODEL_DIR=ROOT/'models'; AUDIT=ROOT/'logs/security.audit'
LLAMA=Path.home()/'llama.cpp/build/bin/llama-server'
HOST=CFG.get('host','127.0.0.1'); PORT=int(CFG.get('port',8080)); CONTEXT=int(CFG.get('context',4096)); TEMP=float(CFG.get('temperature',0.7)); SYMBOL=CFG.get('symbol','◈')
MODEL=CFG.get('default_model','qwen2.5-3b-instruct-q4_k_m.gguf')
server=None; messages=[]; chat_lines=[]
PATTERNS=[r'(?:show|give|print|reveal|dump|tell)\b.{0,100}(?:system prompt|system message|hidden prompt)',r'(?:show|give|read|print|dump)\b.{0,100}(?:protected\.json|secret|credential|private key)',r'(?:ignore|bypass|disable)\b.{0,100}(?:security|audit|protection)']

def sha(s): return hashlib.sha256(s.encode()).hexdigest()
def audit(kind,text):
    AUDIT.parent.mkdir(parents=True,exist_ok=True); prev='0'*64
    if AUDIT.exists():
        try: prev=json.loads(AUDIT.read_text().splitlines()[-1])['event_hash']
        except Exception: pass
    e={'timestamp':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'event_type':kind,'evidence_sha256':sha(text),'previous_event_hash':prev}; e['event_hash']=sha(json.dumps(e,sort_keys=True,separators=(',',':')))
    with AUDIT.open('a') as f: f.write(json.dumps(e,separators=(',',':'))+'\n')
def security_check(text):
    for p in PATTERNS:
        if re.search(p,text,re.I|re.S): audit('protected-resource-attempt',text); return True
    return False
def models(): MODEL_DIR.mkdir(exist_ok=True); return sorted(MODEL_DIR.glob('*.gguf'))
def selected():
    p=MODEL_DIR/MODEL
    return p if p.exists() else (models()[0] if models() else None)
def stop_server():
    global server
    if server and server.poll() is None:
        server.terminate()
        try: server.wait(2)
        except subprocess.TimeoutExpired: server.kill()
    server=None
def start_server():
    global server
    m=selected()
    if not LLAMA.exists(): return False,f'Install llama.cpp first: {LLAMA}'
    if not m: return False,'No .gguf model in models/'
    stop_server(); cmd=[str(LLAMA),'-m',str(m),'--host',HOST,'--port',str(PORT),'-c',str(CONTEXT),'--temp',str(TEMP),'--no-webui']
    try: server=subprocess.Popen(cmd,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    except OSError as e: return False,str(e)
    for _ in range(80):
        if server.poll() is not None: return False,'llama-server exited during startup'
        try:
            with urllib.request.urlopen(f'http://{HOST}:{PORT}/health',timeout=.4) as r:
                if r.status==200: return True,f'Loaded {m.name}'
        except Exception: time.sleep(.15)
    return False,'Model server timeout'
def chat(prompt):
    if security_check(prompt): return 'Protected Exclusion Inc resources are not available.'
    body={'model':MODEL,'messages':[{'role':'system','content':CFG['system_prompt']},*messages,{'role':'user','content':prompt}],'temperature':TEMP,'max_tokens':512,'stream':False}
    req=urllib.request.Request(f'http://{HOST}:{PORT}/v1/chat/completions',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=180) as r: ans=json.loads(r.read())['choices'][0]['message']['content'].strip()
        messages.extend([{'role':'user','content':prompt},{'role':'assistant','content':ans}]); return ans
    except Exception as e: return f'Local model error: {e}'
def cpu():
    try:
        def r():
            v=[int(x) for x in Path('/proc/stat').read_text().splitlines()[0].split()[1:]]; return sum(v),v[3]+v[4]
        a=r(); time.sleep(.04); b=r(); total=b[0]-a[0]; idle=b[1]-a[1]; return f'{100*(1-idle/max(total,1)):4.1f}%'
    except Exception:return 'N/A'
def ram():
    try:
        d={x.split(':')[0]:int(x.split(':')[1].split()[0]) for x in Path('/proc/meminfo').read_text().splitlines()}; return f"{(d['MemTotal']-d.get('MemAvailable',d['MemFree']))/1024:.0f}/{d['MemTotal']/1024:.0f} MB"
    except Exception:return 'N/A'
def disk():
    try:
        d=shutil.disk_usage(Path.home()); return f'{d.used/2**30:.1f}/{d.total/2**30:.1f} GB'
    except Exception:return 'N/A'
def redraw(s,status,text):
    s.erase(); h,w=s.getmaxyx(); m=selected(); mn=m.name if m else 'NO MODEL'
    rows=[f'{SYMBOL}  EXCLUSION INC  //  LOCAL AI',f'TIME {time.strftime("%H:%M:%S")}   CPU {cpu()}   RAM {ram()}   SSD {disk()}',f'OS {platform.system()} {platform.release()}   KERNEL {platform.release()}',f'ENGINE llama.cpp   MODEL {mn}',f'CTX {CONTEXT}   TEMP {TEMP}   SERVER {HOST}:{PORT}',f'STATUS {status}','─'*max(1,min(w-1,100))]
    for y,row in enumerate(rows): s.addstr(y,0,row[:w-1],curses.A_BOLD if y==0 else 0)
    usable=max(1,h-9)
    for i,line in enumerate(chat_lines[-usable:]): s.addstr(7+i,0,line[:w-1])
    s.addstr(h-2,0,'─'*max(1,min(w-1,100))); s.addstr(h-1,0,f'You › {text}'[:w-1]); s.refresh()
def wrap(prefix,text,w):
    import textwrap; out=textwrap.wrap(text,max(10,w-len(prefix)-2)) or ['']; return [prefix+out[0]]+['   '+x for x in out[1:]]
def ui(s):
    curses.curs_set(1); s.timeout(200); text=''; status='STARTING'; ok,msg=start_server(); status=msg
    global MODEL
    while True:
        redraw(s,status,text); ch=s.get_wch()
        if ch==-1: continue
        if isinstance(ch,str) and ch in ('\n','\r'):
            q=text.strip(); text=''
            if not q: continue
            if q.lower() in ('#endconvo','!exit','/exit'): return
            if q in ('!help','/help'): chat_lines.extend(['SYSTEM › !help !status !models !model <file> !clear !reload #endconvo','SYSTEM › Inference is local-only via 127.0.0.1']); continue
            if q in ('!status','/status'): chat_lines.append(f'SYSTEM › CPU {cpu()} | RAM {ram()} | SSD {disk()} | {platform.system()} {platform.release()}'); continue
            if q in ('!models','/models'): chat_lines.append('SYSTEM › Models: '+(', '.join(x.name for x in models()) or 'none')); continue
            if q in ('!clear','/clear'): chat_lines.clear(); messages.clear(); continue
            if q in ('!reload','/reload'): ok,msg=start_server(); status=msg; continue
            if q.startswith('!model ') or q.startswith('/model '):
                name=q.split(None,1)[1].strip()
                if (MODEL_DIR/name).exists(): MODEL=name; ok,msg=start_server(); status='MODEL CHANGED: '+msg
                else: status='Model not found: '+name
                continue
            if not server or server.poll() is not None: ok,msg=start_server(); status=msg; 
            if not server or server.poll() is not None: chat_lines.append('SYSTEM › '+status); continue
            chat_lines.extend(wrap('YOU  › ',q,s.getmaxyx()[1])); status='GENERATING'; redraw(s,status,text); ans=chat(q); chat_lines.extend(wrap('AI   › ',ans,s.getmaxyx()[1])); status='READY'
        elif ch in (curses.KEY_BACKSPACE,'\b','\x7f'): text=text[:-1]
        elif isinstance(ch,str) and ch.isprintable(): text+=ch
def main():
    try: curses.wrapper(ui)
    finally: stop_server(); print('\nExclusion Inc stopped.')
if __name__=='__main__': main()
