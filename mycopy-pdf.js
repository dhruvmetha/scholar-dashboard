/* Scout's PDF worker. Source pages stay vector/text; derived bytes never persist here. */
'use strict';
const COPY_PINS=Object.freeze({
 writer:{url:'https://cdn.jsdelivr.net/npm/pdf-lib@1.17.1/dist/pdf-lib.min.js',integrity:'sha384-weMABwrltA6jWR8DDe9Jp5blk+tZQh7ugpCsF3JwSA53WZM9/14PjS5LAJNHNjAI'},
 fontkit:{url:'https://cdn.jsdelivr.net/npm/@pdf-lib/fontkit@1.1.1/dist/fontkit.umd.min.js',integrity:'sha384-2p6U+1mmqF10USehFeRiyG2ESG9FwIqN+jxULn5w9jjQIihSn9Pt13dVCn/Hawjn'},
 noto:{url:'https://cdn.jsdelivr.net/gh/notofonts/noto-fonts@v20201206-phase3/hinted/ttf/NotoSans/NotoSans-Regular.ttf',integrity:'sha384-AzUdvGOf+GKplEVcLgFtLqtxH0t4ZKdXbGsyiBW2OB77f43z1uUcHkFbLfmMVLdj'}
});
const FORMAT=1,STRIP=180,GUTTER=18,FONT_SIZE=10,LINE=13;
function fail(code,message){const e=Error(message);e.code=code;throw e;}
function base64(a){let s='';for(const b of a)s+=String.fromCharCode(b);return btoa(s);}
async function hash(a){return [...new Uint8Array(await crypto.subtle.digest('SHA-256',a))].map(b=>b.toString(16).padStart(2,'0')).join('');}
async function verifyPinned(entries){for(const e of Object.values(entries)){if(!e.pin||'sha384-'+base64(new Uint8Array(await crypto.subtle.digest('SHA-384',e.bytes)))!==e.pin.integrity)fail('integrity','Pinned dependency integrity mismatch');}return true;}
async function fetchPin(pin){const r=await fetch(pin.url,{integrity: pin.integrity, credentials: 'omit',redirect:'error'});if(!r.ok)fail('dependency','Pinned dependency unavailable');const bytes=new Uint8Array(await r.arrayBuffer());await verifyPinned({entry:{bytes,pin}});return bytes;}
let dependenciesPromise;
function dependencies(){return dependenciesPromise||(dependenciesPromise=(async()=>{
 const [writer,fontkit,noto]=await Promise.all([fetchPin(COPY_PINS.writer),fetchPin(COPY_PINS.fontkit),fetchPin(COPY_PINS.noto)]);
 const urls=[URL.createObjectURL(new Blob([writer],{type:'text/javascript'})),URL.createObjectURL(new Blob([fontkit],{type:'text/javascript'}))];
 try{importScripts(urls[0]);importScripts(urls[1]);}finally{urls.forEach(u=>URL.revokeObjectURL(u));}
 if(!self.PDFLib||!self.fontkit)fail('dependency','Pinned writer did not initialize');return {L:self.PDFLib,noto,glyphs:self.fontkit.create(noto)};
})());}
function pageViewport(p){
 const t=p?.transform,w=p?.width,h=p?.height;if(!Array.isArray(t)||t.length!==6||!t.every(Number.isFinite)||!Number.isFinite(w)||!Number.isFinite(h)||w<=0||h<=0)fail('binding','Missing PDF viewport');
 const det=t[0]*t[3]-t[1]*t[2];if(!det)fail('binding','Invalid PDF viewport');
 return {width:w,height:h,convertToPdfPoint(x,y){const dx=x-t[4],dy=y-t[5];return [(t[3]*dx-t[2]*dy)/det,(-t[1]*dx+t[0]*dy)/det];}};
}
function toPdfPoint(p,v){return v.convertToPdfPoint(p[0]*v.width,p[1]*v.height);}
function toPdfRect(r,v){const a=[[r[0],r[1]],[r[0]+r[2],r[1]],[r[0],r[1]+r[3]],[r[0]+r[2],r[1]+r[3]]].map(p=>toPdfPoint(p,v));return [Math.min(...a.map(p=>p[0])),Math.min(...a.map(p=>p[1])),Math.max(...a.map(p=>p[0])),Math.max(...a.map(p=>p[1]))];}
function pdfWidth(w,v){const a=v.convertToPdfPoint(0,0),b=v.convertToPdfPoint(w*v.width,0);return Math.hypot(b[0]-a[0],b[1]-a[1]);}
function inkCubics(points){return points.slice(0,-1).map((a,i)=>{const p=points[i-1]||a,b=points[i+1],n=points[i+2]||b;return {from:a,c1:[a[0]+(b[0]-p[0])/6,a[1]+(b[1]-p[1])/6],c2:[b[0]-(n[0]-a[0])/6,b[1]-(n[1]-a[1])/6],to:b};});}
const COLORS={orange:'#ff7a1f',yellow:'#ff7a1f',green:'#34c26b',blue:'#4b8ef7',red:'#e03a40',pink:'#f5a0d5',purple:'#a66ff2'};
function color(value,L){const h=COLORS[value]||value||'#000000';if(!/^#[a-f0-9]{6}$/i.test(h))fail('marks','Invalid saved color');return L.rgb(parseInt(h.slice(1,3),16)/255,parseInt(h.slice(3,5),16)/255,parseInt(h.slice(5,7),16)/255);}
function clipOperators(c,L){return [L.pushGraphicsState(),L.rectangle(c.x,c.y,c.width,c.height),L.clip(),L.endPath()];}
function clipOriginal(page,doc,c,L){
 page.node.normalize();const pre=doc.context.register(doc.context.flateStream(`q\n${c.x} ${c.y} ${c.width} ${c.height} re\nW\nn\n`)),post=doc.context.register(doc.context.flateStream('Q\n'));
 if(!page.node.wrapContentStreams(pre,post))fail('source','Unable to clip source content');
}
function strokePath(page,s,map,width,L){
 const pts=s.pts;if(!Array.isArray(pts)||!pts.length||pts.some(p=>!Array.isArray(p)||p.length<2||!p.slice(0,2).every(Number.isFinite)))fail('marks','Invalid saved stroke');
 const c=color(s.color,L),w=Math.max(.1,width),xy=pts.map(map);
 if(xy.length===1){page.drawCircle({x:xy[0][0],y:xy[0][1],size:w/2,color:c});return;}
 const curves=inkCubics(xy);page.pushOperators(L.pushGraphicsState(),L.setLineCap(L.LineCapStyle.Round),L.setLineJoin(L.LineJoinStyle.Round),L.setLineWidth(w),L.setStrokingColor(c),L.moveTo(...xy[0]),...curves.map(x=>L.appendBezierCurve(...x.c1,...x.c2,...x.to)),L.stroke(),L.popGraphicsState());
}
function mergeRects(rects){
 const good=rects.filter(r=>Array.isArray(r)&&r.length===4&&r.every(Number.isFinite)&&r[2]>0&&r[3]>0),ys=[...new Set(good.flatMap(r=>[r[1],r[1]+r[3]]))].sort((a,b)=>a-b),out=[];
 for(let i=0;i<ys.length-1;i++){const y=ys[i],end=ys[i+1],xs=good.filter(r=>r[1]<=y&&r[1]+r[3]>=end).map(r=>[r[0],r[0]+r[2]]).sort((a,b)=>a[0]-b[0]),spans=[];
  for(const x of xs){const last=spans.at(-1);if(last&&x[0]<=last[1])last[1]=Math.max(last[1],x[1]);else spans.push(x.slice());}
  for(const x of spans){const prev=out.find(r=>r[0]===x[0]&&r[2]===x[1]-x[0]&&Math.abs(r[1]+r[3]-y)<1e-9);if(prev)prev[3]+=end-y;else out.push([x[0],y,x[1]-x[0],end-y]);}
 }return out;
}
function textOf(text,notes){return String(text||'').replace(/\[\[cite:([\w-]+)[^\]]*\]\]/g,(_,id)=>{const a=(notes.annos||[]).find(a=>a.id===id);return a?`p. ${a.page}${a.quote?' "'+a.quote+'"':''}`:'Citation';}).replace(/\[\[p\.(\d+)\s+"([^"]*)"\]\]/g,'p. $1 "$2"').replace(/!?\[([^\]]*)\]\([^)]*\)/g,'$1').replace(/[*_`>#]/g,'').replace(/\r/g,'');}
function markdownText(t){return textOf(t,{annos:[]});}
function commentParts(x){return {typed:String(x.note||x.text||''),hand:(x.hand?.strokes||[]).filter(s=>Array.isArray(s.pts))};}
function checkGlyphs(text,glyphs){for(const c of text){const n=c.codePointAt(0);if(n>32&&!glyphs.hasGlyphForCodePoint(n))fail('glyph','A character is unavailable in the saved font');}}
function wrap(text,width,font){
 const result=[];for(const paragraph of text.split('\n')){let line='';for(const word of paragraph.split(/\s+/)){if(!word)continue;
  if(line&&font.widthOfTextAtSize(line+' '+word,FONT_SIZE)>width){result.push(line);line='';}
  if(font.widthOfTextAtSize(word,FONT_SIZE)<=width){line+=(line?' ':'')+word;continue;}
  for(const ch of word){if(line&&font.widthOfTextAtSize(line+ch,FONT_SIZE)>width){result.push(line);line='';}line+=ch;}
 }result.push(line);}return result;
}
function upright(page,text,x,y,frame,font,L,size=FONT_SIZE){
 const p=frame.convertToPdfPoint(x,y),a=frame.convertToPdfPoint(x+1,y),b=frame.convertToPdfPoint(x,y-1);
 page.pushOperators(L.pushGraphicsState(),L.concatTransformationMatrix(a[0]-p[0],a[1]-p[1],b[0]-p[0],b[1]-p[1],p[0],p[1]));
 page.drawText(text,{x:0,y:0,size,font,color:L.rgb(0,0,0)});page.pushOperators(L.popGraphicsState());
}
function expandRight(page,v,L){
 const p=[[0,0],[v.width+STRIP,0],[0,v.height],[v.width+STRIP,v.height]].map(x=>v.convertToPdfPoint(...x)),x=Math.min(...p.map(p=>p[0])),y=Math.min(...p.map(p=>p[1])),right=Math.max(...p.map(p=>p[0])),top=Math.max(...p.map(p=>p[1])),m=page.getMediaBox();
 page.setCropBox(x,y,right-x,top-y);const mx=Math.min(m.x,x),my=Math.min(m.y,y);page.setMediaBox(mx,my,Math.max(m.x+m.width,right)-mx,Math.max(m.y+m.height,top)-my);
}
function handPieces(hand,width,maxHeight){
 if(!hand?.strokes?.length)return [];const wanted=Math.min(width,Number.isFinite(hand.px)&&hand.px>0?hand.px*.75:width),strokes=hand.strokes.map(s=>{if(!s.pts?.length)fail('marks','Empty saved handwriting');const ys=s.pts.map(p=>p[1]);return {s,top:Math.min(...ys),bottom:Math.max(...ys)};}).sort((a,b)=>a.top-b.top),groups=[];
 for(const a of strokes){const last=groups.at(-1);if(last&&a.top<=last.bottom+.002){last.strokes.push(a.s);last.bottom=Math.max(last.bottom,a.bottom);}else groups.push({strokes:[a.s],top:a.top,bottom:a.bottom});}
 return groups.map(g=>{const scale=Math.min(wanted,maxHeight/Math.max(g.bottom-g.top,.01));return {...g,scale,height:Math.max(4,(g.bottom-g.top)*scale+4)};});
}
function contentParts(item,label,width,font,notes,maxHeight){
 const text=(label?label+' ':'')+textOf(item.note||item.text||'',notes),date=String(item.created||item.date||'').slice(0,10),parts=[];
 if(date)parts.push({text:date,height:LINE});for(const line of wrap(text,width,font))parts.push({text:line,height:LINE});
 for(const piece of handPieces(item.hand,width,maxHeight-8))parts.push({hand:piece,height:piece.height});return parts;
}
function drawPart(page,part,x,y,v,font,L){
 if(part.text!==undefined){upright(page,part.text,x,y+FONT_SIZE,v,font,L);return;}
 const h=part.hand;for(const s of h.strokes)strokePath(page,s,p=>v.convertToPdfPoint(x+p[0]*h.scale,y+2+(p[1]-h.top)*h.scale),pdfWidth((s.w||.002)*h.scale/v.width,v),L);
}
function newCommentsPage(doc,heading,font,L){const page=doc.addPage([612,792]),v=pageViewport({width:612,height:792,transform:[1,0,0,-1,0,792]});upright(page,heading,36,32,v,font,L,14);return {page,v,y:60,x:36,width:540,bottom:756};}
function layoutComments(items,height,line){const placed=[],overflow=[];let y=0;for(const x of [...items].sort((a,b)=>(a.anchor||0)-(b.anchor||0))){y=Math.max(y,x.anchor||0);if(y+(x.height||line)>height)overflow.push(x);else{placed.push({...x,y});y+=x.height||line;}}return {placed,overflow};}
function hasSignature(doc,L){
 if(doc.catalog.has(L.PDFName.of('Perms')))return true;const af=doc.catalog.lookupMaybe(L.PDFName.of('AcroForm'),L.PDFDict);if(!af)return false;
 const seen=new Set();function signed(fields){if(!fields)return false;for(let i=0;i<fields.size();i++){const f=fields.lookupMaybe(i,L.PDFDict);if(!f||seen.has(f))continue;seen.add(f);if(String(f.get(L.PDFName.of('FT')))==='/Sig'&&f.has(L.PDFName.of('V')))return true;if(signed(f.lookupMaybe(L.PDFName.of('Kids'),L.PDFArray)))return true;}return false;}
 return signed(af.lookupMaybe(L.PDFName.of('Fields'),L.PDFArray));
}
async function buildCopy(s){
 const original=new Uint8Array(s.sourceBytes||[]);if(!original.length||new TextDecoder().decode(original.slice(0,5))!=='%PDF-')fail('source','Source is not a PDF');const sourceHash=await hash(original);if(s.sourceHash!==sourceHash)fail('binding','Source hash mismatch');
 const result=bytes=>({id:s.id,kind:s.kind,bytes,sourceHash,revision:s.revision,outputHash:bytes===original?sourceHash:null});
 if(s.kind==='plain')return result(original);if(s.kind!=='annotated'||!s.notes)fail('binding','Missing verified notes');
 const notes=s.notes,deleted=notes.deleted||{},live=k=>(notes[k]||[]).filter(x=>x&&!x.deleted&&!x.draft&&(!deleted[x.id]||deleted[x.id]<(x.updated||''))),annos=live('annos'),ink=live('ink'),entries=live('entries');
 if(!annos.length&&!ink.length&&!entries.length)return result(original);
 if((annos.length||ink.length)&&(!s.pdfFingerprint||notes.pdf?.fp!==s.pdfFingerprint))fail('binding','Notes belong to a different PDF');
 if(/\/ByteRange\s*\[/.test(new TextDecoder('latin1').decode(original)))fail('signed','Signed PDF is unchanged');
 const {L,noto,glyphs}=await dependencies();let doc;try{doc=await L.PDFDocument.load(original);}catch(e){fail('source','Malformed or encrypted PDF');}
 if(hasSignature(doc,L))fail('signed','Signed PDF is unchanged');const pages=doc.getPages();if(!Array.isArray(s.pages)||s.pages.length!==pages.length)fail('binding','Page binding mismatch');
 for(const a of [...annos,...ink])if(!Number.isInteger(a.page)||a.page<1||a.page>pages.length)fail('binding','Invalid note page');
 const texts=[...annos,...entries].map(x=>textOf(x.note||x.text||'',notes));for(const t of texts)checkGlyphs(t,glyphs);
 doc.registerFontkit(self.fontkit);const font=await doc.embedFont(noto,{subset:true});
 for(let i=0;i<pages.length;i++){
  const page=pages[i],v=pageViewport(s.pages[i]),crop=page.getCropBox(),a=annos.filter(a=>a.page===i+1),strokes=ink.filter(k=>k.page===i+1),comments=a.filter(x=>x.kind==='note'||String(x.note||'').trim()||x.hand?.strokes?.length).sort((a,b)=>(a.rects?.[0]?.[1]||0)-(b.rects?.[0]?.[1]||0));
  if(comments.length)clipOriginal(page,doc,crop,L);page.pushOperators(...clipOperators(crop,L));
  for(const h of a.filter(a=>a.kind==='hl'))for(const r of mergeRects(h.rects||[])){const q=toPdfRect(r,v);page.drawRectangle({x:q[0],y:q[1],width:q[2]-q[0],height:q[3]-q[1],color:color(h.color,L),opacity:.4,blendMode:L.BlendMode.Multiply});}
  for(const h of a.filter(a=>a.kind!=='hl'))for(const r of h.rects||[]){const start=toPdfPoint([r[0],r[1]+r[3]],v),end=toPdfPoint([r[0]+r[2],r[1]+r[3]],v);page.drawLine({start:{x:start[0],y:start[1]},end:{x:end[0],y:end[1]},thickness:pdfWidth(.0015,v),color:L.rgb(.25,.35,.65)});}
  for(const k of strokes)strokePath(page,k,p=>toPdfPoint(p,v),pdfWidth(k.w||.002,v),L);page.pushOperators(L.popGraphicsState());
  if(!comments.length)continue;expandRight(page,v,L);let y=18,overflow=null;
  for(let n=0;n<comments.length;n++){
   const c=comments[n],anchor=(c.rects?.[0]?.[1]||0)*v.height;y=Math.max(y,anchor);const parts=contentParts(c,String(n+1)+'.',STRIP-GUTTER-12,font,notes,Math.max(30,v.height-36));
   for(const part of parts){if(!overflow&&y+part.height>v.height-18)overflow=newCommentsPage(doc,'Comments · page '+(i+1),font,L);
    if(overflow){if(overflow.y+part.height>overflow.bottom)overflow=newCommentsPage(doc,'Comments · page '+(i+1),font,L);drawPart(overflow.page,part,overflow.x,overflow.y,overflow.v,font,L);overflow.y+=part.height;}
    else {drawPart(page,part,v.width+GUTTER,y,v,font,L);y+=part.height;}}
   y+=8;if(overflow)overflow.y+=8;
  }
 }
 let general=null;for(const e of entries){if(!general)general=newCommentsPage(doc,'Your notes',font,L);const parts=contentParts(e,'',general.width,font,notes,general.bottom-60);
  for(const part of parts){if(general.y+part.height>general.bottom)general=newCommentsPage(doc,'Your notes',font,L);drawPart(general.page,part,general.x,general.y,general.v,font,L);general.y+=part.height;}general.y+=12;
 }
 const bytes=new Uint8Array(await doc.save());return {...result(bytes),outputHash:await hash(bytes)};
}
self.ScoutMyCopyPDF={COPY_PINS,FORMAT,verifyPinned,fetchPin,pageViewport,toPdfPoint,toPdfRect,pdfWidth,inkCubics,commentParts,layoutComments,markdownText,buildCopy};
self.onmessage=async e=>{if(e.data?.type!=='buildCopy')return;try{const result=await buildCopy(e.data.snapshot);self.postMessage({type:'copyResult',result},[result.bytes.buffer]);}catch(x){self.postMessage({type:'copyError',error:{code:x.code||'copy',message:'Could not prepare this copy'}});}};
