# The embed scripts

This folder holds the small pieces of JavaScript that other people's websites
load. The service hands them out at:

```
GET https://usta-loops-260481739341.us-central1.run.app/embed/<name>.js
```

## Who puts what here

**`casepack.js` is written by the casepack worker, not by the service worker.**
When it lands in this folder it is served straight away. Nothing in the service
needs changing, and there is no list of allowed names to update.

## The rules the service applies

- Only files whose name ends in `.js` are served. Anything else answers `404`.
- The name may hold small letters, numbers, dots, dashes and underscores only,
  and must start with a letter or a number.
- Nothing outside this folder is ever served. Names containing `..` are refused,
  and a shortcut pointing outside the folder is refused as well.
- Files are cached by browsers for one hour, so a change takes up to an hour to
  reach a page that has already loaded it.
- Any website may load these files. That is the point of an embed.

## What a script here is expected to do

The paste-in lines the service hands a wholesaler look like this:

```html
<script src="https://usta-loops-260481739341.us-central1.run.app/embed/casepack.js" data-cfg="CFG_ID"></script>
```

The script draws the sheet where that tag sits, and reads the service address from
its own `src`. The older two-line form still works too (a `<div data-casepack="CFG_ID"
data-service="..." data-badge="1">` plus the script loaded `async`); `casepack.js`
handles both.

So a script here should:

1. Find its own `<script>` tag (or any `<div>` tags that carry its own `data-` attribute).
2. Read the sheet id and the service address off that tag.
3. Fetch `GET <service>/cp/config/<id>` and draw the sheet.
4. Count the load by adding an image pointing at
   `<service>/t?f=casepack&e=embed_load`.
5. Show the small "made with" badge when `data-badge="1"` is present, and leave
   it out when it is not. A paid sheet has no badge.

## The line that has to stay

Any page built from data somebody pasted carries this sentence:

> Data you paste stays in this link. Delete it any time.

## What never goes in here

No names, no email addresses, no phone numbers, no network addresses. A script
here reads a sheet id and draws rows. It never asks a visitor who they are.
