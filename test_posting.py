import json,unittest
from unittest.mock import patch
from posting import parse_posting,validate_url,fetch_page,PostingError,import_posting

class PostingTests(unittest.TestCase):
 def page(self,data):return '<script type="application/ld+json">'+json.dumps(data)+'</script>'
 def test_full_posting(self):
  job={'@type':'JobPosting','title':'Backend Engineer','hiringOrganization':{'name':'Acme'},'description':'<p>Build APIs.</p><ul><li>Python</li></ul>','jobLocation':{'address':{'addressLocality':'Seattle','addressRegion':'WA','addressCountry':{'name':'US'}}},'jobLocationType':'TELECOMMUTE','baseSalary':{'currency':'USD','value':{'minValue':100000,'maxValue':150000,'unitText':'YEAR'}},'employmentType':['FULL_TIME'],'datePosted':'2026-10-08'}
  r=parse_posting(self.page({'@graph':[{'@type':'WebPage'},job]}),'https://example.com/job')
  self.assertEqual((r['company'],r['role']),('Acme','Backend Engineer'));self.assertEqual(r['warning'],'')
  for value in ['Remote','Seattle, WA, US','USD 100000–150000 /year','Full Time','Build APIs.','Python','Posted: 2026-10-08']:self.assertIn(value,r['notes'])
 def test_multiple_jobs_needs_specific_url(self):
  data=[{'@type':'JobPosting','title':'One'},{'@type':'JobPosting','title':'Two'}]
  with self.assertRaises(PostingError):parse_posting(self.page(data),'https://example.com/jobs')
  data[1]['url']='https://example.com/two';self.assertEqual(parse_posting(self.page(data),'https://example.com/two')['role'],'Two')
 def test_malformed_json_falls_back_without_inventing_company(self):
  r=parse_posting('<script type="application/ld+json">{broken</script><title>Careers</title><h1>Software Engineer</h1>','https://example.com/job')
  self.assertEqual(r['company'],'');self.assertEqual(r['role'],'Software Engineer');self.assertIn('Company was not found',r['warning'])
 def test_metadata_title(self):
  r=parse_posting('<meta property="og:title" content="Designer at Example &amp; Co"><meta name="description" content="Design products">','https://example.com/job')
  self.assertEqual((r['company'],r['role']),('Example & Co','Designer'));self.assertIn('Design products',r['notes'])
 def test_greenhouse_uses_public_posting_and_company_data(self):
  job={'title':'Platform Engineer','location':{'name':'Remote'},'content':'&lt;p&gt;Build systems.&lt;/p&gt;'}
  with patch('posting.fetch_page',side_effect=[(json.dumps(job),'unused'),(json.dumps({'name':'Example Co'}),'unused')]) as fetch:
   r=import_posting('https://job-boards.greenhouse.io/example/jobs/123')
   self.assertEqual((r['company'],r['role']),('Example Co','Platform Engineer'));self.assertIn('Build systems.',r['notes']);self.assertIn('Location: Remote',r['notes']);self.assertEqual(fetch.call_count,2)
 def test_only_first_heading_is_used(self):
  r=parse_posting('<h1>Engineer</h1><h1>About us</h1>','https://example.com/job');self.assertEqual(r['role'],'Engineer')
 def test_scripts_are_not_saved_as_notes(self):
  r=parse_posting(self.page({'@type':['JobPosting'],'title':'Engineer','hiringOrganization':{'name':'Acme'},'description':'<p>Work</p><script>alert(1)</script>'}),'https://example.com/job')
  self.assertNotIn('alert',r['notes'])
 def test_private_urls_and_credentials_are_rejected(self):
  for url in ['file:///etc/passwd','http://user:password@example.com/job','http://localhost/job','http://127.0.0.1/job','http://169.254.169.254/latest/meta-data','http://[::1]/job','http://example.com:3005/job']:
   with self.subTest(url=url),self.assertRaises(PostingError):validate_url(url)
 def test_mixed_dns_rejected(self):
  with patch('posting.socket.getaddrinfo',return_value=[(2,1,6,'',('8.8.8.8',443)),(2,1,6,'',('127.0.0.1',443))]),self.assertRaises(PostingError):validate_url('https://example.com/job')
 def test_redirect_to_private_is_rejected(self):
  class Response:
   status=302
   def getheader(self,name,default=''):return 'http://127.0.0.1/secret'
  with patch('posting.socket.getaddrinfo',side_effect=[[(2,1,6,'',('8.8.8.8',80))],[(2,1,6,'',('127.0.0.1',80))]]),patch('posting.socket.create_connection'),patch('posting.http.client.HTTPConnection') as conn:
   conn.return_value.getresponse.return_value=Response()
   with self.assertRaises(PostingError):fetch_page('http://example.com/job')

 def test_posted_dates_keep_their_precision(self):
  from posting import normalize_posted
  self.assertEqual(normalize_posted('2026-10-15'),('2026-10-15','day'))
  self.assertEqual(normalize_posted('2026-10-15T00:00:00Z'),('2026-10-15','day'))
  self.assertEqual(normalize_posted('2026-10-15T09:30:00'),('2026-10-15','day'))
  self.assertEqual(normalize_posted('2026-10-01T18:17:28-04:00'),('2026-10-01T22:17:28+00:00','time'))
  self.assertEqual(normalize_posted('soon'),('',''))
 def test_relative_posted_phrases(self):
  from posting import relative_posted
  from datetime import datetime,timezone
  now=datetime(2026,10,22,20,0,tzinfo=timezone.utc)
  self.assertEqual(relative_posted('Engineer · Posted 3 hours ago · 40 applicants',now)[:2],('2026-10-22T17:00:00+00:00','hour'))
  self.assertEqual(relative_posted('Posted 30+ Days Ago',now)[:2],('2026-09-22','day'))
  self.assertEqual(relative_posted('Just posted',now)[:2],('2026-10-22','day'))
  self.assertEqual(relative_posted('Our founder joined 3 days ago',now)[0],'')
  self.assertEqual(relative_posted('14 hours ago',now,anchored=False)[:2],('2026-10-22T06:00:00+00:00','hour'))
 def test_greenhouse_returns_first_published_time(self):
  job={'title':'Platform Engineer','location':{'name':'Remote'},'content':'x','first_published':'2026-10-01T18:17:28-04:00'}
  with patch('posting.fetch_page',side_effect=[(json.dumps(job),'unused'),(json.dumps({'name':'Example Co'}),'unused')]):
   r=import_posting('https://job-boards.greenhouse.io/example/jobs/123')
  self.assertEqual((r['posted'],r['posted_precision'],r['posted_via']),('2026-10-01T22:17:28+00:00','time','greenhouse'))
 def test_page_relative_time_beats_day_only_structured_date(self):
  page=self.page({'@type':'JobPosting','title':'Engineer','hiringOrganization':{'name':'Acme'},'datePosted':'2026-10-15'})+'<main><p>Posted 3 hours ago</p></main>'
  with patch('posting.fetch_page',return_value=(page,'https://example.com/job')):r=import_posting('https://example.com/job')
  self.assertEqual((r['posted_precision'],r['posted_via'],r['posted_text']),('hour','page','Posted 3 hours ago'))
 def test_greenhouse_edit_time_is_not_a_posting_time(self):
  job={'title':'Engineer','location':{'name':'Remote'},'content':'x','updated_at':'2026-10-20T10:00:00-04:00'}
  with patch('posting.fetch_page',side_effect=[(json.dumps(job),'unused'),(json.dumps({'name':'Example Co'}),'unused')]):
   r=import_posting('https://job-boards.greenhouse.io/example/jobs/123')
  self.assertEqual(r['posted'],'')
 def test_oracle_recruiting_cloud_uses_job_feed(self):
  feed={'items':[{'Title':'Full Stack Engineer, Principal','ExternalPostedStartDate':'2026-10-21T21:08:55+00:00','PrimaryLocation':'Oakland, CA','ShortDescriptionStr':'Build things.','OrganizationDescriptionStr':'About Stellarus and the Ascendiun Family of Companies'}]}
  with patch('posting.fetch_page',return_value=(json.dumps(feed),'unused')) as fetch:
   r=import_posting('https://ecge.fa.us2.oraclecloud.com/hcmUI/CandidateExperience/en/sites/CX_1003/job/20262199?utm_source=linkedin')
  self.assertIn('finder=ById;Id=%2220262199%22,siteNumber=CX_1003',fetch.call_args[0][0])
  self.assertEqual((r['company'],r['role'],r['posted'],r['posted_precision']),('Stellarus','Full Stack Engineer, Principal','2026-10-21T21:08:55+00:00','time'))
  self.assertIn('Location: Oakland, CA',r['notes'])
 def test_bookmark_capture_from_indeed(self):
  from posting import import_captured
  r=import_captured({'url':'https://www.indeed.com/viewjob?jk=59a65da58eafa1b2','title':'Senior .NET Developer - Remote | Indeed.com','company':'Acme \\u0026 Co','role':'Senior .NET Developer','pub':'1792700000000','ld':[]})
  self.assertEqual((r['company'],r['role'],r['posted_precision'],r['posted_via']),('Acme & Co','Senior .NET Developer','time','indeed'))
  self.assertEqual(r['posted'],'2026-10-22T20:13:20+00:00')
 def test_bookmark_capture_prefers_structured_data_and_relative_age(self):
  from posting import import_captured
  ld=json.dumps({'@type':'JobPosting','title':'Backend Engineer','hiringOrganization':{'name':'Globex'},'datePosted':'2026-10-20'})
  r=import_captured({'url':'https://www.indeed.com/viewjob?jk=1','ld':[ld],'age':'3 hours ago','role':'ignored'})
  self.assertEqual((r['company'],r['role'],r['posted_precision'],r['posted_text']),('Globex','Backend Engineer','hour','3 hours ago'))
  r=import_captured({'url':'https://www.indeed.com/viewjob?jk=2','company':'Initech','role':'Dev','age':'30+ days ago'})
  self.assertEqual(r['posted_precision'],'day');self.assertEqual(import_captured({'url':'https://x.example/job','role':'Dev','company':'Initech','age':'Today'})['posted_precision'],'day')
  with self.assertRaises(PostingError):import_captured({'url':'javascript:alert(1)'})
 def test_peoplesoft_candidate_gateway_fields(self):
  page="<title>Careers</title><span class='ps_box-value' id='HRS_SCH_WRK2_POSTING_TITLE' >Lead Platform Developer</span><span class='ps_box-value' id='HRS_SCH_WRK_HRS_DESCRLONG' >Davis</span><span id='HRS_SCH_WRK_HRS_FULL_PART_TIME'>Full Time</span><h2><span class='ps-text' id='HRS_SCH_WRK_DESCR100$0lbl'>Job Summary</span></h2><span class='ps_box-value' id=HRS_SCH_PSTDSC_DESCRLONG$0 ><p><span>Build <strong>Appian</strong> apps.</span></p><ul><li>Salary: $97,500</li></ul></span><p>Footer</p>"
  url='https://careerspub.universityofcalifornia.edu/psc/ucdavis/EMPLOYEE/HRMS/c/X.GBL?JobOpeningId=1'
  with patch('posting.fetch_page',return_value=(page,url+'&')):r=import_posting(url)
  self.assertEqual((r['company'],r['role'],r['url'],r['source'],r['warning']),('UC Davis','Lead Platform Developer',url,'peoplesoft',''))
  for value in ['Location: Davis','Employment: Full Time','Job Summary','Build Appian apps.','Salary: $97,500']:self.assertIn(value,r['notes'])
  self.assertNotIn('Footer',r['notes'])
 def test_redirect_keeps_session_cookies(self):
  class Msg:
   def __init__(self,cookies):self.cookies=cookies
   def get_all(self,name):return self.cookies
  class Response:
   def __init__(self,status,location='',cookies=()):self.status=status;self.location=location;self.msg=Msg(list(cookies))
   def getheader(self,name,default=''):return {'Location':self.location,'Content-Type':'text/html'}.get(name,default)
   def read(self,n):return b'<h1>Job</h1>'
  responses=[Response(302,'/job?x=1',['SID=abc; domain=.example.com; path=/; secure; HttpOnly','evil=1; domain=other.com']),Response(200)]
  with patch('posting.socket.getaddrinfo',return_value=[(2,1,6,'',('8.8.8.8',80))]),patch('posting.socket.create_connection'),patch('posting.http.client.HTTPConnection') as conn:
   conn.return_value.getresponse.side_effect=responses
   fetch_page('http://jobs.example.com/job')
   first,second=[c.kwargs['headers'] for c in conn.return_value.request.call_args_list]
  self.assertNotIn('Cookie',first);self.assertEqual(second['Cookie'],'SID=abc')
if __name__=='__main__':unittest.main()
