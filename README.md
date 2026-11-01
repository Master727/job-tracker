# Simple Job Tracker

A standalone local tracker for Pavlo, built around the Headless Headhunter's application strategy (https://www.headlessheadhunter.org): apply as soon as a job is posted, use one resume per job title, and judge each resume by how many interviews it gets per application. Python standard library + HTML/CSS/JavaScript + SQLite. No AI, no accounts, nothing leaves this Mac except posting lookups you ask for.

## Start and stop

Double-click **Start Job Tracker.command**, then visit http://localhost:3005. Double-click **Stop Job Tracker.command** to stop it. Terminal: `python3 manage.py start` or `python3 manage.py stop`.

## Add an application

Right after you hit submit on an application, paste the posting URL into the box at the top and press Enter. The tracker fills in the company, role, when the job was posted and the job board, and shows them as a ticket. Pick the resume you sent (the one you used last is preselected), then press Enter or Save ticket.

Resumes are the files in `/Users/pavlopyshnyy/Pavlo/Jobs` with "resume" in the name (PDF, Word or Pages). Add a new one there and it shows up next time you open the page. To use another folder, start the tracker with `JOB_TRACKER_RESUMES=/path/to/folder`.

You only type something when the posting leaves it out: a box appears for a missing company or role, and time chips appear if the page doesn't say when it was posted. "Fix details" lets you correct anything the posting got wrong. You'll get a warning if you already have a ticket for the same company and role.

### Indeed and other sites that block the tracker

Indeed (and Glassdoor and ZipRecruiter) put job pages behind a bot check that only a person's own browser passes, so pasting their links can't work. Pasting one shows an **Add to Job Tracker** button instead. Drag it to your bookmarks bar once. Then, on any posting, click the bookmark: it reads the page you're looking at in your browser (title, company, posting time) and opens the ticket here. Nothing is sent anywhere except this tracker on your Mac. It works on any site, including ones that need you to sign in.

## Update a status

Click the status on any ticket and pick the new one: Applied, Screen, Interview, Offer, Rejected or Withdrawn. Click the company name to edit everything else, including exact posted and applied times, notes and the link, or to delete the ticket.

## What the numbers mean

- **The big number** is your median time from posting to applying, across tickets where you logged when the job was posted. Each ticket's stub shows its own time. Tickets sent within 24 hours stay bright yellow.
- **Interviews per application, by resume** grades each resume on Lee's scale: 1 in 10 or better is an A+, 1 in 25 a B, 1 in 50 a C-, 1 in 75 a D, worse is an F. A recruiter screen counts as an interview. An application keeps counting after a later rejection, because the tracker remembers the furthest stage it reached. Grades appear after 10 applications or the first interview.

Export CSV downloads every application with its times, board and resume.

## Storage

`data/tracker.db` stores applications (permissions 600). `data/tracker.before-redesign.db` is the backup taken before the redesign. The HTTP server binds only to 127.0.0.1. Back up the data directory with the server stopped.

Gmail syncing has been removed. `data/connection.json` still holds the old read-only Gmail token but nothing uses it; delete it and revoke "Simple Job Tracker" at https://myaccount.google.com/permissions if you no longer want it.

## When was it posted?

The tracker reads the posting time straight from the job site's own data and preselects it in the draft, showing where it came from:

- Greenhouse: the time the job was first published (not when it was last edited)
- Ashby: the publish time; Lever: the time the posting was created
- LinkedIn: the "14 hours ago" shown on the public job page (LinkedIn shows the repost time for reposted jobs)
- Workday: the posting day
- Oracle Recruiting Cloud (`…oraclecloud.com/hcmUI/CandidateExperience/…`): the exact time it went live on the careers site
- Indeed (through the bookmark): the publish time Indeed stores with the job, or its "3 days ago"
- Any other site: its structured JobPosting date, or a "Posted 3 hours ago" line on the page

A site that only lists the day gets a day-only chip, counted from midnight; pick an hour chip instead if the listing shows hours. If a page says nothing about when it was posted, the draft tells you so and you pick the closest time.

## Fill from a posting URL

The importer reads standard JobPosting JSON-LD, supports Greenhouse's public Job Board API, and falls back to page metadata. Location, salary, employment type, posted date and description go into notes. Some sites need a login or block automated reads; enter those by hand. Importing never submits anything to the employer.

## Development

Run `python3 -m unittest -v`. Tests use temporary databases.

Fonts (Barlow and Barlow Condensed, SIL Open Font License) are bundled in `web/fonts`, so the app works offline.
