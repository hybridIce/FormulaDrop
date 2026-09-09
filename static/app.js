'use strict';
const $ = id => document.getElementById(id);
const isWindowsDesktop = !!window.chrome?.webview;
const isDesktop = isWindowsDesktop || !!window.webkit?.messageHandlers?.formulaNative;
const nativeRequests = new Map();
window.formulaNativeReply = ({id,error,data}) => {const pending=nativeRequests.get(id);if(!pending)return;nativeRequests.delete(id);error?pending.reject(Error(error)):pending.resolve(data);};
function nativeCall(action,payload={}){return new Promise((resolve,reject)=>{const id=crypto.randomUUID();nativeRequests.set(id,{resolve,reject});const bridge=isWindowsDesktop?window.chrome.webview:window.webkit.messageHandlers.formulaNative;bridge.postMessage({id,action,...payload});});}

const examples = [String.raw`x = \frac{-b \pm \sqrt{b^2-4ac}}{2a}`, String.raw`\int_0^\infty e^{-x}\,dx=1`, String.raw`e^{i\pi}+1=0`];
let currentBlob=null, originalBlob=null, picture=null, selection=null, startPoint=null, busy=false, capturing=false, ready=false, format='latex', toastTimer, editTimer, version=0;
let history=[];
try { const saved=JSON.parse(localStorage.getItem('formuladrop.history') || '[]'); history=Array.isArray(saved)?saved.filter(v=>typeof v==='string'&&v.length<=12000).slice(0,20):[]; } catch {}
function status(text='', error=false){ $('status').textContent=text; $('status').classList.toggle('error',error); }
function toast(text){$('toast').textContent=text;$('toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('toast').hidden=true,3500);}
function updateButtons(){ const locked=busy||capturing; $('capture').disabled=locked; $('capture').firstElementChild.textContent=capturing?'正在框选…':'截图'; $('recognize').disabled=!currentBlob||!ready||locked; $('recognize').classList.toggle('busy',busy); $('recognize').firstElementChild.textContent=busy?'正在识别…':'识别公式'; for(const id of ['copy','word','word-copy']) $(id).disabled=!$('latex').value.trim()||locked; $('replace').disabled=locked; $('upload').disabled=locked; $('crop').disabled=locked||!selection; $('reset-image').disabled=locked; $('latex').readOnly=locked; for(const button of document.querySelectorAll('.example')) button.disabled=locked; }
async function api(url, body){const r=await fetch(url,{method:'POST',headers:body instanceof FormData?{}:{'Content-Type':'application/json'},body:body instanceof FormData?body:JSON.stringify(body)});if(!r.ok){let message='操作失败，请稍后再试。';const raw=await r.text();try{const detail=JSON.parse(raw).detail;message=typeof detail==='string'?detail:'公式过长或输入格式不正确。';}catch{if(raw.length<200)message=raw;}throw Error(message);}return r;}
function render(){ const text=$('latex').value.trim();$('parse-error').hidden=true; if(!text){$('preview').innerHTML='<div class="empty-preview"><span>ƒ(x)</span><p>识别结果</p></div>';}else{try{katex.render(text,$('preview'),{displayMode:true,throwOnError:true,trust:false,maxExpand:1000});}catch(e){$('preview').textContent='暂时无法预览';$('parse-error').textContent='请检查公式语法：'+e.message.replace(/^KaTeX parse error: /,'');$('parse-error').hidden=false;}} updateButtons(); }
function setLatex(text){$('latex').value=text;version++;$('edited').textContent='';render();}
$('latex').addEventListener('input',()=>{version++;$('edited').textContent='已编辑';clearTimeout(editTimer);updateButtons();editTimer=setTimeout(render,120);});
function draw(){if(!picture)return;const c=$('canvas'),ctx=c.getContext('2d');ctx.clearRect(0,0,c.width,c.height);ctx.drawImage(picture,0,0);if(selection){const {x,y,w,h}=selection;ctx.fillStyle='rgba(35,79,53,.16)';ctx.fillRect(0,0,c.width,c.height);ctx.clearRect(x,y,w,h);ctx.drawImage(picture,x,y,w,h,x,y,w,h);ctx.strokeStyle='#397b51';ctx.lineWidth=Math.max(2,c.width/300);ctx.strokeRect(x,y,w,h);}}
async function loadImage(blob, original=true){if(busy||capturing)return;if(blob.size>12*1024*1024){status('图片不能超过 12 MB。',true);return;}const url=URL.createObjectURL(blob);const img=new Image();try{await new Promise((resolve,reject)=>{img.onload=resolve;img.onerror=()=>reject(Error('无法读取图片，请使用 PNG、JPG、WebP 或 BMP。'));img.src=url;});if(img.width*img.height>16000000)throw Error('图片过大，请先截取公式区域。');currentBlob=blob;setLatex('');$('timing').textContent='可编辑结果';if(original)originalBlob=blob;picture=img;selection=null;const c=$('canvas');c.width=img.width;c.height=img.height;$('drop').hidden=true;$('image-area').hidden=false;$('image-info').textContent=`${img.width} × ${img.height}`;draw();status('图片已载入');updateButtons();}catch(e){status(e.message,true);}finally{URL.revokeObjectURL(url);}}
$('drop').onclick=()=>$('file').click();$('drop').onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();$('file').click();}};$('replace').onclick=$('upload').onclick=()=>$('file').click();$('file').onchange=e=>{const file=e.target.files[0];if(file)loadImage(file);e.target.value='';};
document.addEventListener('paste',e=>{const item=Array.from(e.clipboardData?.items||[]).find(x=>x.type.startsWith('image/'));if(item){e.preventDefault();if(busy){toast('请等当前识别完成后再粘贴。');return;}loadImage(item.getAsFile());}});
for(const name of ['dragenter','dragover'])document.addEventListener(name,e=>{e.preventDefault();$('drop').classList.add('dragging');});document.addEventListener('dragleave',()=>$('drop').classList.remove('dragging'));document.addEventListener('drop',e=>{e.preventDefault();$('drop').classList.remove('dragging');if(busy)return;const f=e.dataTransfer.files[0];if(f)loadImage(f);});
function point(e){const r=$('canvas').getBoundingClientRect();return {x:Math.max(0,Math.min(picture.width,(e.clientX-r.left)*picture.width/r.width)),y:Math.max(0,Math.min(picture.height,(e.clientY-r.top)*picture.height/r.height))};}
$('canvas').onpointerdown=e=>{if(busy||!picture)return;startPoint=point(e);selection=null;$('canvas').setPointerCapture(e.pointerId);};$('canvas').onpointermove=e=>{if(!startPoint)return;const p=point(e);selection={x:Math.round(Math.min(p.x,startPoint.x)),y:Math.round(Math.min(p.y,startPoint.y)),w:Math.round(Math.abs(p.x-startPoint.x)),h:Math.round(Math.abs(p.y-startPoint.y))};draw();};$('canvas').onpointerup=()=>{startPoint=null;if(selection&&(selection.w<8||selection.h<8))selection=null;draw();updateButtons();};$('canvas').onpointercancel=()=>{startPoint=null;selection=null;draw();updateButtons();};
$('crop').onclick=()=>{if(!selection||busy)return;const c=document.createElement('canvas');c.width=selection.w;c.height=selection.h;c.getContext('2d').drawImage(picture,selection.x,selection.y,selection.w,selection.h,0,0,selection.w,selection.h);c.toBlob(blob=>loadImage(blob,false),'image/png');};$('reset-image').onclick=()=>originalBlob&&loadImage(originalBlob,false);
$('recognize').onclick=async()=>{if(busy||!currentBlob)return;busy=true;setLatex('');$('timing').textContent='识别中';updateButtons();status('正在本机识别，复杂公式可能需要稍等片刻…');const data=new FormData();data.append('file',currentBlob,'formula.png');try{const r=await (await api('/api/recognize',data)).json();setLatex(r.latex);$('timing').textContent=r.cached?'已复用上次结果':`识别用时 ${r.seconds} 秒`;saveHistory(r.latex);status('识别完成');}catch(e){$('timing').textContent='识别未完成';status(e.message,true);}finally{busy=false;updateButtons();}};
function saveHistory(text){history=[text,...history.filter(x=>x!==text)].slice(0,20);try{localStorage.setItem('formuladrop.history',JSON.stringify(history));}catch{toast('浏览器未允许保存历史记录。');}renderHistory();}
function renderHistory(){const list=$('history-list');list.replaceChildren();if(!history.length){const p=document.createElement('p');p.className='muted';p.textContent='识别完成后，公式会保存在这里。';list.append(p);return;}history.forEach(text=>{const b=document.createElement('button');b.className='history-item';b.title='载入：'+text.slice(0,120);b.setAttribute('aria-label','载入历史公式 '+text.slice(0,80));try{if(text.length>600)throw Error('long history');katex.render(text,b,{throwOnError:true,trust:false,maxExpand:1000});}catch{b.textContent=text.slice(0,80)+(text.length>80?'…':'');}b.onclick=()=>{if(busy)return;setLatex(text);$('timing').textContent='来自历史记录';status('已载入历史公式，可直接复制或修改。');};list.append(b);});}
$('clear-history').onclick=()=>{history=[];try{localStorage.removeItem('formuladrop.history');}catch{}renderHistory();toast('历史记录已清除');};$('clear').onclick=()=>{if(!busy){setLatex('');$('timing').textContent='可编辑结果';status();}};
const labels={latex:'LaTeX',inline:'行内公式',block:'块级公式',mathml:'MathML'};
$('copy-format').onchange=()=>{format=$('copy-format').value;$('copy').innerHTML=`复制 ${labels[format]} <span>⧉</span>`;};
async function mathml(text){return (await (await api('/api/mathml',{latex:text})).json()).mathml;}
async function copyText(text){if(isDesktop){await nativeCall('copy',{text});return;}if(navigator.clipboard?.writeText){await navigator.clipboard.writeText(text);return;}const t=document.createElement('textarea');t.value=text;t.style.position='fixed';t.style.opacity='0';document.body.append(t);t.select();const ok=document.execCommand('copy');t.remove();if(!ok)throw Error('浏览器未允许复制，请手动选择源码复制。');}
$('copy').onclick=async()=>{const text=$('latex').value.trim(), chosen=format;if(!text)return;try{if(chosen==='mathml'&&!isDesktop&&navigator.clipboard?.write&&window.ClipboardItem){await navigator.clipboard.write([new ClipboardItem({'text/plain':mathml(text).then(v=>new Blob([v],{type:'text/plain'}))})]);}else{await copyText(chosen==='inline'?`$${text}$`:chosen==='block'?`$$\n${text}\n$$`:chosen==='mathml'?await mathml(text):text);}toast(`已复制 ${labels[chosen]}`);}catch(e){status(e.message||'复制失败，请允许剪贴板访问。',true);}};
$('word-copy').onclick=async()=>{const text=$('latex').value.trim();if(!text)return;try{if(isDesktop){const m=await mathml(text);await nativeCall('copy',{text,html:`<html><body>${m}</body></html>`});toast('已复制到剪贴板，可粘贴到 Word');return;}if(!navigator.clipboard?.write||!window.ClipboardItem)throw Error('此浏览器不支持富文本复制，请下载 .docx。');const html=mathml(text).then(m=>new Blob([`<html><body><!--StartFragment-->${m}<!--EndFragment--></body></html>`],{type:'text/html'}));await navigator.clipboard.write([new ClipboardItem({'text/html':html,'text/plain':new Blob([text],{type:'text/plain'})})]);toast('已复制。若 Word 未显示公式，请下载 .docx。');}catch(e){status('富文本复制未完成，请使用右侧 ↓ .docx 下载可编辑公式。',true);}};
$('word').onclick=async()=>{const text=$('latex').value.trim();if(!text)return;try{const blob=await (await api('/api/word',{latex:text})).blob();if(isDesktop){const base64=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=reject;reader.readAsDataURL(blob);});await nativeCall('save',{base64});toast('Word 文档已保存');return;}const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='formula.docx';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);toast('Word 文档已生成，请查看浏览器下载。');}catch(e){status(e.message,true);}};
document.querySelectorAll('.example').forEach(button=>button.onclick=async()=>{try{const r=await fetch(`/static/examples/${button.dataset.example}.png`);if(!r.ok)throw Error('示例图片加载失败');await loadImage(await r.blob());}catch(e){status(e.message,true);}});
$('help').onclick=()=>$('help-dialog').showModal();$('close-help').onclick=$('help-ok').onclick=()=>$('help-dialog').close();
async function health(){try{const r=await fetch('/api/health');if(!r.ok)throw Error();const s=await r.json();ready=s.status==='ready';$('health').className='health '+s.status;$('health').lastElementChild.textContent=s.message;if(s.status==='error')status(s.message,true);}catch{ready=false;$('health').className='health error';$('health').lastElementChild.textContent='服务未连接，请双击启动.command';}updateButtons();setTimeout(health,ready?15000:2500);}
examples.forEach((tex,i)=>katex.render(tex,$('ex'+i),{throwOnError:false}));renderHistory();render();health();

$('capture').onclick=async()=>{
    if(busy||capturing)return;
    capturing=true;updateButtons();
    try{
        status('请拖动框选公式，松开鼠标完成；按 Esc 取消。');
        if(isWindowsDesktop){
            const encoded=await nativeCall('capture');
            if(!encoded){status('已取消截图');return;}
            const bytes=Uint8Array.from(atob(encoded),c=>c.charCodeAt(0));
            const blob=new Blob([bytes],{type:'image/png'});capturing=false;
            await loadImage(blob);
            if(currentBlob===blob&&ready)await $('recognize').onclick();
            return;
        }
        if(isDesktop)await nativeCall('hide');
        const response=await fetch('/api/capture',{method:'POST',headers:{'X-FormulaDrop-Capture':'1'}});
        if(isDesktop)await nativeCall('show');
        if(response.status===204){status('已取消截图。');return;}
        if(!response.ok){let message='截图失败，请重试。';try{message=(await response.json()).detail||message;}catch{}throw Error(message);}
        const blob=await response.blob();capturing=false;
        await loadImage(blob);
        if(currentBlob===blob&&ready)await $('recognize').onclick();
    }catch(e){status(e.message||'截图服务未连接，请重新启动工具。',true);}
    finally{if(isDesktop&&!isWindowsDesktop)nativeCall('show').catch(()=>{});capturing=false;updateButtons();}
};
