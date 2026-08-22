# Point feeds.ustechautomations.com at this site

Do not run this from an agent session. DNS changes live traffic for a new host. The github.io copy stays up either way.

DNS today: Google Cloud DNS (`ns-cloud-b*.googledomains.com`). Existing `permits.` and `agents.` are A records to a VM. This host should be a **CNAME to GitHub Pages**, not that VM.

## 1. Create the name

Google Cloud Console (`admin@ustechautomations.com`) → Cloud DNS → zone for `ustechautomations.com` → Add record set:

- DNS name: `feeds`
- Type: `CNAME`
- Data: `ustechautomations.github.io.`
- TTL: `300`

→ Create.

That is reversible: delete the `feeds` CNAME.

## 2. Tell GitHub Pages the name

GitHub → `USTechAutomations/usta-paid-surfaces` → Settings → Pages → Custom domain:

```
feeds.ustechautomations.com
```

→ Save. Wait for the certificate. Then add a `CNAME` file in this repo containing exactly:

```
feeds.ustechautomations.com
```

and change every `rel=canonical` and `sitemap.xml` loc from github.io to `https://feeds.ustechautomations.com/`.

## 3. Optional later: a family gets its own host

When one feed deserves `grid.ustechautomations.com`, copy `families/grid/` into its own repo (same GitHub Pages pattern) and add a second CNAME `grid` → `ustechautomations.github.io.`. Do not put a second custom domain on this repo — GitHub Pages allows one.

## Do not

- Point `feeds` at the permits VM (`136.117.179.118`)
- Point `feeds` at the main load balancer unless you also add host rules (that is a different, larger change)
- Touch `app.` or `api.`
- Edit `~/code/USTA`
