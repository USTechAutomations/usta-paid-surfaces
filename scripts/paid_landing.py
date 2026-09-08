"""Stable purchase instructions and anchors for the five reviewed destinations."""
import re
scopes={
'permit-files/austin':'One assembled Austin permit CSV, $349 once. This is a dated file, not a permit application or a current contact list. A person emails the CSV within one working day.',
'boston':'Choose one Boston work-type slice for $349 once. After payment, reply to your receipt naming Short form building, Electrical, Plumbing, Gas, or Electrical low voltage. A person emails that slice within one working day.',
'nyc-ll84':'Choose one year (2022, 2023 or 2024) or one borough for $349 once. After payment, reply to your receipt naming the slice. A person emails that CSV within one working day. This is data, not a compliance filing service.',
'wp-accessibility-scan':'$49 a month for weekly automated checks of one site. Enter your website address at checkout. The first report arrives within 7 days. Automated checks find some accessibility issues, not all. Cancel any month by email.',
'pilot-logbook-digitizer':'$175 once for up to 60 pages. After payment, reply to your receipt with your own scans. Import files and page checksums come back within one business day. Check all entries against the original logbook before importing.'}
def enhance_paid_landing(rel,s):
 if rel not in scopes:return s
 if not re.search(r'<a\b[^>]*data-checkout[^>]*>',s):return s
 note=scopes[rel]
 s=s.replace(' There is no pay button on this page yet.','').replace('No pay button on this page yet. ','')
 if 'ad-buyer-guide' not in s:
  i=s.index('</h1>')+len('</h1>');s=s[:i]+'\n    <p class="ad-buyer-guide">'+note+' <a href="#sample">See the sample before you buy</a>.</p>'+s[i:]
 rules={'sample':['See the file before you pay','Public sample'], 'deliverable':['What you get','What this page is'], 'coverage':['What is in the file','What is in this file','What this cannot tell you','What this page cannot tell you','What the weekly scan checks','Sample rows from'], 'buy':['Start the thread','Ask before you buy','Buy the file','Subscribe to this feed']}
 for anchor,needles in rules.items():
  if re.search(r'id=["\']'+anchor+r'["\']',s):continue
  target=None
  for needle in needles:
   target=next((m for m in re.finditer(r'<h2\b[^>]*>.*?</h2>',s,re.S) if needle in re.sub('<[^>]+>','',m.group())),None)
   if target:break
  if not target:raise RuntimeError((rel,anchor))
  old=target.group();new=old.replace('<h2','<h2 id="'+anchor+'"',1);s=s[:target.start()]+new+s[target.end():]
 return s
