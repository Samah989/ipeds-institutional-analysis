# 50-Minute OSG Workshop  -  Presenter Guide

## Workshop Flow

| Time | What | How |
|------|------|-----|
| 0-5 min | **The mental model** | Whiteboard/slide: laptop vs access point vs worker |
| 5-15 min | **Mini demo  -  live** | Type 4 tiny files, submit, get results |
| 15-20 min | **Debrief mini demo** | "Your script didn't change. You added 2 files." |
| 20-30 min | **Real research job** | Walk through IPEDS files, pull data, submit |
| 30-40 min | **Hands-on exercise** | Audience fills in blank .sh and .submit templates |
| 40-45 min | **Results + power pitch** | Show regression output, "now imagine 1000 jobs" |
| 45-50 min | **Q&A + resources** | Links, where to get an account, office hours |

---

## Part 1: The Mental Model (5 min)

**Draw this on the whiteboard:**

```
YOUR LAPTOP          ACCESS POINT (ap40)        WORKER NODE
─────────────        ──────────────────         ───────────
- your script        - your script              - empty container
- your data          - your data                - gets your files
- packages work      - has internet             - NO internet
- just run python    - condor_submit            - installs packages
                                                - runs your code
                                                - ships results back
```

**Key phrase:** "The worker is a stranger's computer. It has never seen your code. It starts empty every time."

---

## Part 2: Mini Demo  -  Type Live (10 min)

Follow `mini-demo/PRESENTER-SCRIPT.md` exactly. Four files:

1. `students.csv`  -  10 rows of hours/score data
2. `regression.py`  -  13 lines, scipy linregress
3. `run.sh`  -  7 lines, installs packages + runs script
4. `run.submit`  -  18 lines, the recipe card

Submit, wait ~2 min, show `result.csv`.

**Punchline:** "Same result as your laptop. But it ran on someone else's computer 1000 miles away. Now imagine you need to run this 500 times with different datasets."

---

## Part 3: Real Research Job (10 min)

**The question:** "Does institution size predict 6-year graduation rate?"

**Walk through the files** (don't type these  -  they're already on the access point):

```
osg_02/
├── mini-demo/                    # what we just did
├── src/
│   ├── __init__.py               # makes src a Python package
│   ├── data_pull.py              # downloads IPEDS data from API
│   ├── panels.py                 # builds the analysis dataset
│   └── regression.py             # OLS with publication-quality output
├── run_analysis.py               # the main script
├── run.sh                        # wrapper (same pattern as mini demo!)
├── run.submit                    # submit file (same pattern!)
├── requirements.txt              # pinned dependencies for the worker
├── pull_data.sh                  # data download (access point only)
├── preflight.sh                  # sanity check before submitting
├── data/                         # parquet files (created by pull_data.sh)
├── logs/                         # HTCondor logs
└── results/                      # output (created by jobs)
```

**Key point:** "Same pattern as the mini demo  -  a wrapper that installs packages and runs your script, and a submit file that ships your files. The only difference is your script is bigger."

### Pull data (~2 min)

```bash
cd ~/osg_02
bash pull_data.sh
```

This downloads 3 years (2020-2022) of directory and grad-rates data. About 2 minutes.

### Preflight + Submit

```bash
bash preflight.sh
condor_submit run.submit
condor_q
```

### While waiting  -  explain the monitoring commands

This is a great teaching moment. The job is running, so show them how to watch it:

**Say:** "Your job is out there running on someone else's computer. How do you know what's happening? HTCondor gives you four ways to check."

```bash
# 1. condor_q  -  "Are my jobs still running?"
condor_q
```
**Explain:** "This is your dashboard. It shows how many jobs are idle (waiting for a machine), running, or done. Think of it like checking the status of an Uber  -  is it matched, on the way, or arrived?"

```bash
# 2. condor_watch_q  -  "Let me watch in real time"
condor_watch_q
```
**Explain:** "Same information, but it auto-refreshes like a live scoreboard. You'll see the progress bar fill up as jobs finish. Press any key to exit."

**What the columns mean:**
- `IDLE` = waiting for a machine (like being in a queue at the DMV)
- `RUN` = actively running on a worker
- `DONE` = finished, results are being transferred back
- `INPUT` = files are being shipped to the worker

```bash
# 3. condor_tail -f  -  "Show me the live output"
condor_tail -f <job_id>
```
**Explain:** "This is like `tail -f` on a log file, but the file is on a computer hundreds of miles away. You'll see your Python script's print statements in real time. Only works if your submit file has `stream_output = True`."

```bash
# 4. condor_q -held  -  "Why is my job stuck?"
condor_q -held
```
**Explain:** "If a job gets 'held', something went wrong  -  not enough memory, a file is missing, the container image doesn't exist. This tells you why. It's your error message."

**Quick reference to draw on the board:**

```
condor_q           →  "What's the status?"
condor_watch_q     →  "Let me watch live"
condor_tail -f ID  →  "Show me the output"
condor_q -held     →  "What went wrong?"
```

**Say:** "These four commands are 90% of what you need. Bookmark them."

### After jobs finish  -  show results

When `condor_q` shows no jobs, they're done:

```bash
ls -lh results/
cat results/regression.csv
cat logs/job.*.out
```

**Walk through the output:** "The regression table shows the coefficient, standard error, t-statistic, and p-value  -  same format you'd get from Stata or R. The bootstrap confidence intervals are at the bottom."

---

## Part 4: Hands-on Exercise (10 min)

Hand out `templates/my_wrapper.sh` and `templates/my_job.submit`. 

"Fill in the blanks. You've seen the pattern twice now  -  the mini demo and the real job. Same structure every time."

Give them 5 minutes, then reveal the answer key.

---

## Part 5: The Power Pitch (5 min)

"You just ran a regression on a single worker. Here's what makes OSG powerful:"

1. **Scale:** Change `queue 1` to `queue 50`  -  run 50 different regressions simultaneously
2. **Speed:** 50 regressions that take 30 seconds each = 25 minutes sequentially. On OSG, all 50 finish in ~1 minute (they run in parallel on different machines)
3. **Reproducibility:** Your submit file + requirements.txt is a complete record of how the analysis ran
4. **Free:** OSPool is available to any US researcher at no cost

**Show them the one-line change:**

```
# Instead of:
queue 1

# Do this  -  run the analysis on 50 random subsamples:
queue 50
```

"One line. 50 parallel jobs. That's the power of grid computing."

---

## Part 6: Q&A + Resources (5 min)

- Get an account: https://portal.osg-htc.org/
- Documentation: https://portal.osg-htc.org/documentation/
- Office hours: https://osg-htc.org/office-hours
- This repo: (your GitHub link)

---

## Backup: If Things Go Wrong

| Problem | Quick fix |
|---------|-----------|
| `pull_data.sh` fails | Data is pre-cached in the repo; skip to preflight |
| Job stuck idle | "OSPool is busy  -  let me show you cached results" |
| `ModuleNotFoundError` | `ls src/`  -  check files are there |
| No condor_submit | "Are we on the access point? `ssh ap40...`" |

**Always have cached results ready** in case live jobs don't finish in time:
```bash
# Before the workshop, run everything once and save:
cp -r results/ results-backup/
cp logs/job.*.out logs-backup.out
```
