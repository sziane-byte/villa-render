# Villa Compliance — Complete Setup (full accuracy version)

## First, the Docker question — answered

**You do NOT install Docker. You do NOT run Docker.** 

The `Dockerfile` is just a recipe (a plain text file). When you run the Azure deploy command, **Azure reads that recipe and builds everything in the cloud, on Azure's servers.** Your laptop only sends the 3 small files up. That's why the Dockerfile has to exist — it tells Azure how to assemble your PDF-to-image service — but you never touch Docker yourself.

Why this service is needed at all: n8n online cannot turn PDF pages into sharp images, and sharp images are what make the reading accurate. So that one job runs on Azure, and n8n calls it through a URL — exactly like the Azure task you already did in n8n before.

```
3 files  ──upload──>  Azure builds the service in the cloud  ──>  gives you a URL
                                                                      │
                                                  n8n calls this URL when a PDF arrives
```

---

# PART A — Put the service on Azure

You have the folder `service/` with 3 files inside: `main.py`, `Dockerfile`, `requirements.txt`.

### Step 1 — Install the Azure CLI (the `az` command)
- **Windows:** download and run https://aka.ms/installazurecliwindows  
- **Mac:** in terminal: `brew install azure-cli`  
- **Linux:** `curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash`

Close and reopen your terminal, then check:
```bash
az version
```
You should see version numbers. ✅

### Step 2 — Sign in
```bash
az login
```
A browser opens → sign in with your Azure free-trial account → come back to the terminal.

### Step 3 — One-time setup (extension + permissions)
Copy-paste these one at a time:
```bash
az upgrade
az extension add --name containerapp --upgrade
az provider register --namespace Microsoft.App
az provider register --namespace Microsoft.OperationalInsights
```

### Step 4 — Go into the service folder
In your terminal, navigate INTO the `service` folder (the one with the 3 files):
```bash
cd path/to/service
```
Confirm the files are there:
```bash
ls
# should show: Dockerfile  main.py  requirements.txt
```

### Step 5 — Deploy (the one big command)
Copy-paste this whole block:
```bash
az containerapp up \
  --name villa-render \
  --resource-group villa-rg \
  --location uaenorth \
  --environment villa-env \
  --ingress external \
  --target-port 8000 \
  --source .
```
> On **Windows PowerShell**, replace each `\` at the end of a line with a backtick `` ` ``.

This runs for **3–6 minutes**. Azure builds your service in the cloud. When done, it prints a URL near the bottom like:
```
https://villa-render.victoriousmoss-1a2b3c4d.uaenorth.azurecontainerapps.io
```
**Copy that whole URL.** This is your `YOUR_URL`. You need it in Part B.

### Step 6 — Make it sleep when idle (saves your credit)
```bash
az containerapp update --name villa-render --resource-group villa-rg --min-replicas 0 --max-replicas 2
```

### Step 7 — Test it
Open this in your browser (paste your URL, add `/health`):
```
YOUR_URL/health
```
You should see: `{"ok":true}` ✅

---

# PART B — Import the workflow into n8n

You have the file `villa_compliance_v11.json`.

### Step 1 — Import
In n8n → top-right **⋯ menu → Import from File → choose `villa_compliance_v11.json`**.

### Step 2 — Paste YOUR_URL into 5 nodes
The workflow has the placeholder `https://YOUR-CONTAINER-APP.azurecontainerapps.io` in **5 nodes**. Open each, find the **URL** field, and replace ONLY the placeholder part — keep the `/render_thumbs` or `/render_pages?...` ending.

The 5 nodes are:
1. **Render Thumbnails**
2. **Render Site Pages**
3. **Render Floor Pages**
4. **Render Vert Pages**
5. **Render Sched Pages**

Example — in *Render Thumbnails* the URL field currently reads:
```
https://YOUR-CONTAINER-APP.azurecontainerapps.io/render_thumbs
```
change it to:
```
https://villa-render.victoriousmoss-1a2b3c4d.uaenorth.azurecontainerapps.io/render_thumbs
```
(using YOUR actual URL). Do the same in the other 4 — they end in `/render_pages?indices=...`; leave the `?indices=...` part exactly as is, only swap the domain.

### Step 3 — Check the credentials show as valid
- Telegram nodes → credential **plans_pdf** (your existing one)
- Gemini nodes → credential **Vertex AI Service Account** (your existing one)

If any says "not found", click it and pick the right one from the dropdown.

### Step 4 — Activate
Flip the workflow to **Active** (switch, top-right).

### Step 5 — Run it
In Telegram, open your bot → **send the villa PDF as a file** (not as a photo).

You get:
1. `📥 تم استلام المخطط...` right away (it started)
2. ~1 minute later: 5 Arabic report messages.

---

# How you know it worked (your test PDF)
- Stair width **1.40 m** → ✅
- Riser **170 mm**, Tread **300 mm** → ✅
- Total height **14.70 m** → ✅ (≤18)

Unreadable items show as **🔍 مراجعة** — that's correct, it never invents numbers.

---

# Stopping everything before the trial ends (your plan)
One command deletes the whole service so nothing can ever charge you:
```bash
az group delete --name villa-rg --yes --no-wait
```
To bring it back later, just redo Part A steps 5–7. (Your n8n workflow stays as-is; you'd only re-paste the new URL if it changed.)

---

# Quick troubleshooting
| Problem | Fix |
|--------|-----|
| `az: command not found` | Azure CLI not installed or terminal not reopened. Redo Part A Step 1. |
| Deploy error "missing parameters" | Run `az extension add --name containerapp --upgrade` again (Part A Step 3). |
| Error 413 on deploy | Source folder too big (>200MB). Make sure `service/` has ONLY the 3 files. |
| `/health` doesn't load | First call after sleep is slow — wait 20s and retry. If still nothing, the deploy URL is wrong. |
| Render node errors in n8n | URL typo, or you removed the `/render_pages` ending. Recheck Part B Step 2. |
| Values look off | In each Render…Pages node change `"dpi": 250` to `300` (sharper, a bit slower). |
