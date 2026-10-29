# Auction Lot Tracker

A web page that shows how your lots in a StampAuctionNetwork (SAN) auction are doing: current bids, final prices, and how each compares with its catalog value (CV) or estimate. It updates itself during the sale. Anyone you share the link with can use it by dropping in their own lotting summary.

**How it works, in plain words**

1. A small program runs on GitHub's computers every 15 minutes during the sale. It visits the public SAN pages the way a person would, and saves what it finds as a data file.
2. The web page reads that data file. It matches the data to *your* lots.
3. Your lotting summary PDF is read **in your own browser**. It is never uploaded, so your name and address stay private.

You do not need to know how to code. You need a free GitHub account and about 20 minutes, once.

---

## One-time setup

### Step 1. Make a GitHub account
Go to github.com and choose **Sign up**. It is free.

### Step 2. Create an empty project ("repository")
1. Click the **+** at the top right, then **New repository**.
2. Name it `stamp-auction-tracker`.
3. Choose **Public**. (Free GitHub web pages need this. Everything stored is public auction data. Your PDF is never stored here.)
4. Leave every box unticked, including "Add a README".
5. Click **Create repository**.

### Step 3. Put the files in
1. Unzip the file you were given. You will see `index.html`, `sales.json`, `parser.js`, `README.md`, and folders named `scripts`, `data` and `.github`.
2. On your new empty repository page, click **uploading an existing file**.
3. Open the unzipped folder and **drag everything inside it** onto the page, including the folders.
4. Click **Commit changes**.

**Check the hidden folder arrived.** Click into the repository and look for a folder called `.github`, then `workflows`, then `update.yml`. If it is missing (some computers hide it), do this instead:
1. Click **Add file → Create new file**.
2. In the name box type exactly `.github/workflows/update.yml` (typing the slashes makes the folders).
3. Open `update.yml` from the unzipped folder in Notepad, copy everything, paste it in, and click **Commit changes**.

### Step 4. Let the job save its results
1. In your repository, click **Settings → Actions → General**.
2. Scroll to **Workflow permissions**, choose **Read and write permissions**, click **Save**.

### Step 5. Turn on the web page
1. Click **Settings → Pages**.
2. Under **Branch**, choose `main` and `/ (root)`, then **Save**.
3. After a minute or two the page shows your address: `https://YOUR-USERNAME.github.io/stamp-auction-tracker/`. Bookmark it.

### Step 6. Run the first test
1. Click the **Actions** tab. If you see a green button saying workflows are disabled, click it to enable them.
2. Click **Update sale data** on the left, then **Run workflow**, leave the box ticked, and click the green **Run workflow** button.
3. Refresh the page after a minute. A yellow dot means it is running; a green tick means success; a red cross means a problem.
4. Click the run, then **update**, then **Fetch SAN data**, and look for these lines:

| You see | It means |
|---|---|
| `HANDSHAKE_OK` | The key test passed. SAN accepted the "Realizations" request and returned the right sale. |
| `HANDSHAKE_FAILED` | SAN did not return that sale's results. **Copy the log text and send it to Claude.** |
| `catalog: 86/86 pages` (numbers vary) | The catalog was read. |
| `ERROR` or `HTTP 403` | SAN refused the request. See "If SAN says no" below. |

The test sale **RM-592** (R. Maresch, ends Oct 29) is included on purpose. It has real results right now, so you can see the whole thing working before your own sale starts. You can delete its block from `sales.json` afterwards.

### Step 7. Use the page
1. Open your page address. Pick your sale from the menu at the top.
2. Drop your lotting summary PDF on the box. You should see "Read 95 lots from the PDF" (your count will match the PDF's own total).
3. The summary tiles, chart and table fill in. The page refreshes itself every 5 minutes.

---

## Running the sale

- The job runs every 15 minutes by itself. Nothing for you to do.
- Outside a sale's dates (set in `sales.json`) the job skips that sale, so it makes no requests to SAN.
- Before the sale you see current bids. As lots close you see final prices and a result such as "Under CV".
- "Bid has moved" shows lots whose bid changed since tracking began. Until a bid moves, the number you see may be just the opening bid.

## Reading the page

- **Where is the auction?** Shows how far the sale has got. Before the sale it reads "0 of N lots closed (0%)" and every one of your lots is a hollow dot. As lots close, the closed stretch is shaded and a "Closing now" marker appears.
- **Price chart, two views.** The switch above the chart flips between **% of value** (the dashed line is 100%) and **$ vs value** (a pale bar is the catalog value, a solid bar is the final price, a hollow bar is a bid still open; one dollar scale). In the $ view the scale is capped when a few huge lots would flatten everything else; a ▲ marks the bars that run off the top. Hover a bar for its numbers (the popup leads with % in the % view and dollars in the $ view). **Click a bar to pin that lot**: its details stay in the panel under the chart and the bar gets a shaded band and a ▼; hovering other bars still shows their popups. Click the same bar again, press Unpin, or press Escape to clear it. On a phone, tap a bar to pin it. With the keyboard, Tab to the chart, use the arrow keys to move between lots, and press Enter to pin. The page remembers which view you chose.
- **Download CSV.** Saves the rows currently shown in the table, so the filter and search apply (a filtered file is named `...-filtered.csv`). It opens in Excel with the symbols intact, has a currency column, and text that starts with = + - or @ is prefixed with an apostrophe so a spreadsheet never runs it as a formula.
- **Photo of a lot.** Hover over a lot number in the table (on a phone, tap it once) to see its photo from SAN. Tap or click again to open the lot on SAN. Photos are fetched only when you ask for one. If SAN has no photo, or refuses to show it on another site, you see "no image".
- **What kinds of lots did well?** Four small charts: by condition grade, certified or not, mint / used / cover, and by value band (with the share of closed lots that went unsold). These groups are **guessed from keywords** (for example PSE, PF or Weiss mean certified; "NH" or "**" means mint). They are approximate, and with about 100 lots each group is small, so read them as hints, not trends. Each row shows n, the number of lots in the group. Rows with fewer than 3 sold lots are drawn pale and say "too few to judge".

## Refreshing by hand

The job already runs every 15 minutes. The two numbers in `sales.json` (`catalog_refresh_minutes` before the sale, `..._live` during it) say how often the full catalog is re-read; they are honoured to within one 15-minute run, so use multiples of 15 (15, 30, 45, 60). Results are read on every run. To force a refresh, scroll to the bottom of the page and click **Refresh now**. This opens the repository's *Update sale data* page on GitHub. Press **Run workflow** (and the green button inside the box), wait a minute or two, then reload the page.

This only works for the person who owns the repository (you must be signed in to GitHub with access to it). Everyone else lands on a GitHub page that will not let them run it, which does no harm. The link works out the repository from the page address (`https://NAME.github.io/REPO/`). If your page is on another address, add `"repo": "https://github.com/NAME/REPO"` at the top level of `sales.json` (next to `"sales"`).

## Updating one file later

1. In your repository click the file name (for example `index.html`).
2. Click the **pencil icon** (Edit this file), top right of the file box.
3. Press **Ctrl+A** to select everything, then paste the new version over it.
4. Click **Commit changes**, then **Commit changes** again in the box.
5. Click **Actions** → **Update sale data** → **Run workflow** → green **Run workflow** button.

## Sharing it

Send people your page address. Each person drops in their own PDF, or pastes their lot numbers, and sees only their lots. Their lists stay on their own computer.

## Tracking another sale

1. On the sale's SAN page, look at the address, for example `.../TS/TS367.cfm`. The letters are the **firm** (`TS`) and the number is the **sale** (`367`).
2. In your repository click `sales.json`, then the pencil icon. Copy one of the blocks, paste it after a comma, and change `key`, `label`, `firm`, `sale`, `sale_url` and the dates.
3. Click **Commit changes**, then run the job once by hand (Step 6).

Times are in UTC. US Eastern is 4 hours behind UTC until November 1, 2026 and 5 hours behind after.

---

## Things to know

- **Final prices on SAN do not say if buyer's premium is included.** The page has a setting for this. Ask the auction firm, or compare one lot's last bid to its final price after it closes.
- **Net proceeds are not shown.** They depend on the firm's commission and fees.
- **Catalog values can use a different condition basis** than your lot (for example "CV listed is for no gum"). Those lots are tagged "basis noted". Treat percentages as a guide.
- **Unsold lots:** SAN's "Unsold Lots" page really lists every lot that has *not sold yet*, including lots that have not closed. Before a sale it lists the whole catalog. So the page only counts a lot as unsold once the sale has moved past it (its number is below the highest lot that has sold). Two small side effects: a lot is not called unsold until the lot after it has sold, and the very last lots of a sale that pass unsold stay "open" until you check SAN.
- **Be a good guest.** The job pauses a second between requests and only runs during sales. Consider emailing support@stampauctionnetwork.com to say you are doing this. If they ask you to stop, stop. This project is not affiliated with SAN.
- **If SAN says no** (HTTP 403, or `HANDSHAKE_FAILED` every time), the fallback is manual: on the SAN sale page click **Realizations**, copy the page text, and paste it to Claude, who can read it.
- GitHub pauses scheduled jobs in a repository with no activity for 60 days. Press **Run workflow** once to wake it.

## Files

| File | What it is |
|---|---|
| `index.html` | The web page |
| `parser.js` | Reads the PDF/paste text in your browser, and guesses grade / certified / mint-used-cover from keywords |
| `sales.json` | Which auctions to track, and when |
| `scripts/fetch_sale.py` | The program that reads SAN |
| `scripts/test_parsers.py` | Self-test that runs before every fetch |
| `.github/workflows/update.yml` | The 15-minute schedule |
| `data/` | The collected data (written by the job) |
