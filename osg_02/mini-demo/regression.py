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
