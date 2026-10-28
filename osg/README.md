# Running on OSPool (ap40.uw.osg-htc.org)

This folder uses **HTCondor on OSPool** via the UW access point
`ap40.uw.osg-htc.org`, logging in as `samah.alshrief`. Two steps, run in
order:

1. **`pull_data.sh`**  -  downloads every IPEDS panel to parquet. Run this
   **directly on the access point** (via `./launch.sh pull`), *not* as a
   condor job. It makes live HTTPS calls to `educationdata.urban.org`, and
   OSPool execute nodes are opportunistic, heterogeneous machines that
   generally do **not** provide general outbound internet access  -  only a
   Squid proxy scoped to software repos (CVMFS, PyPI), not arbitrary
   third-party REST APIs. A job that needs the open internet belongs on the
   access point (a normal login node with normal internet access), not on
   the compute fabric. See the note at the top of `pull_data.submit` for
   more, and the OSPool Acceptable Use Policy:
   <https://osg-htc.org/docs/submit/ap-ospool-aup/>.
2. **`run_regression.submit`**  -  an actual HTCondor job. It's pure
   computation over already-downloaded parquet (no network needed), which is
   exactly the workload OSPool's compute fabric is for. Runs the
   regressions with 1,000 bootstrap replicates; queues one job per RQ.

## One-time setup (do this once, on your Mac)

```bash
# 1. Confirm you can log in
ssh samah.alshrief@ap40.uw.osg-htc.org

# 2. On the access point, create a working directory
mkdir -p ~/ipeds-analysis && exit
```

## Every run

The easiest path is `launch.sh`, which handles rsync + ssh + preflight for
you:

```bash
# --- from repo root ---
cd ipeds-institutional-analysis

./launch.sh pull       # runs the data pull ON the access point (30-60 min,
                        # streams live output to your terminal)
./launch.sh regress    # submits run_regression.submit (all 3 RQs) to condor
./launch.sh status     # condor_q / condor_history
./launch.sh pull-back  # rsync data/ + results/ back to your laptop
```

If you'd rather drive it by hand:

```bash
# 1. Ship the code up (excluding data + venv)
rsync -avz --delete \
  --exclude '.venv' --exclude '__pycache__' \
  --exclude 'data/*.parquet' --exclude 'results/*' \
  ./ samah.alshrief@ap40.uw.osg-htc.org:~/ipeds-analysis/

# 2. Log in and run the pull DIRECTLY (not condor_submit)
ssh samah.alshrief@ap40.uw.osg-htc.org
cd ~/ipeds-analysis/osg
chmod +x *.sh
bash pull_data.sh          # streams to your terminal; 30-60 min

# 3. Once it's done, submit the regressions as an actual condor job
mkdir -p logs
condor_submit run_regression.submit
condor_watch_q

# 4. Log out
exit
```

Then, back on your Mac, pull results:

```bash
rsync -avz \
  samah.alshrief@ap40.uw.osg-htc.org:~/ipeds-analysis/osg/results/ \
  ./results/
rsync -avz \
  samah.alshrief@ap40.uw.osg-htc.org:~/ipeds-analysis/osg/data/ \
  ./data/
```

## Debugging a failed job

The pull's output is just your ssh session's stdout/stderr (it isn't a
condor job, so there's no `pull.*.log/.out/.err` triple for it  -  if it
fails you'll see the Python traceback directly in your terminal).
`run_regression.submit` jobs write to `osg/logs/` on the access point:

```bash
ssh samah.alshrief@ap40.uw.osg-htc.org
cd ~/ipeds-analysis/osg
condor_q                       # jobs still running/idle
condor_history samah.alshrief  # jobs that already exited

ls logs/                        # inspect .log .out .err triples
tail -50 logs/regress.*.err
```

Common failure modes:

| Symptom | Fix |
| --- | --- |
| Job idle for hours in `condor_q` | No matching machines yet  -  OSPool schedules opportunistically. Wait, or lower resource asks in `run_regression.submit`. |
| `ModuleNotFoundError` in `.err` | `requirements-osg.txt` didn't install  -  check `pip install` output early in the `.out` file. |
| `FileNotFoundError: No parquet files matched` | `run_regression.submit` ran before `pull_data.sh` finished, or the pull produced no output  -  check the pull's terminal output (it isn't logged to a file) or rerun `./launch.sh pull`. |
| Repeated held jobs | `condor_q -held` shows the reason; often it's a resource ask over the site limit. |
| `ProxyError` / `Connection refused` if you ever try to condor_submit the pull anyway | Expected  -  see the top of `pull_data.submit`. Run it on the access point instead. |

## Job categories and why

`run_regression.submit` uses `+JobDurationCategory = "Medium"` (<10h).
OSPool prefers short/medium jobs because they're easier to schedule
opportunistically. Keep it under 10 hours  -  with 1,000 bootstrap replicates
on a 45,000-row panel that's very comfortable. (The old `pull_data.submit`
job category no longer applies since that step isn't a condor job anymore.)

## OSG docs to bookmark

- OSPool tutorial quickstart: <https://portal.osg-htc.org/documentation/htc_workloads/submitting_workloads/tutorial-quickstart/>
- Python on OSPool: <https://portal.osg-htc.org/documentation/software_examples/python/manage-python-packages/>
- Scaling with the `queue` command: <https://portal.osg-htc.org/documentation/software_examples/python/tutorial-ScalingUp-Python/>
- OSPool Acceptable Use Policy: <https://osg-htc.org/docs/submit/ap-ospool-aup/>
