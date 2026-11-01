const $=s=>document.querySelector(s);
let data={applications:[],resumes:[],resume_files:[],stages:[],sources:[]},filter='all',printed=null;
const ACTIVE=['Applied','Screen','Interview','Offer'],CLOSED=['Rejected','Withdrawn'];
// "How long ago was it posted?" — matches what LinkedIn and Indeed show next to a posting.
const POSTED=[['<1h',.5],['1h',1],['2h',2],['3h',3],['6h',6],['12h',12],['1d',24],['2d',48],['3d',72],['1w+',168],['Not sure','']];

function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
async function post(path,d={}){const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});const j=await r.json();if(j.error)throw Error(j.error);return j;}
async function load(){data=await(await fetch('/api/state')).json();render();}
function note(msg){$('#notice').textContent=msg||'';}
function remember(k,v){try{if(v)localStorage.setItem('jt-'+k,v);}catch{}}
function recall(k){try{return localStorage.getItem('jt-'+k)||'';}catch{return '';}}

function hoursToApply(a){if(!a.posted_at||!a.applied_at)return null;return Math.max(0,(new Date(a.applied_at)-new Date(a.posted_at))/36e5);}
function span(h){if(h==null)return '—';if(h<1)return '<1h';if(h<24)return Math.round(h)+'h';if(h<24*14)return Math.round(h/24)+'d';return Math.round(h/168)+'w';}
function longSpan(h){if(h<1)return Math.max(1,Math.round(h*60))+'m';if(h<24){const m=Math.round(h*60);return Math.floor(m/60)+'h'+(m%60?' '+m%60+'m':'');}return span(h);}
function freshness(h){return h==null?'unknown':h<=24?'fresh':h<=72?'aging':'stale';}
function median(xs){const s=[...xs].sort((a,b)=>a-b),m=s.length>>1;return s.length%2?s[m]:(s[m-1]+s[m])/2;}
function day(a){const d=a.applied_at?new Date(a.applied_at):new Date(a.applied+'T12:00');return d.toLocaleDateString([],{month:'short',day:'numeric'});}
// Board from the link itself, or from the tracking tag company sites add (e.g. ?source=LinkedIn); '' when unsure.
function boardFor(url){try{const u=new URL(url),h=u.hostname,q=decodeURIComponent(u.search).toLowerCase();
 if(/linkedin\./.test(h)||/source=(linkedin|lili)\b/.test(q))return 'LinkedIn';if(/indeed\./.test(h)||/source=indeed\b/.test(q))return 'Indeed';if(/craigslist\./.test(h))return 'Craigslist';return '';}catch{return '';}}
// "Pavlo-Pyshnyy-Resume-Full-Stack.pdf" -> "Full Stack"; free-text names from older tickets pass through.
function resumeName(r){if(!r)return '';const stem=r.replace(/\.(pdf|docx?|pages)$/i,''),short=stem.replace(/^.*?resume[\s_-]*/i,'').replace(/[-_]+/g,' ').trim();return short||stem.replace(/[-_]+/g,' ');}
// Day-only posting dates count from local midnight.
function postedDate(v){const m=/^(\d{4})-(\d{2})-(\d{2})$/.exec(v||'');return m?new Date(+m[1],m[2]-1,+m[3]):new Date(v);}
const VIA={greenhouse:'from Greenhouse',ashby:'from Ashby',lever:'from Lever',workday:'from Workday',oracle:'from Oracle',indeed:'from Indeed',linkedin:'from LinkedIn',page:'from the page',structured:'from the posting data'};
function localInput(iso){if(!iso)return '';const d=new Date(iso);return new Date(d-d.getTimezoneOffset()*6e4).toISOString().slice(0,16);}
function fromLocalInput(v){return v?new Date(v).toISOString():'';}

function render(){hero();grades();filters();tickets();}

// Local calendar day an application was sent; older tickets only know the day.
function appliedDay(a){return a.applied_at?new Date(a.applied_at).toLocaleDateString('en-CA'):a.applied;}
function tally(){const today=new Date(),key=d=>d.toLocaleDateString('en-CA'),week=new Set([...Array(7)].map((_,i)=>key(new Date(today.getFullYear(),today.getMonth(),today.getDate()-i))));
 $('#todayCount').textContent=data.applications.filter(a=>appliedDay(a)===key(today)).length;
 $('#weekCount').textContent=data.applications.filter(a=>week.has(appliedDay(a))).length;}
function hero(){tally();const known=data.applications.map(hoursToApply).filter(h=>h!=null);
 if(!known.length){$('#median').textContent='—';$('#speedNote').innerHTML='Median time from posting to applying.<br>Log how long ago each job was posted and your speed shows up here.';return;}
 const fast=known.filter(h=>h<=24).length;
 $('#median').textContent=longSpan(median(known));
 $('#speedNote').innerHTML=`Median time from posting to applying.<br><b>${fast} of ${known.length}</b> sent within 24 hours of posting.`;}

// Report card: one red-pen grade per resume, on the Headless Headhunter's scale.
function grades(){const cards=data.resumes.filter(r=>r.resume),loose=data.resumes.find(r=>!r.resume);
 if(!cards.length&&!loose){$('#grades').innerHTML='';return;}
 const plural=(n,w)=>n+' '+w+(n===1?'':'s');
 $('#grades').innerHTML=`<p class="gradehead">Interviews per application, by resume</p><div class="cards">${cards.map(r=>{
  const ratio=r.interviews?`1 interview in ${Math.round(r.applications/r.interviews)}`:r.applications?'No interviews yet':'Not used yet';
  return `<div class="rc"><div><b>${esc(resumeName(r.resume))}</b><small>${plural(r.applications,'application')} · ${plural(r.interviews,'interview')}</small><small>${r.grade?ratio:ratio+'. Graded after 10 applications or 1 interview.'}</small></div><span class="pen" data-grade="${esc(r.grade)}" ${r.grade?'':'aria-label="Not graded yet"'}>${r.grade||'–'}</span></div>`;}).join('')}</div>
 <p class="scale">A+ is 1 interview in 10 or better · B 1 in 25 · C- 1 in 50 · D 1 in 75 · F beyond</p>${loose?`<p class="loose">${plural(loose.applications,'earlier application')} ${loose.applications===1?'has':'have'} no resume picked. Click a company name to choose one.</p>`:''}`;}

function inFilter(a){return filter==='all'||(filter==='active'?ACTIVE.includes(a.status):filter==='closed'?CLOSED.includes(a.status):a.status===filter);}
function filters(){const a=data.applications,count=f=>a.filter(x=>f==='all'||(f==='active'?ACTIVE.includes(x.status):f==='closed'?CLOSED.includes(x.status):x.status===f)).length;
 const items=[['all','All'],['active','Active'],['Applied','Applied'],['Screen','Screen'],['Interview','Interview'],['Offer','Offer'],['closed','Closed']];
 $('#filters').innerHTML=items.map(([k,l])=>`<button type="button" data-filter="${k}" aria-pressed="${filter===k}">${l}<span>${count(k)}</span></button>`).join('');
 $('#filters').querySelectorAll('button').forEach(b=>b.onclick=()=>{filter=b.dataset.filter;filters();tickets();});}

function tickets(){const q=$('#search').value.trim().toLowerCase();
 const list=data.applications.filter(a=>inFilter(a)&&`${a.company} ${a.role} ${resumeName(a.resume)}`.toLowerCase().includes(q));
 $('#tickets').innerHTML=list.map(a=>{const h=hoursToApply(a);
  return `<li class="ticket" data-fresh="${freshness(h)}" data-status="${esc(a.status)}" data-id="${a.id}">
   <div class="stub"><b>${span(h)}</b><small>${h==null?'posting time unknown':'after posting'}</small></div>
   <button type="button" class="body" data-edit="${a.id}"><strong>${esc(a.company)}</strong><span class="role">${esc(a.role)}</span><span class="meta">${[a.source,a.resume&&resumeName(a.resume)+' resume','applied '+day(a)].filter(Boolean).map(esc).join(' · ')}</span></button>
   ${a.url?`<a class="link" href="${esc(a.url)}" target="_blank" rel="noopener" aria-label="Open the ${esc(a.company)} posting">Posting ↗</a>`:'<span class="link"></span>'}
   <label class="pill" data-status="${esc(a.status)}"><span class="sr">Status for ${esc(a.company)}</span><select data-status-id="${a.id}">${data.stages.map(s=>`<option ${s===a.status?'selected':''}>${s}</option>`).join('')}</select></label>
  </li>`;}).join('');
 const empty=$('#empty');empty.hidden=!!list.length;
 empty.innerHTML=data.applications.length?'<p>Nothing matches. Try another filter or search.</p>':'<h2>No tickets yet.</h2><p>Sort LinkedIn or Indeed by most recent, apply, then paste the posting URL above. Every ticket shows how fast you got in line.</p>';
 $('#tickets').querySelectorAll('[data-status-id]').forEach(s=>s.onchange=async()=>{const pill=s.parentElement,before=pill.dataset.status;pill.dataset.status=pill.closest('.ticket').dataset.status=s.value;s.disabled=true;
  try{await post('/api/status',{id:Number(s.dataset.statusId),status:s.value});await load();note('');}
  catch(e){pill.dataset.status=s.value=before;s.disabled=false;note(e.message);}});
 $('#tickets').querySelectorAll('[data-edit]').forEach(b=>b.onclick=()=>edit(data.applications.find(a=>a.id===Number(b.dataset.edit))));
 if(printed!=null){const t=$(`.ticket[data-id="${printed}"]`);if(t)t.classList.add('printed');printed=null;}}

// ---------- Quick add: paste a link, check the draft ticket, save ----------
let importing=false;
function chips(selected){$('#postedChips').innerHTML=POSTED.map(([l,v],i)=>`<label><input type="radio" name="posted" value="${v}" ${String(v)===String(selected)?'checked':''}><span>${l}</span></label>`).join('');
 $('#postedChips').querySelectorAll('input').forEach(r=>r.onchange=draftSpeed);}
// Preselect the posting time pulled from the link.
function foundChip(r){const when=postedDate(r.posted);if(!r.posted||isNaN(when))return;$('#postedChips [data-found]')?.remove();
 const day=r.posted_precision==='day',lab=document.createElement('label');lab.dataset.found='1';
 lab.innerHTML=`<input type="radio" name="posted" value="found" checked><span>Posted ${day?when.toLocaleDateString([],{month:'short',day:'numeric'}):span((Date.now()-when)/36e5)+' ago'}</span>`;
 const input=lab.querySelector('input');input.dataset.iso=when.toISOString();input.onchange=draftSpeed;$('#postedChips').prepend(lab);
 $('#draft').dataset.posted=`${lab.textContent} ${VIA[r.posted_via]||''}${day?' (day only)':''}`;draftSpeed();}
function resumeChips(){const files=data.resume_files,box=$('#resumeChips');
 if(!files.length){box.innerHTML=`<input name="resume" maxlength="200" placeholder="Add resumes to ${esc(data.resume_dir)} to pick them here">`;return;}
 const last=recall('resume'),pick=files.includes(last)?last:files[0];
 box.innerHTML=files.map(f=>`<label title="${esc(f)}"><input type="radio" name="resume" value="${esc(f)}" ${f===pick?'checked':''}><span>${esc(resumeName(f))}</span></label>`).join('');}
function postedChoice(){const f=$('#draft'),r=f.querySelector('input[name=posted]:checked');if(!r||r.value==='')return null;return r.dataset.iso?Math.max(0,(Date.now()-new Date(r.dataset.iso))/36e5):Number(r.value);}
function draftSpeed(){const h=postedChoice();$('#draftSpeed').textContent=h==null?'?':span(h);$('#draftSpeedLabel').textContent=h==null?'posting time unknown':'after posting';$('#draft').dataset.fresh=freshness(h);}
// Everything comes from the link; inputs only appear for what it couldn't supply, or after "Fix details".
function openDraft(fields={},info=''){const f=$('#draft');f.reset();
 for(const k of ['company','role','url'])f.elements[k].value=fields[k]||'';
 f.elements.source.innerHTML='<option value="">—</option>'+data.sources.map(s=>`<option>${s}</option>`).join('');
 f.elements.source.value=boardFor(fields.url);resumeChips();
 chips('');$('#draftPosted').textContent='';$('#draft').dataset.posted='';foundChip(fields);
 const missingPost=!fields.posted;$('#postedField').hidden=!missingPost;
 if(missingPost)$('#draftPosted').textContent='This posting doesn’t say when it went up. Check the listing on LinkedIn or Indeed and pick the closest time.';
 $('#details').hidden=!!(f.elements.company.value&&f.elements.role.value);$('#fixDetails').hidden=!$('#details').hidden;
 $('#draftInfo').textContent=info;f.hidden=false;draftSpeed();summary();
 (!f.elements.company.value?f.elements.company:!f.elements.role.value?f.elements.role:missingPost?f.querySelector('input[name=posted]'):f.querySelector('button[type=submit]')).focus();}
function summary(){const f=$('#draft'),el=f.elements;
 $('#summary').hidden=!(el.company.value||el.role.value);
 $('#sumCompany').textContent=el.company.value;$('#sumRole').textContent=el.role.value;
 $('#sumMeta').textContent=[f.dataset.posted,el.source.value&&!(f.dataset.posted||'').includes(el.source.value)&&'found on '+el.source.value].filter(Boolean).join(' · ');
 duplicateNote();}
function duplicateNote(){const f=$('#draft'),key=x=>x.trim().toLowerCase(),c=key(f.elements.company.value),r=key(f.elements.role.value);
 const dup=c&&r&&data.applications.find(a=>key(a.company)===c&&key(a.role)===r);
 $('#draftDup').textContent=dup?`You already have a ticket for this role, applied ${day(dup)}.`:'';}
function closeDraft(){$('#draft').hidden=true;$('#quickUrl').value='';$('#quickUrl').focus();}
// Sites that turn away automated reads; their postings come in through the bookmark instead.
const BLOCKED=[[/(^|\.)indeed\./,'Indeed'],[/(^|\.)glassdoor\./,'Glassdoor'],[/(^|\.)ziprecruiter\./,'ZipRecruiter']];
function blockedSite(url){try{const h=new URL(url).hostname;return (BLOCKED.find(([r])=>r.test(h))||[])[1]||'';}catch{return '';}}
function showBlocked(site,url){$('#blockedSite').textContent=site||'This site';$('#openPosting').href=url;$('#openPosting').textContent='Open the posting on '+(site||'the site');$('#blocked').hidden=false;}
// The bookmark runs on the posting page in your browser, collects what the page knows, and opens it here.
const BOOKMARKLET=`javascript:(()=>{if(location.origin==='${location.origin}'){alert('Open a job posting on Indeed or any job site, then click Add to Job Tracker on that page.');return}const q=s=>[...document.querySelectorAll(s)],t=q('script:not([src])').map(s=>s.textContent).join('\\n'),m=r=>{const x=t.match(r);return x?x[1]:''},a=m(/"age"\\s*:\\s*"([^"]{1,60})"/)||m(/"formattedRelativeTime"\\s*:\\s*"([^"]{1,60})"/),d={url:location.href,title:document.title,h1:(q('h1')[0]||{}).innerText||'',og:(q('meta[property="og:title"]')[0]||{}).content||'',ld:q('script[type="application/ld+json"]').map(s=>s.textContent.slice(0,30000)),company:m(/"companyName"\\s*:\\s*"([^"]{1,200})"/),role:m(/"jobTitle"\\s*:\\s*"([^"]{1,300})"/),age:/ago|today|yesterday|just/i.test(a)?a:'',pub:m(/"pubDate"\\s*:\\s*(\\d{13})/),datePosted:m(/"datePosted"\\s*:\\s*"([^"]{8,40})"/),text:(document.body.innerText.match(/(?:posted|reposted)[^\\n]{0,40}?(?:ago|today|yesterday)/i)||[''])[0]};window.open('${location.origin}/\\x23import='+encodeURIComponent(JSON.stringify(d)),'job-tracker')})()`;
$('#bookmarklet').href=BOOKMARKLET;$('#bookmarklet').onclick=e=>{e.preventDefault();note('Drag the button to your bookmarks bar, then click it on a job posting.');};
$('#copyBookmarklet').onclick=async()=>{try{await navigator.clipboard.writeText(BOOKMARKLET);note('Copied. Make a new bookmark named Add to Job Tracker and paste this as its URL.');}catch{note('Copy failed. Drag the button to your bookmarks bar instead.');}};
async function importFromBookmark(){const m=/^#import=(.*)$/s.exec(location.hash);if(!m)return;history.replaceState(null,'',location.pathname);
 let d;try{d=JSON.parse(decodeURIComponent(m[1]));}catch{note('The bookmark sent something unreadable. Try it again on the posting.');return;}
 if(String(d.url||'').startsWith(location.origin)){note('The bookmark ran on the tracker itself. Open the job posting on Indeed, then click Add to Job Tracker on that page.');return;}
 try{const r=await post('/api/import-captured',d);$('#blocked').hidden=true;$('#quickUrl').value=r.url;openDraft(r,r.warning||'');}catch(err){note(err.message);}}
window.addEventListener('hashchange',importFromBookmark);
$('#quick').onsubmit=async e=>{e.preventDefault();if(importing)return;let v=$('#quickUrl').value.trim();$('#blocked').hidden=true;
 if(!/^https?:\/\//i.test(v)&&/^[^\s]+\.[^\s]{2,}/.test(v))v='https://'+v;
 if(!/^https?:\/\//i.test(v)){note('Paste the link to the job posting, starting with https://');$('#quickUrl').focus();return;}
 note('');
 if(blockedSite(v)){$('#draft').hidden=true;showBlocked(blockedSite(v),v);return;}
 importing=true;$('#quickGo').disabled=true;$('#quickGo').textContent='Reading posting…';
 try{const r=await post('/api/import-url',{url:v});openDraft({...r,url:r.url||v},r.warning||'');
}
 catch(err){if(/HTTP 40[13]|log ?in|block/i.test(err.message)){$('#draft').hidden=true;showBlocked('',v);}else openDraft({url:v},err.message);}
 finally{importing=false;$('#quickGo').disabled=false;$('#quickGo').textContent='Take a ticket';}};
$('#fixDetails').onclick=()=>{$('#details').hidden=false;$('#fixDetails').hidden=true;$('#draft').elements.company.focus();};
$('#draftCancel').onclick=closeDraft;
$('#draft').elements.company.oninput=$('#draft').elements.role.oninput=$('#draft').elements.source.onchange=summary;
$('#draft').onkeydown=e=>{if(e.key==='Escape'){e.preventDefault();closeDraft();}};
$('#draft').onsubmit=async e=>{e.preventDefault();const f=e.target,h=postedChoice(),at=new Date(),found=f.querySelector('input[name=posted]:checked')?.dataset.iso;
 const d={company:f.elements.company.value,role:f.elements.role.value,url:f.elements.url.value,source:f.elements.source.value,resume:f.elements.resume.value,status:'Applied',
  applied_at:at.toISOString(),applied:at.toLocaleDateString('en-CA'),posted_at:found||(h==null?'':new Date(at-h*36e5).toISOString())};
 try{const r=await post('/api/application',d);remember('resume',d.resume);remember('source',d.source);printed=r.id;if(filter!=='all'&&filter!=='active'&&filter!=='Applied')filter='all';closeDraft();await load();note('');}
 catch(err){$('#draftInfo').textContent=err.message;}};

// ---------- Full editor ----------
function edit(a){const f=$('#form');f.reset();
 f.elements.status.innerHTML=data.stages.map(s=>`<option>${s}</option>`).join('');
 f.elements.source.innerHTML='<option value="">—</option>'+data.sources.map(s=>`<option>${s}</option>`).join('');
 const choices=[...data.resume_files,...(a.resume&&!data.resume_files.includes(a.resume)?[a.resume]:[])];
 f.elements.resume.innerHTML='<option value="">None picked</option>'+choices.map(r=>`<option value="${esc(r)}">${esc(resumeName(r))}</option>`).join('');
 for(const k of ['id','company','role','status','source','resume','url','notes'])f.elements[k].value=a[k]??'';
 f.elements.posted_at.value=localInput(a.posted_at);
 // Older rows only know the day they were applied; keep that until a time is entered.
 const applied=a.applied_at?localInput(a.applied_at):a.applied+'T12:00';f.elements.applied_at.value=applied;f.elements.applied_at.dataset.initial=a.applied_at?'':applied;
 $('#formError').textContent='';$('#editor').showModal();}
$('#close').onclick=()=>$('#editor').close();
$('#form').onsubmit=async e=>{e.preventDefault();const f=e.target,el=f.elements,untouched=el.applied_at.dataset.initial&&el.applied_at.value===el.applied_at.dataset.initial;
 const d={id:el.id.value,company:el.company.value,role:el.role.value,status:el.status.value,source:el.source.value,resume:el.resume.value,url:el.url.value,notes:el.notes.value,
  posted_at:fromLocalInput(el.posted_at.value),applied_at:untouched?'':fromLocalInput(el.applied_at.value),applied:el.applied_at.value.slice(0,10)};
 try{await post('/api/application',d);$('#editor').close();await load();}catch(err){$('#formError').textContent=err.message;}};
$('#delete').onclick=async()=>{if(!confirm('Delete this application?'))return;try{await post('/api/delete',{id:$('#form').elements.id.value});$('#editor').close();await load();}catch(e){$('#formError').textContent=e.message;}};

$('#search').oninput=tickets;
// Roll the daily count over when you come back to the tab the next day.
document.addEventListener('visibilitychange',()=>{if(!document.hidden)tally();});
load().then(importFromBookmark).catch(()=>note('Could not reach the tracker. Start it again and refresh this page.'));
