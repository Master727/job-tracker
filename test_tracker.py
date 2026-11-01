import sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import server

class TrackerTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.db=patch.object(server,'DB',Path(self.temp.name)/'data/tracker.db');self.db.start();self.root=patch.object(server,'ROOT',Path(self.temp.name));self.root.start()
  folder=Path(self.temp.name)/'Jobs';folder.mkdir()
  for name in ['Me-Resume-Backend.pdf','Me-Resume-Full-Stack.docx','Me-Cover-Letter-Backend.pdf','notes.txt']:(folder/name).write_text('x')
  self.resumes=patch.object(server,'RESUME_DIR',folder);self.resumes.start();server.init()
 def tearDown(self):self.root.stop();self.db.stop();self.resumes.stop();self.temp.cleanup()
 def add(self,**kw):
  d={'company':'Acme','role':'Software Engineer','applied_at':'2026-10-20T18:00:00.000Z','posted_at':'2026-10-20T15:00:00.000Z','source':'LinkedIn','resume':'Software Engineer'};d.update(kw);return server.save_application(d)
 def app(self,app_id):return next(a for a in server.state()['applications'] if a['id']==app_id)
 def test_quick_add_stores_speed_inputs(self):
  a=self.app(self.add())
  self.assertEqual((a['status'],a['applied'],a['source'],a['furthest']),('Applied','2026-10-20','LinkedIn','Applied'))
  self.assertEqual((a['applied_at'],a['posted_at']),('2026-10-20T18:00:00+00:00','2026-10-20T15:00:00+00:00'))
 def test_unknown_posting_time_is_allowed(self):
  self.assertEqual(self.app(self.add(posted_at=''))['posted_at'],'')
 def test_rejects_bad_input(self):
  for bad in [{'company':''},{'status':'Ghosted'},{'source':'Monster'},{'url':'javascript:alert(1)'},{'applied_at':'2026-10-20T18:00:00'}]:
   with self.assertRaises(ValueError):self.add(**bad)
 def test_status_change_keeps_furthest_stage(self):
  i=self.add();server.set_status(i,'Interview');server.set_status(i,'Rejected')
  a=self.app(i);self.assertEqual((a['status'],a['furthest']),('Rejected','Interview'))
  with self.assertRaises(ValueError):server.set_status(i,'Responded')
 def test_editing_does_not_lose_furthest_stage(self):
  i=self.add();server.set_status(i,'Screen');self.add(id=i,status='Applied',notes='Recruiter: Sam')
  a=self.app(i);self.assertEqual((a['status'],a['furthest'],a['notes']),('Applied','Screen','Recruiter: Sam'))
 def test_resume_grade_uses_headless_headhunter_scale(self):
  self.assertEqual([server.grade(n,1) for n in (8,10,11,25,50,75,76)],['A+','A+','B','B','C-','D','F'])
  self.assertEqual(server.grade(9,0),'');self.assertEqual(server.grade(30,0),'C-')
 def test_grades_group_by_resume(self):
  for _ in range(4):self.add()
  i=self.add();server.set_status(i,'Interview');self.add(resume='Full Stack Engineer')
  r={x['resume']:x for x in server.state()['resumes']}
  self.assertEqual((r['Software Engineer']['applications'],r['Software Engineer']['interviews'],r['Software Engineer']['grade']),(5,1,'A+'))
  self.assertEqual(r['Full Stack Engineer']['grade'],'')
 def test_existing_database_is_upgraded(self):
  with sqlite3.connect(server.DB) as c:
   c.execute('DROP TABLE applications')
   c.execute("CREATE TABLE applications(id INTEGER PRIMARY KEY,company TEXT NOT NULL,role TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'Applied',applied TEXT NOT NULL,url TEXT DEFAULT '',notes TEXT DEFAULT '',thread_id TEXT DEFAULT '',updated TEXT NOT NULL)")
   c.execute("INSERT INTO applications(company,role,status,applied,updated) VALUES('Old Co','Engineer','Responded','2026-10-08','x')")
  server.init();a=server.state()['applications'][0]
  self.assertEqual((a['status'],a['furthest'],a['posted_at'],a['resume']),('Screen','Screen','',''))
 def test_resume_folder_lists_resumes_only(self):
  self.assertEqual(server.resume_files(),['Me-Resume-Backend.pdf','Me-Resume-Full-Stack.docx'])
 def test_every_resume_gets_a_card_before_use(self):
  self.add(resume='Me-Resume-Backend.pdf');st=server.state()
  self.assertEqual([r['resume'] for r in st['resumes']][:2],['Me-Resume-Backend.pdf','Me-Resume-Full-Stack.docx'])
  self.assertEqual(st['resumes'][1]['applications'],0)
if __name__=='__main__':unittest.main()
