# ChaCha PA widget for Android (KWGT + Tasker)

Shows the running task (or the last result), the team size, time and usage on your home screen.
Tap it to open the run. The iPhone version is `widgets/scriptable.js`.

> Not yet tested on a real phone. If a step doesn't match your app versions, note what you saw and
> we'll fix this guide.

## Why two apps
The server needs your `APP_TOKEN` (and, when hosted behind Cloudflare Access, a service token) in
request headers. KWGT's own web fetch can't send headers. So Tasker does the request, and KWGT only
draws what Tasker gives it. No token ever goes in a URL.

**Simpler option:** if you only want to know when a run needs you, skip the widget. Install the app
to your home screen (open it in Chrome > menu > Add to Home screen) and turn on ntfy pushes
(`NTFY_URL` and `NTFY_TOPIC` in `.env`, plus the ntfy app subscribed to the same topic).

## You need
- **KWGT** (free; the Pro key removes the editor limits) and **Tasker** (paid), from the Play Store.
- A URL the phone can reach: your Cloudflare Tunnel URL when hosted, or the laptop's LAN address if
  you start the server with `--host 0.0.0.0` and `APP_TOKEN` set.

## 1. Tasker: fetch the status every 10 minutes
1. **Tasks > + > name it `ChaCha status`.**
2. Add action **Net > HTTP Request**:
   - Method: `GET`
   - URL: `https://YOUR-URL/api/status`
   - Headers (one per line):
     ```
     Authorization:Bearer YOUR_APP_TOKEN
     CF-Access-Client-Id:YOUR_ID
     CF-Access-Client-Secret:YOUR_SECRET
     ```
     Leave out the two `CF-` lines if you're not behind Cloudflare Access.
   - Timeout: 10 seconds. Tick **Continue Task After Error**.
3. Add action **Code > JavaScriptlet** and paste:
   ```js
   var base = "https://YOUR-URL";
   var label = "ChaCha PA", title = "Can't reach ChaCha PA", detail = "", url = base;
   function clock(s) { s = Math.round(s || 0); var m = Math.floor(s / 60), x = s % 60;
     return (m < 10 ? "0" : "") + m + ":" + (x < 10 ? "0" : "") + x; }
   try {
     var st = JSON.parse(http_data);
     var run = (st.running || []).filter(function (r) { return r.needs_approval; })[0] || (st.running || [])[0];
     if (run) {
       label = run.needs_approval ? "Needs your approval" : "Running";
       title = run.title;
       detail = run.agents + (run.agents == 1 ? " agent · " : " agents · ") + clock(run.elapsed_s) + " · $" + Number(run.cost_usd).toFixed(2) + " est.";
       url = base + "/runs/" + run.id;
     } else if (st.last) {
       var names = { finished: "Finished", gave_up: "Out of budget", failed: "Crashed", stopped: "Stopped", interrupted: "Interrupted" };
       label = names[st.last.status] || st.last.status; title = st.last.title; url = base + "/runs/" + st.last.id;
     } else { title = "No runs yet"; }
   } catch (e) { detail = (typeof http_response_code !== "undefined" && http_response_code == 401) ? "Sign-in failed: check the token" : ""; }
   setLocal("cc_label", label); setLocal("cc_title", title); setLocal("cc_detail", detail); setLocal("cc_url", url);
   ```
4. Add action **Plugin > KWGT > Kustom Variable** four times, sending `%cc_label`, `%cc_title`,
   `%cc_detail` and `%cc_url` to KWGT variables named `cclabel`, `cctitle`, `ccdetail` and `ccurl`.
5. **Profiles > + > Time:** every 10 minutes (from 00:00 to 23:59), task `ChaCha status`.
   Run the task once by hand to check it.

## 2. KWGT: draw it
1. Long-press the home screen > Widgets > KWGT > pick a 4×1 or 4×2 size. Tap it to open the editor.
2. Background: color `#0A0A0A` (dark) or `#FFFFFF` (light), corner radius about 16.
3. Add three **Text** items, top to bottom:
   - `$br(tasker, cclabel)$` at 12 sp, color `#A3A3A3`
   - `$br(tasker, cctitle)$` at 16 sp, bold, color `#F5F5F5`, max 2 lines
   - `$br(tasker, ccdetail)$` at 11 sp, monospace, color `#A3A3A3`
4. **Touch:** on the whole widget, action **Open link**, link `$br(tasker, ccurl)$`.
5. Save. The widget updates each time the Tasker profile runs.

## Check it works
Start a run in the app, run the Tasker task by hand, and the widget should show "Running" with the
task title. Approve-needed runs show "Needs your approval" first.
