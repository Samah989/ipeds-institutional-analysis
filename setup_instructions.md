# First-run instructions  -  do this once, in your terminal

I built every file. These are the commands **you** need to run  -  I can't type
into your Terminal from here (macOS blocks agents from typing into terminal
apps for safety), so you drive this two-minute step.

Open Terminal and paste each block.

## 1. Verify the project is where I put it

```bash
cd ipeds-institutional-analysis
ls
```

You should see: `README.md notebooks src osg data results requirements.txt .gitignore setup_instructions.md`

## 2. Create a Python environment and install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

This takes 2-5 minutes.

## 3. Create the **private** GitHub repo and push

Option A  -  with the GitHub CLI (`gh`), the easiest path:

```bash
# One-time: install gh if you don't have it
brew install gh
gh auth login   # follow the prompts, pick HTTPS, log in via browser

# From the project folder:
git init
git add .
git commit -m "Initial commit: IPEDS panel analysis (3 RQs) with OSG pipeline"
gh repo create Samah989/ipeds-institutional-analysis \
    --private \
    --source=. \
    --remote=origin \
    --push
```

That creates the repo as **private** under your account and pushes the code
in one step. Nothing is public.

Option B  -  without `gh` (create the empty repo in your browser first at
<https://github.com/new>, set visibility to **Private**, then):

```bash
git init
git add .
git commit -m "Initial commit: IPEDS panel analysis (3 RQs) with OSG pipeline"
git branch -M main
git remote add origin https://github.com/Samah989/ipeds-institutional-analysis.git
git push -u origin main
```

## 4. Launch JupyterLab and run the tutorial notebook

```bash
jupyter lab
```

Open `notebooks/00_ipeds_api_tutorial.ipynb` and run cells top-to-bottom.
It's designed so every cell finishes in a few seconds (small, filtered pulls).

## 5. Run the three research-question notebooks

Open each in order. They pull real IPEDS data and cache it to `data/`:

- `notebooks/01_rq1_affordability.ipynb`
- `notebooks/02_rq2_completion.ipynb`
- `notebooks/03_rq3_equity.ipynb`

If `01` runs cleanly against the small-slice defaults, you're ready to move
to OSG for the full-panel runs.

## 6. Push to OSPool for the heavy runs

See [`osg/README.md`](osg/README.md) for the SSH + `condor_submit` sequence.

---

## What I did NOT do (and why)

- **Did not push to GitHub.** I can't authenticate to your GitHub from this
  sandbox  -  that needs your `gh` login on your Mac. Step 3 above takes 60 seconds.
- **Did not SSH to OSPool.** Same reason: your SSH key lives on your Mac.
  The `osg/README.md` gives you the exact commands.
- **Did not run the notebooks.** The sandbox has no internet to the Urban
  Institute API, so I can't validate the exact JSON column names live. If a
  cell errors on a column name, it's likely the API renamed it since the docs
  I checked  -  tell me the error and I'll patch the notebook.
