# Getting the live link

Two steps. Neither needs a terminal.

**End state:** a public URL Aerchain can open and drive themselves, plus the
GitHub repo. Both are links you paste into an email.

---

## Step 1 · Push to GitHub (5 min)

Your repo already exists and is empty, waiting:
**github.com/vaidant137-collab/killspreadsheet**

1. **desktop.github.com** → Download for macOS → open it → drag **GitHub
   Desktop** into Applications → open it.
2. It offers **"Sign in to GitHub.com"**. Click it. Your browser opens, you're
   already logged in, click **Authorize**. No token, no password typed.
3. **File** menu → **Add Local Repository…** → Documents → **killspreadsheet**
   → **Add Repository**.
   It recognises it immediately — 20 saved versions, and it already knows where
   it belongs on GitHub.
4. A button appears at the top: **Push origin**. Click it.

Refresh the GitHub page. Your code is there.

> **That link is deliverable #1.** At submission: repo page → **Settings** →
> **Collaborators** → **Add people** → whoever Aerchain names.

---

## Step 2 · Deploy it (15 min, mostly waiting)

1. Go to **render.com** → **Get Started** → **GitHub** → authorise.
2. Top right: **New +** → **Blueprint**.
3. Pick **killspreadsheet** from the list. If it isn't there, click
   **"Configure account"** and give Render access to that repo.
4. Render reads `render.yaml` and fills everything in itself — build command,
   start command, Python version. **Don't change any of it.**
5. It asks for one value: **OPENROUTER_API_KEY**. Paste your key.
   (Leave it blank if you'd rather — the site still works, you just lose the
   live chat.)
6. **Apply** / **Create**.

Watch the log. It installs, builds the dataset, renders the five vendor
documents, runs the pipeline, and starts serving. **First build takes about
5–8 minutes.** When it says *Live*, click the URL at the top.

> **That URL is deliverable #2.**

### Two things to know about the free tier

**It sleeps after 15 minutes idle.** The next visitor waits ~50 seconds for it
to wake. Fine for a link someone opens on their own time — *not* fine if you're
on a call watching them wait. So: **open the link yourself 2 minutes before any
call** to wake it up.

**The chat is capped at 60 questions an hour.** A public URL with your paid key
behind it needs a ceiling, or one person holding down Enter drains your $5 and
the demo is dead for whoever opens the link next. If the cap is hit, everything
except the chat still works — the comparison, evidence drawer, review queue and
assumptions panel are all served from the database, not the model.

*(That's worth a line in your write-up, by the way. "I put a budget ceiling on
a public demo and made it degrade rather than break" is a product decision, not
a technical one.)*

---

## Step 3 · The iteration loop

Once both are up, changes flow like this:

1. You tell me what to change in this chat.
2. I edit the files on your Mac directly and commit them.
3. You click **Push origin** in GitHub Desktop.
4. Render rebuilds automatically (~3 min) and the live URL updates.
5. You refresh and check.

You never touch a terminal. Tell me what's wrong and click one button.

---

## Optional · Running it on your Mac

`START-HERE.command` should work now — the last blocker was a line that built a
type union at runtime, where Python 3.9 can't handle `|`. It uses
`typing.Union` instead and runs on everything from 3.9 up.

Worth doing once as a fallback in case Render has a bad night. **Not worth
debugging tonight** if it misbehaves — the live URL is the deliverable.

---

## If Render fails to build

Copy the red lines from the log into this chat. The build is pinned to Python
3.11, so none of the 3.9 problems can recur there — anything that goes wrong
will be a missing system library, and those are quick.
