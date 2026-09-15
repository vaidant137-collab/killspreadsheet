# Step by step — no terminal knowledge needed

Everything is already on your Mac at:

**Documents → killspreadsheet**

---

# Part 1 · Run the demo (5 minutes)

### Step 1 — Open the folder

Open **Finder** → click **Documents** in the left sidebar → open the
**killspreadsheet** folder.

### Step 2 — Double-click `START-HERE.command`

A black window (Terminal) opens by itself and starts working. You don't type
commands — it does everything.

> **If macOS says "cannot be opened because it is from an unidentified
> developer":** right-click the file instead → **Open** → **Open** again in the
> dialog. You only do this once.

### Step 3 — It asks for an API key

It will pause and show:

```
  Key:
```

Paste your OpenRouter key (get one at **openrouter.ai/keys** — it starts with
`sk-or-`) and press **Enter**.

**Or just press Enter to skip it.** The demo works either way — without a key
you lose only the live chat with the analyst. The comparison table, the evidence
drawer, the review queue and the scorecard all work regardless.

The key is saved to a file that git ignores, so it never leaves your Mac.

### Step 4 — Wait

It installs what it needs, builds the dataset, renders the five vendor
documents, runs extraction, and prints your scorecard. First run takes a couple
of minutes; after that it's seconds.

### Step 5 — Your browser opens automatically

`http://127.0.0.1:8000` opens on its own. That's the demo.

**Leave the black window open while you demo.** Closing it stops the server.
When you're completely finished, close the window.

---

### To run it again later

Double-click `START-HERE.command` again. That's it.

---

# Part 2 · Put it on GitHub (5 minutes, no terminal)

Your repo already exists and is empty, waiting:
**github.com/vaidant137-collab/killspreadsheet**

Rather than use the terminal, use the app — it's all buttons.

### Step 1 — Get GitHub Desktop

Go to **desktop.github.com** → Download for macOS → open the downloaded file →
drag **GitHub Desktop** into Applications → open it.

### Step 2 — Sign in

It offers **"Sign in to GitHub.com"**. Click it; your browser opens, you're
already logged in, click **Authorize**. No token, no password typing.

### Step 3 — Add the folder

In GitHub Desktop: **File** menu → **Add Local Repository…** → navigate to
**Documents → killspreadsheet** → **Add Repository**.

It will recognise it immediately — the project already has its full history
(13 saved versions) and knows where it belongs on GitHub.

### Step 4 — Publish

A button appears at the top: **Push origin** (or **Publish repository**).
Click it.

If it asks about visibility, **keep "Keep this code private" ticked.**

Done. Refresh github.com/vaidant137-collab/killspreadsheet and your code is
there.

### Step 5 — Add their reviewers, at submission time

On the repo page: **Settings** → **Collaborators** → **Add people** → enter the
GitHub usernames or emails Aerchain gives you.

---

# Part 3 · What to actually do tonight

In priority order. If you run out of time, stop partway down — the top items
matter most.

1. **Double-click `START-HERE.command`** and check the demo opens.
2. **Rehearse the eight questions** in `RUNBOOK.md` once, out loud.
3. **Record the walkthrough.** One take, eight minutes, mistakes left in.
   On a Mac: **Cmd+Shift+5** → "Record Entire Screen" → Record. Stop from the
   menu bar icon. It saves to your Desktop.
4. **Send** `ONE-PAGER.md`, the recording, and the repo link.
5. GitHub Desktop (Part 2) — only if there's time. You can also just attach the
   folder as a zip.

---

# If something goes wrong

| What you see | What to do |
|---|---|
| "unidentified developer" | Right-click the file → Open → Open |
| A window offers to install Developer Tools | Click Install, wait, then double-click `START-HERE.command` again |
| It says the port is in use | An old copy is still running. Close any other black Terminal windows and try again. |
| Real extraction fails | It falls back automatically and keeps going. Nothing to do. |
| Browser shows "can't connect" | The black window must stay open. If you closed it, double-click the file again. |
| Anything else | Tell me exactly what it says on screen. I can run things on your Mac from here and look. |

---

# One thing worth knowing

You do **not** need to learn git or the terminal tonight. I can run things on
your Mac directly from this chat — I already built the dataset, rendered all
five vendor documents and ran the full pipeline there while writing this.

The only reason `START-HERE.command` exists is that the web server has to run on
your Mac for your browser to see it. Everything else, just ask me.
