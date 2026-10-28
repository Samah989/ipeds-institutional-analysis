# Answer Key (Presenter Only)

## my_wrapper.sh

1. `mkdir -p results deps`
2. `--target=deps -r requirements.txt`
3. `PYTHONPATH="$PWD/deps"`
4. `python3 run_analysis.py --out results/`

## my_job.submit

1. `htc/ubuntu:22.04`
2. `run.sh`
3. `run_analysis.py, requirements.txt, src, data`
4. `transfer_output_files = results`
5. `request_cpus = 1`, `request_memory = 2 GB`, `request_disk = 2 GB`
6. `+JobDurationCategory = "Medium"`
7. `logs` (for all three log paths)
