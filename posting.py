"""Extract public posting details, including when the job was posted; no AI or browser dependencies."""
import html
import http.client
import ipaddress
import json
import re
import socket
import ssl
from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
from urllib.parse import urlsplit, urljoin

class PostingError(ValueError): pass

class PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.scripts=[]; self.meta={}; self.title=[]; self.headings=[]; self.capture=None; self.buffer=[]; self.ld=False; self.heading_done=False
    def handle_starttag(self, tag, attrs):
        a=dict(attrs)
        if tag=='meta': self.meta[(a.get('property') or a.get('name') or '').lower()]=a.get('content','')
        if tag=='script':
            self.ld=a.get('type','').lower().split(';')[0]=='application/ld+json'; self.buffer=[]
        if tag=='title' or (tag=='h1' and not self.heading_done): self.capture=tag
    def handle_data(self, text):
        if self.ld:self.buffer.append(text)
        if self.capture=='title':self.title.append(text)
        if self.capture=='h1':self.headings.append(text)
    def handle_endtag(self, tag):
        if tag=='script':
            if self.ld:self.scripts.append(''.join(self.buffer))
            self.ld=False
        if tag==self.capture:
            if tag=='h1':self.heading_done=True
            self.capture=None

class TextParser(HTMLParser):
    def __init__(self):super().__init__();self.parts=[];self.hidden=0
    def handle_starttag(self,tag,attrs):
        if tag in ('script','style'):self.hidden+=1
        if tag in ('p','div','li','br','h1','h2','h3'):self.parts.append('\n')
    def handle_endtag(self,tag):
        if tag in ('script','style'):self.hidden=max(0,self.hidden-1)
        if tag in ('p','div','li'):self.parts.append('\n')
    def handle_data(self,s):
        if not self.hidden:self.parts.append(s)
def clean(value,limit=12000):
    if not isinstance(value,(str,int,float)):return ''
    p=TextParser();p.feed(str(value));return re.sub(r'\n\s*\n+', '\n\n', ''.join(p.parts)).strip()[:limit]
def nodes(value):
    if isinstance(value,list):
        for v in value:yield from nodes(v)
    elif isinstance(value,dict):
        yield value
        for v in value.values():
            if isinstance(v,(dict,list)):yield from nodes(v)
def validate_url(url):
    try:
        p=urlsplit(url)
        if p.scheme not in ('https','http') or not p.hostname or p.username or p.password or p.port not in (None,80,443):raise ValueError()
        if len(url)>4096:raise ValueError()
        addresses=socket.getaddrinfo(p.hostname,p.port or (443 if p.scheme=='https' else 80),type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):raise ValueError()
        return p,addresses[0][4][0]
    except (ValueError,OSError):raise PostingError('Use a public http or https job posting URL.')
def fetch_page(url, json_mode=False):
    cookies={}
    for _ in range(6):
        p,address=validate_url(url); port=p.port or (443 if p.scheme=='https' else 80)
        conn=http.client.HTTPConnection(p.hostname,port,timeout=15)
        # Pin the socket to the validated public address, including for every redirect.
        sock=socket.create_connection((address,port),timeout=15)
        if p.scheme=='https':sock=ssl.create_default_context().wrap_socket(sock,server_hostname=p.hostname)
        conn.sock=sock
        try:
            headers={'User-Agent':'Mozilla/5.0 (compatible; LocalJobTracker/1.0)','Accept':'application/json' if json_mode else 'text/html,application/xhtml+xml','Accept-Encoding':'identity'}
            jar='; '.join(k+'='+v for k,(domain,v) in cookies.items() if p.hostname==domain or p.hostname.endswith('.'+domain))
            if jar:headers['Cookie']=jar
            conn.request('GET',(p.path or '/')+('?' + p.query if p.query else ''),headers=headers)
            response=conn.getresponse()
            # Keep session cookies across redirects; sites like PeopleSoft bounce to a login page without them.
            for header in (response.msg.get_all('Set-Cookie') or []) if hasattr(response,'msg') else []:
                pair,_,attrs=header.partition(';');name,eq,value=pair.partition('=')
                domain=(re.search(r'(?i)(?:^|;)\s*domain=\.?([^;\s]+)',attrs) or [None,p.hostname])[1].lower()
                if eq and name.strip() and (p.hostname==domain or p.hostname.endswith('.'+domain)):cookies[name.strip()]=(domain,value.strip())
            if response.status in (301,302,303,307,308):
                location=response.getheader('Location')
                if not location:raise PostingError('This posting redirected without a destination.')
                url=urljoin(url,location);continue
            if response.status!=200:raise PostingError('This site could not be read (HTTP '+str(response.status)+'). Try the company’s direct posting or enter the fields manually.')
            if not any(t in response.getheader('Content-Type','').lower() for t in (('application/json',) if json_mode else ('text/html','application/xhtml+xml'))):raise PostingError('This URL does not point to an HTML job posting.')
            content=response.read(2_000_001)
            if len(content)>2_000_000:raise PostingError('This page is too large to import. Try the direct posting URL.')
            charset=re.search(r'charset=([\w-]+)',response.getheader('Content-Type',''))
            return content.decode(charset.group(1) if charset else 'utf-8',errors='replace'),url
        finally:conn.close()
    raise PostingError('Too many redirects. Try the direct job posting URL.')
def parse_posting(source,url):
    p=PageParser();p.feed(source); jobs=[]
    for script in p.scripts:
        try:
            for n in nodes(json.loads(script)):
                types=n.get('@type',[]);types=[types] if isinstance(types,str) else types
                if isinstance(types,list) and any(str(t).split('/')[-1]=='JobPosting' for t in types):jobs.append(n)
        except (ValueError,TypeError,RecursionError):continue
    if len(jobs)>1:
        matched=[j for j in jobs if str(j.get('url','')).rstrip('/')==url.rstrip('/')]
        if len(matched)!=1:raise PostingError('This page contains several jobs. Paste the URL of one specific posting.')
        jobs=matched
    company=role=description=posted='';details=[]
    if jobs:
        j=jobs[0];org=j.get('hiringOrganization',{});company=clean(org.get('name','') if isinstance(org,dict) else org,200);role=clean(j.get('title') or j.get('name',''),300);description=clean(j.get('description',''))
        locations=j.get('jobLocation',[]);locations=locations if isinstance(locations,list) else [locations];names=[]
        for place in locations:
            if not isinstance(place,dict):continue
            address=place.get('address',{})
            if isinstance(address,str):names.append(clean(address,300));continue
            if not isinstance(address,dict):continue
            parts=[]
            for k in ('addressLocality','addressRegion','addressCountry'):
                v=address.get(k,'');v=v.get('name','') if isinstance(v,dict) else v
                if clean(v):parts.append(clean(v,100))
            if parts:names.append(', '.join(parts))
        if j.get('jobLocationType')=='TELECOMMUTE':names.insert(0,'Remote')
        if names:details.append('Location: '+' / '.join(dict.fromkeys(names)))
        employment=j.get('employmentType','');employment=employment if isinstance(employment,list) else [employment]
        types=[clean(t,80).replace('_',' ').title() for t in employment if clean(t)]
        if types:details.append('Employment: '+', '.join(types))
        salary=j.get('baseSalary')
        if isinstance(salary,dict):
            value=salary.get('value',{});currency=clean(salary.get('currency',''),15)
            if isinstance(value,dict):
                low=value.get('minValue');high=value.get('maxValue');amount=(str(low)+'–'+str(high)) if low is not None and high is not None else clean(value.get('value',low if low is not None else high));unit=clean(value.get('unitText',''),30).lower()
                salary=' '.join(s for s in [currency,amount,('/'+unit if unit else '')] if s)
            else:salary=' '.join(s for s in [currency,clean(value,100)] if s)
        if isinstance(salary,(str,int,float)) and clean(salary):details.append('Salary: '+clean(salary,200))
        if j.get('datePosted'):posted=clean(j['datePosted'],100);details.append('Posted: '+posted)
    else:
        title=' '.join(p.title) if re.search(r'\s+at\s+', ' '.join(p.title), re.I) else (p.meta.get('og:title') or ' '.join(p.title) or ' '.join(p.headings))
        title=re.sub(r'^Job Application for\s+', '', title, flags=re.I)
        m=re.match(r'^(.+?)\s+at\s+(.+?)(?:\s+[|–—]\s+.*)?$',title,re.I)
        if m:role=clean(m.group(1),300);company=clean(m.group(2),200)
        else:role=clean(' '.join(p.headings) or title,300)
        description=clean(p.meta.get('description') or p.meta.get('og:description',''),2000)
    notes='\n'.join(details)+ ('\n\n'+description if description else '')
    warnings=[]
    if not jobs:warnings.append('Only page metadata was available. Check the title and fill in any missing fields.')
    if not company:warnings.append('Company was not found.')
    if not role:warnings.append('Role was not found.')
    return {'company':company,'role':role,'url':url,'posted':posted,'notes':notes.strip(),'warning':' '.join(warnings),'source':'structured' if jobs else 'metadata'}
class PeopleSoftParser(HTMLParser):
    """Collect text from PeopleSoft Candidate Gateway fields, keyed by element id."""
    def __init__(self):super().__init__();self.fields={};self.capture=None
    def handle_starttag(self,tag,attrs):
        if self.capture:
            if tag==self.capture[1]:self.capture[2]+=1
            if tag in ('p','div','li','br','h1','h2','h3'):self.fields[self.capture[0]].append('\n')
            return
        id=dict(attrs).get('id') or ''
        if re.fullmatch(r'HRS_SCH_WRK2?_[A-Z0-9_]+|HRS_SCH_WRK_DESCR100\$\d+lbl|HRS_SCH_PSTDSC_DESCRLONG\$\d+',id):self.capture=[id,tag,1];self.fields[id]=[]
    def handle_endtag(self,tag):
        if not self.capture:return
        if tag in ('p','div','li'):self.fields[self.capture[0]].append('\n')
        if tag==self.capture[1]:
            self.capture[2]-=1
            if not self.capture[2]:self.capture=None
    def handle_data(self,s):
        if self.capture:self.fields[self.capture[0]].append(s)
    def text(self,id):return re.sub(r'\n\s*\n+','\n\n',re.sub(r'[ \t\xa0]+',' ',''.join(self.fields.get(id,[])))).strip()
UC_CAMPUSES={'ucb':'UC Berkeley','ucberkeley':'UC Berkeley','ucdavis':'UC Davis','uci':'UC Irvine','ucla':'UCLA','ucm':'UC Merced','ucmerced':'UC Merced','ucr':'UC Riverside','ucsd':'UC San Diego','ucsf':'UCSF','ucsb':'UC Santa Barbara','ucsc':'UC Santa Cruz','ucop':'UC Office of the President','ucanr':'UC Agriculture and Natural Resources'}
def peoplesoft_posting(source,url):
    """PeopleSoft Candidate Gateway (e.g. University of California careers) has no structured data, only labelled fields."""
    if "HRS_SCH_WRK2_POSTING_TITLE" not in source:return None
    p=PeopleSoftParser();p.feed(source);role=p.text('HRS_SCH_WRK2_POSTING_TITLE')[:300]
    if not role:return None
    parts=urlsplit(url);site=(re.match(r'/psc/([^/]+)/',parts.path) or [None,''])[1].lower()
    company=UC_CAMPUSES.get(site,'University of California') if (parts.hostname or '').endswith('universityofcalifornia.edu') else ''
    details=[label+': '+p.text(id) for label,id in (('Location','HRS_SCH_WRK_HRS_DESCRLONG'),('Employment','HRS_SCH_WRK_HRS_FULL_PART_TIME'),('Job ID','HRS_SCH_WRK2_HRS_JOB_OPENING_ID')) if p.text(id)]
    rows=sorted({int(k.split('$')[1]) for k in p.fields if k.startswith('HRS_SCH_PSTDSC_DESCRLONG$')})
    sections=['\n'.join(x for x in (p.text('HRS_SCH_WRK_DESCR100$'+str(n)+'lbl'),p.text('HRS_SCH_PSTDSC_DESCRLONG$'+str(n))) if x) for n in rows]
    description='\n\n'.join(x for x in sections if x)[:12000]
    notes='\n'.join(details)+('\n\n'+description if description else '')
    return {'company':company,'role':role,'url':url,'posted':'','notes':notes.strip(),'warning':'' if company else 'Company was not found.','source':'peoplesoft'}
def local_now():return datetime.now().astimezone()
def normalize_posted(raw):
    """Posting date from structured data -> (value, precision); a bare day stays 'YYYY-MM-DD'."""
    raw=str(raw or '').strip()
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}',raw):return raw,'day'
    try:t=datetime.fromisoformat(raw.replace('Z','+00:00'))
    except ValueError:return '',''
    # Many sites stamp midnight or omit the zone when they only know the day.
    if t.tzinfo is None or (t.hour,t.minute,t.second)==(0,0,0):return t.date().isoformat(),'day'
    return t.astimezone(timezone.utc).isoformat(),'time'
def relative_posted(text,now=None,anchored=True):
    """Parse 'Posted 14 hours ago', 'Posted 30+ Days Ago', 'Just posted' -> (value, precision, matched text)."""
    now=now or local_now();text=html.unescape(str(text))
    lead=r'(?:posted|reposted|listed|published)\s*:?\s*' if anchored else r'(?:(?:posted|reposted)\s*:?\s*)?'
    m=re.search(lead+r'(\d+|an?|one)(\+)?\s*(minute|min|hour|hr|day|week|month)s?\s+ago',text,re.I)
    if m:
        n=1 if m.group(1).lower() in ('a','an','one') else int(m.group(1));unit=m.group(3).lower()
        hours={'minute':1/60,'min':1/60,'hour':1,'hr':1,'day':24,'week':168,'month':720}[unit]*n
        when=now-timedelta(hours=hours)
        if unit in ('minute','min','hour','hr'):return when.astimezone(timezone.utc).isoformat(),'hour',m.group(0).strip()
        return when.date().isoformat(),'day',m.group(0).strip()
    m=re.search(r'\b(just posted|posted today|posted yesterday)\b',text,re.I) or (None if anchored else re.fullmatch(r'\s*(today|yesterday)\s*',text,re.I))
    if m:return (now-timedelta(days=1 if 'yesterday' in m.group(1).lower() else 0)).date().isoformat(),'day',m.group(0).strip()
    return '','',''
def page_text(source):
    p=TextParser();p.feed(source);return re.sub(r'\s*\n\s*','\n',re.sub(r'[ \t]+',' ',''.join(p.parts))).strip()[:40000]
def with_posted(result,value,precision,via,label=''):
    result.update(posted=value,posted_precision=precision,posted_via=via,posted_text=label);return result
def linkedin_posting(url):
    p=urlsplit(url);m=re.search(r'currentJobId=(\d+)',p.query) or re.search(r'/jobs/view/(?:[^/]*?-)?(\d+)/?$',p.path)
    if not m:return None
    source,_=fetch_page('https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/'+m.group(1))
    def pick(cls):
        found=re.search(r'class="[^"]*\b'+cls+r'\b[^"]*"[^>]*>(.*?)</',source,re.S);return clean(found.group(1),300) if found else ''
    body=re.search(r'class="[^"]*show-more-less-html__markup[^"]*"[^>]*>(.*?)</div>',source,re.S)
    location=pick('topcard__flavor--bullet');notes=('Location: '+location+'\n\n' if location else '')+(clean(body.group(1)) if body else '')
    result={'company':pick('topcard__org-name-link') or pick('topcard__flavor'),'role':pick('topcard__title'),'url':'https://www.linkedin.com/jobs/view/'+m.group(1)+'/','notes':notes.strip(),'warning':'','source':'linkedin'}
    ago=pick('posted-time-ago__text')
    return with_posted(result,*relative_posted(ago,anchored=False)[:2],'linkedin',ago)
def oracle_posting(url):
    """Oracle Recruiting Cloud pages render in the browser; their public job feed has the details and exact posting time."""
    p=urlsplit(url);m=re.search(r'/hcmUI/CandidateExperience/[^/]+/sites/([^/]+)/job/(\d+)',p.path)
    if not (p.hostname or '').endswith('.oraclecloud.com') or not m:return None
    site,job_id=m.groups()
    feed='https://'+p.hostname+'/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails?expand=all&onlyData=true&finder=ById;Id=%22'+job_id+'%22,siteNumber='+site
    items=json.loads(fetch_page(feed,json_mode=True)[0]).get('items') or []
    if not items:return None
    job=items[0];about=re.match(r'\s*About ([A-Z][\w&.\'-]*(?: [A-Z][\w&.\'-]*){0,4})',clean(job.get('OrganizationDescriptionStr') or job.get('CorporateDescriptionStr') or '',300))
    company=about.group(1) if about else ''
    if not company:
        try:company=clean(' '.join(re.findall(r'<title>([^<]*)',fetch_page(url)[0])[:1]),200)
        except PostingError:pass
    location=clean(job.get('PrimaryLocation') or '',200);description=clean((job.get('ShortDescriptionStr') or '')+'\n\n'+(job.get('ExternalDescriptionStr') or ''))
    result={'company':company,'role':clean(job.get('Title') or '',300),'url':url,'notes':(('Location: '+location+'\n\n') if location else '')+description,'warning':'' if company else 'Company was not found.','source':'oracle'}
    return with_posted(result,*normalize_posted(job.get('ExternalPostedStartDate')),'oracle')
def workday_posted(url):
    p=urlsplit(url);m=re.fullmatch(r'(?:/[a-z]{2}-[A-Z]{2})?/([^/]+)/(job/.+?)/?',p.path)
    if not (p.hostname or '').endswith('.myworkdayjobs.com') or not m:return None
    tenant=p.hostname.split('.')[0];job=json.loads(fetch_page('https://'+p.hostname+'/wday/cxs/'+tenant+'/'+m.group(1)+'/'+m.group(2),json_mode=True)[0])
    info=dict(job.get('jobPostingInfo',{}),company=(job.get('hiringOrganization') or {}).get('name',''))
    label=clean(info.get('postedOn',''),60)
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}',str(info.get('startDate',''))):return info,str(info['startDate']),'day',label
    value,precision,_=relative_posted(label);return info,value,precision,label
def lever_or_ashby_posted(url):
    p=urlsplit(url);parts=[x for x in p.path.split('/') if x]
    if p.hostname=='jobs.lever.co' and len(parts)>=2:
        job=json.loads(fetch_page('https://api.lever.co/v0/postings/'+parts[0]+'/'+parts[1],json_mode=True)[0])
        if job.get('createdAt'):return datetime.fromtimestamp(job['createdAt']/1000,timezone.utc).isoformat(),'lever'
    if p.hostname=='jobs.ashbyhq.com' and len(parts)>=2:
        board=json.loads(fetch_page('https://api.ashbyhq.com/posting-api/job-board/'+parts[0],json_mode=True)[0])
        job=next((j for j in board.get('jobs',[]) if j.get('id')==parts[1]),None)
        if job and job.get('publishedAt'):return normalize_posted(job['publishedAt'])[0],'ashby'
    return None
def import_captured(d):
    """Details read by the bookmark button inside your own browser, for sites like Indeed that block the tracker."""
    url=str(d.get('url','')).strip()[:4096]
    if not re.match(r'https?://',url):raise PostingError('The bookmark sent a page without a web address.')
    text=lambda k,n:str(d.get(k) or '')[:n]
    def unescape(raw):
        try:return json.loads('"'+raw+'"')
        except ValueError:return raw
    scripts=''.join('<script type="application/ld+json">'+str(x)[:30000].replace('</','<\\/')+'</script>' for x in list(d.get('ld') or [])[:5])
    shell='<title>'+html.escape(text('title',300))+'</title><meta property="og:title" content="'+html.escape(text('og',300))+'"><h1>'+html.escape(text('h1',300))+'</h1>'
    result=parse_posting(scripts+shell,url);structured=result['source']=='structured'
    company=clean(unescape(text('company',400)),200);role=clean(unescape(text('role',600)),300)
    if company and not result['company']:result['company']=company
    if role and (not result['role'] or not structured):result['role']=role
    result['warning']=' '.join(w for w in ['Company was not found.' if not result['company'] else '','Role was not found.' if not result['role'] else ''] if w)
    host=(urlsplit(url).hostname or '');via='indeed' if re.search(r'(^|\.)indeed\.',host) else 'page'
    value,precision=normalize_posted(result.pop('posted','') or unescape(text('datePosted',40)))
    if re.fullmatch(r'\d{13}',text('pub',13)):value,precision=datetime.fromtimestamp(int(text('pub',13))/1000,timezone.utc).isoformat(),'time'
    if precision=='time':return with_posted(result,value,precision,via)
    for phrase,anchored in ((text('age',60),False),(text('text',120),True)):
        found=relative_posted(unescape(phrase),anchored=anchored)
        if found[0] and (not value or found[1]=='hour'):return with_posted(result,found[0],found[1],via,found[2])
    return with_posted(result,value,precision,via if value else '')
def import_posting(url):
    try:
        url=str(url).strip(); p=urlsplit(url)
        greenhouse=re.fullmatch(r'/([A-Za-z0-9_-]+)/jobs/([0-9]+)/?',p.path)
        if p.scheme=='https' and p.hostname in ('boards.greenhouse.io','job-boards.greenhouse.io') and not p.username and not p.password and p.port in (None,443) and greenhouse:
            board,job_id=greenhouse.groups();base='https://boards-api.greenhouse.io/v1/boards/'+board
            job=json.loads(fetch_page(base+'/jobs/'+job_id,json_mode=True)[0]);org=json.loads(fetch_page(base,json_mode=True)[0])
            data={'@type':'JobPosting','title':job.get('title',''),'hiringOrganization':{'name':org.get('name','')},'description':html.unescape(job.get('content','')),'jobLocation':{'address':job.get('location',{}).get('name','')}}
            result=parse_posting('<script type="application/ld+json">'+json.dumps(data).replace('</','<\/')+'</script>',url);result['source']='greenhouse'
            # first_published only: updated_at changes whenever the posting is edited.
            value,precision=normalize_posted(job.get('first_published'))
            return with_posted(result,value,precision,'greenhouse')
        if p.scheme=='https' and re.fullmatch(r'(www\.)?linkedin\.com',p.hostname or ''):
            result=linkedin_posting(url)
            if result:return result
        if p.scheme=='https' and (p.hostname or '').endswith('.oraclecloud.com'):
            result=oracle_posting(url)
            if result:return result
        try:workday=workday_posted(url)
        except (PostingError,ValueError):workday=None
        try:direct=lever_or_ashby_posted(url)
        except (PostingError,ValueError):direct=None
        source,final_url=fetch_page(url);result=peoplesoft_posting(source,url) or parse_posting(source,final_url);text=page_text(source)
        if workday:
            info,value,precision,label=workday
            if not result['role'] and info.get('title'):result['role']=clean(info['title'],300);result['warning']=result['warning'].replace('Role was not found.','').strip()
            if not result['company'] and info.get('company'):result['company']=clean(info['company'],200);result['warning']=result['warning'].replace('Company was not found.','').strip()
            if not result['notes'] and info.get('jobDescription'):result['notes']=('Location: '+clean(info.get('location',''),200)+'\n\n' if info.get('location') else '')+clean(info['jobDescription'])
            if value:return with_posted(result,value,precision,'workday',label)
        if direct:return with_posted(result,direct[0],'time',direct[1])
        value,precision=normalize_posted(result.pop('posted',''))
        if precision!='time':
            found=relative_posted(text)
            if found[0]:return with_posted(result,found[0],found[1],'page',found[2])
        return with_posted(result,value,precision,'structured' if value else '')
    except PostingError:raise
    except Exception:raise PostingError('Could not read this posting. The site may require a login or block imports. Try the company’s direct posting or enter the fields manually.')
