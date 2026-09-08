# Mission — Patent Practitioner Directory

Every night the USPTO's Office of Enrollment and Discipline publishes the
full roster of everyone licensed to practice patent law before it: about
53,700 attorneys and agents. This family turns that list into one page per
US city with at least 25 registered practitioners, showing which firms are
there and how many practitioners each has, largest cities first.

**What ships.** Up to 200 city pages, largest cities first by practitioner
count. Each page names the organizations with practitioners registered at
that city and how many each has, plus a split of attorneys vs. agents. It
never prints a person's own name, street address, or phone number: rows with
no listed organization, and any organization name that reads as a person's
own name rather than a business (`looks_personal()`, the same check the rest
of this site's estate uses), are folded into one line: "Individual
practitioners: N (names withheld)." Every page carries the standing
disclosure, a freshness stamp, and a `data-source-url` back to the USPTO
roster on every factual sentence.

**What sells.** One Featured slot per city, $350 for 12 months: a firm's name
and website placed at the top of that city's page. A second buyer for an
already-held city is told plainly and pointed at the standing refund text —
this never happens silently.

**What it is not.** Not affiliated with, or endorsed by, the USPTO. Not
legal, tax, or professional advice. A listing is not an endorsement.

**Known limits, disclosed on every page:** `looks_personal()` has false
positives on real company names (it also catches "Boston Scientific");
firm-name matching is punctuation cleanup only, not real entity resolution;
USPTO registration is not a state bar license.
