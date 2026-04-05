#!/usr/bin/env python3
"""Edit the two lists, run: python3 two_sample_ttest.py"""

from scipy.stats import ttest_ind

a = [30.6, 23.8, 23.3]
b = [30.7, 74.4, 68.8]

stat, p = ttest_ind(a, b)  # Welch: ttest_ind(a, b, equal_var=False)
print(f"t = {stat:.6g}, p = {p:.6g}")
