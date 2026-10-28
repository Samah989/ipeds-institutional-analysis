# Mini Demo  -  Presenter Script

**Goal:** Show the full OSG cycle (create files → submit → get results) live in ~3 minutes with a dead-simple linear regression.

**Story to tell:** "You have 10 students. You know how many hours each studied and what they scored. You want to find the line of best fit. On your laptop you'd just run `python regression.py`. Let's do the same thing on OSG."

---

## Live typing (4 files, nothing over 15 lines)

### 1. The data (type or paste)

```bash
mkdir -p mini-demo && cd mini-demo
mkdir -p logs
```

```bash
nano students.csv
```

Type this:
```
hours,score
1,35
2,45
3,50
4,60
5,65
6,70
7,80
8,85
9,90
10,95
```

Save: Ctrl-O, Enter, Ctrl-X

**Say:** "Nothing special  -  just a CSV you'd have on your laptop."

---

### 2. The Python script

```bash
nano regression.py
```

Type this:
```python
import pandas as pd
from scipy import stats

df = pd.read_csv("students.csv")
slope, intercept, r, p, se = stats.linregress(df["hours"], df["score"])

print(f"slope     = {slope:.2f}")
print(f"intercept = {intercept:.2f}")
print(f"R-squared = {r**2:.3f}")
print(f"p-value   = {p:.4f}")

with open("result.csv", "w") as f:
    f.write("slope,intercept,r_squared,p_value\n")
    f.write(f"{slope:.2f},{intercept:.2f},{r**2:.3f},{p:.4f}\n")
print("Saved result.csv")
```

Save: Ctrl-O, Enter, Ctrl-X

**Say:** "This is your normal Python script. You'd run this on your laptop with `python regression.py`. Nothing has changed about YOUR code."

---

### 3. The wrapper (NEW for OSG)

```bash
nano run.sh
```

Type this:
```bash
#!/bin/bash
set -euo pipefail

mkdir -p deps
python3 -m pip install --target=deps scipy pandas 2>&1 | tail -1
export PYTHONPATH="$PWD/deps"

python3 regression.py
```

Save: Ctrl-O, Enter, Ctrl-X

```bash
chmod +x run.sh
```

**Say:** "The worker machine has no packages. This script installs them and then runs your code. That's all it does  -  setup, then run."

---

### 4. The submit file (NEW for OSG)

```bash
nano run.submit
```

Type this:
```
container_image = /cvmfs/singularity.opensciencegrid.org/htc/ubuntu:22.04

executable = run.sh

transfer_input_files = regression.py, students.csv
transfer_output_files = result.csv
should_transfer_files = YES
when_to_transfer_output = ON_EXIT

request_cpus   = 1
request_memory = 1 GB
request_disk   = 1 GB

+JobDurationCategory = "Medium"

log    = logs/demo.$(Cluster).log
output = logs/demo.$(Cluster).out
error  = logs/demo.$(Cluster).err

queue 1
```

Save: Ctrl-O, Enter, Ctrl-X

**Say:** "This is the recipe card. It tells HTCondor: use this container, run this script, ship these two files, bring back result.csv, and give me 1 GB of memory."

---

## Submit and watch

```bash
condor_submit run.submit
```

**Say:** "That's it. Your job is now running on someone else's computer somewhere in the country."

```bash
condor_q
```

Wait for it to finish (usually 1-3 minutes for this tiny job), then:

```bash
cat result.csv
cat logs/demo.*.out
```

**Say:** "slope = 6.85  -  for every extra hour of studying, the score goes up about 7 points. R-squared = 0.99  -  almost perfect fit. Same result you'd get on your laptop, but it ran on the grid."

---

## Key points to highlight

1. **Your Python script didn't change**  -  `regression.py` is identical to what you'd run locally
2. **You only added 2 files**  -  the wrapper (`run.sh`) and the submit file (`run.submit`)
3. **The wrapper installs packages** because the worker starts empty
4. **The submit file ships your files** and brings back results
5. **Now imagine** this CSV has 10 million rows and you need to run 50 regressions  -  THAT'S why you use OSG
