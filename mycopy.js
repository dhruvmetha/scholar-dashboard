/* Scout paper delivery. Finished PDFs remain in memory until an explicit local delivery. */
(function(root){
'use strict';
const BASE='http://127.0.0.1:7823';
const kinds=['plain','annotated'];
const validID=id=>typeof id==='string'&&/^[A-Za-z0-9][A-Za-z0-9._-]{0,159}$/.test(id);
function safePrefs(value={}) {
 const out={plain:value.plain!==false,annotated:value.annotated!==false,notesDone:value.notesDone===true,folderDone:value.folderDone===true};
 const p=value.pending;
 if(p&&Array.isArray(p.ids)&&Array.isArray(p.kinds))out.pending={ids:p.ids.filter(validID).slice(0,10000),kinds:p.kinds.filter(k=>kinds.includes(k)),cursor:Math.max(0,Math.min(Number.isSafeInteger(p.cursor)?p.cursor:0,p.ids.length))};
 return out;
}
async function copiesFetch(path,options={},ctx={}) {
 if(!/^\/(?:copies\/(?:status|config|folder|session|prepare|upload\?ticket=[a-zA-Z0-9_-]+|commit|cancel|move\/resume)|health|pair)$/.test(path))throw Error('copy_route');
 if(!ctx.current||!ctx.current())throw Error('copy_expired');
 const response=await ctx.fetch(BASE+path,{...options,redirect:'error',credentials:'omit',cache:'no-store',headers:{...(typeof options.body==='string'?{'Content-Type':'application/json'}:{}),...options.headers,...(ctx.token?{Authorization:'Bearer '+ctx.token}:{})}});
 if(!ctx.current())throw Error('copy_expired');return response;
}
function createQueue(a) {
 let pending=new Map(),failed=new Map(),running=null,cancelled=0,retry=0,attempts=0;
 function retryLater(){if(retry||!failed.size)return;retry=setTimeout(()=>{retry=0;for(const [id,job] of failed)if(job.epoch===a.epoch()&&a.eligible(id)&&!pending.has(id))pending.set(id,job);failed.clear();drain();},Math.min((a.retryMs||5000)*2**Math.min(attempts++,3),30000));retry.unref?.();}
 async function pump(){const run=cancelled;
  while(pending.size&&run===cancelled){const [id,job]=pending.entries().next().value;pending.delete(id);
   if(job.epoch!==a.epoch()||!a.eligible(id))continue;
   for(const kind of a.enabled()) {if(run!==cancelled||job.epoch!==a.epoch()||!a.eligible(id)||!a.enabled().includes(kind))break;
    try {const s=await a.snapshot(id,kind);if(run!==cancelled||job.epoch!==a.epoch()||!a.current(s))continue;
     if(a.already&&await a.already(s))continue;
     const r=await a.build(s);if(run!==cancelled||!a.current(s)||!a.eligible(id)||!a.enabled().includes(kind))continue;
     await a.deliver(r,s);if(a.progress)a.progress(id,kind,r);
    }catch(e){if(e&&e.skip)continue;if(run===cancelled&&job.epoch===a.epoch())failed.set(id,job);if(a.error)a.error(e,id,kind);}
   }
  }
 }
 function drain(){if(!running)running=Promise.resolve().then(pump).finally(()=>{running=null;if(pending.size)drain();else retryLater();});return running;}
 return {queueCopy(id,reason){if(validID(id)){failed.delete(id);pending.set(id,{epoch:a.epoch(),reason});}return drain();},drain,cancel(){cancelled++;pending.clear();failed.clear();clearTimeout(retry);retry=0;},get size(){return pending.size+failed.size;}};
}
function createShare(a){
 let state={ids:[],kinds:[],cursor:0},ready=null,serial=0,busy=false;
 const persist=()=>a.persist&&a.persist(safePrefs({pending:state}).pending);
 async function prepare(){const serial0=serial;ready=null;
  while(state.cursor<state.ids.length){const id=state.ids[state.cursor],ks=state.kinds.filter(k=>a.enabled().includes(k));
   if(!ks.length)break;if(!a.eligible(id)){state.cursor++;continue;}
   let files;try{files=await a.prepare(id,ks);}catch(e){if(serial0!==serial)return;if(e&&e.skip){state.cursor++;continue;}if(a.error)a.error(e);break;}
   if(serial0!==serial)return;
   if(!a.current(files)||!a.eligible(id))continue;
   ready={id,files,kinds:ks};break;
  }
  persist();if(a.changed)a.changed();
 }
 return {async start(ids,saved){serial++;state=saved?{ids:saved.ids.slice(),kinds:saved.kinds.slice(),cursor:saved.cursor}:{ids:ids.slice(),kinds:a.enabled().slice(),cursor:0};await prepare();},
  async handoff(){if(!ready||busy)return;let item=ready;
   if(!a.eligible(item.id)||!a.current(item.files)||item.kinds.some(k=>!a.enabled().includes(k))){ready=null;await prepare();return;}
   busy=true;const serial0=serial;
   try {const handoff=a.share(item.files);await handoff;if(serial0!==serial)return;state.cursor++;ready=null;item=null;if(a.release)a.release();persist();await prepare();}
   catch(e){if(e.name==='AbortError'){serial++;ready=null;persist();}else if(a.error)a.error(e);}
   finally{busy=false;if(a.changed)a.changed();}
  },cancel(){serial++;ready=null;persist();if(a.changed)a.changed();},invalidate(){serial++;ready=null;},get ready(){return ready;},get state(){return state;},get busy(){return busy;}};
}
const API={BASE,safePrefs,copiesFetch,createQueue,createShare};
if(typeof module!=='undefined'&&module.exports)module.exports=API;else root.ScoutCopies=API;
})(typeof self!=='undefined'?self:globalThis);
