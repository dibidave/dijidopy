#!/usr/bin/env python3
"""
Caffeine intake summaries using logical days: each logical day is 04:00–04:00 local time
(times in [00:00, 04:00) on calendar day D belong to logical day D − 1).

Evening caffeine window for logical day D: local wall time from 18:00 on calendar date D
through 03:59 on calendar date D + 1 (so midnight–4am after “your evening” still counts for D).

Requires DIJIBLE_* env vars (see dijible.py). Optional: INTAKE_TZ (default America/Los_Angeles).

Loads ``.env`` from the parent of this repo (``../.env`` when the repo is ``dijidopy/``).

Examples::

  python3 caffeine_latest_april.py --start 2026-04-01 --end 2026-04-30
  python3 caffeine_latest_april.py --april-year 2026
  python3 caffeine_latest_april.py --summary-through 2026-04 --summary-months 6 --binomial-april
  python3 caffeine_latest_april.py --compare-experiment-windows
"""

from __future__ import annotations

import argparse
import calendar
import datetime as dt
import math
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import dotenv
import pandas as pd
import requests

_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
dotenv.load_dotenv(_ENV_FILE)

import dijible

try:
    from scipy.stats import binomtest
except ImportError:
    binomtest = None
try:
    from scipy.stats import fisher_exact
except ImportError:
    fisher_exact = None


def parse_iso_date(s: str) -> dt.date:
    return dt.datetime.strptime(s.strip(), "%Y-%m-%d").date()


def parse_year_month(s: str) -> Tuple[int, int]:
    parts = s.strip().split("-")
    if len(parts) != 2:
        raise ValueError(f"expected YYYY-MM, got {s!r}")
    y, m = int(parts[0]), int(parts[1])
    if not 1 <= m <= 12:
        raise ValueError(f"invalid month in {s!r}")
    return y, m


def _intake_item_label(row: dict) -> str:
    for key in (
        "name",
        "food_name",
        "item_name",
        "recipe_name",
        "description",
        "title",
        "label",
    ):
        v = row.get(key)
        if v is not None and str(v).strip():
            return str(v).strip()
    return ""


def fetch_caffeine_intakes(session: requests.Session) -> pd.DataFrame:
    nutrient_id = dijible.get_nutrient_id(session, "caffeine")
    if nutrient_id is None:
        raise RuntimeError("nutrient 'caffeine' not found")

    rows_out = []
    page = 1
    while True:
        result = dijible.fetch_intakes(session, str(nutrient_id), page=page)
        data = result["data"]
        pagination = result["pagination"]

        for r in data:
            consumed_at = r.get("consumed_at") or r.get("logged_at")
            if not consumed_at:
                continue
            nv = r.get("nutrient_values", {})
            raw = nv.get(nutrient_id) if nv.get(nutrient_id) is not None else nv.get(str(nutrient_id))
            caffeine = float(raw) if raw is not None else None
            rows_out.append(
                {
                    "consumed_at": consumed_at,
                    "caffeine_mg": caffeine,
                    "item": _intake_item_label(r),
                }
            )

        if not pagination.get("hasMore"):
            break
        page += 1

    df = pd.DataFrame(rows_out)
    if df.empty:
        return df
    df["consumed_at"] = pd.to_datetime(df["consumed_at"], utc=True)
    return df.sort_values("consumed_at").reset_index(drop=True)


def add_logical_day_columns(df: pd.DataFrame, tz: str) -> pd.DataFrame:
    """Add logical_date and consumed_at_local (tz-aware)."""
    if df.empty:
        return df
    loc = df["consumed_at"].dt.tz_convert(tz)
    return df.assign(
        logical_date=(loc - pd.Timedelta(hours=4)).dt.date,
        consumed_at_local=loc,
    )


def caffeine_intakes_in_logical_date_range(
    df: pd.DataFrame,
    start: dt.date,
    end: dt.date,
    tz: str,
) -> pd.DataFrame:
    """Rows with caffeine mg > 0 and logical_date in [start, end] inclusive."""
    if df.empty:
        return pd.DataFrame()
    work = add_logical_day_columns(df, tz)
    with_caffeine = work[(work["caffeine_mg"].notna()) & (work["caffeine_mg"] > 0)]
    return with_caffeine[
        (with_caffeine["logical_date"] >= start) & (with_caffeine["logical_date"] <= end)
    ].copy()


def evening_caffeine_window_mask(
    consumed_at_local: pd.Series,
    logical_date: pd.Series,
) -> pd.Series:
    """
    True iff local time is in the evening window for that logical day:
    same calendar date as logical_date and hour >= 18, OR next calendar date and hour < 4.
    """
    local_cal = consumed_at_local.dt.date
    hour = consumed_at_local.dt.hour
    logical_next_cal = (pd.to_datetime(logical_date) + pd.Timedelta(days=1)).dt.date
    same_day_evening = (local_cal == logical_date) & (hour >= 18)
    next_morning = (local_cal == logical_next_cal) & (hour < 4)
    return same_day_evening | next_morning


def logical_dates_in_range(start: dt.date, end: dt.date) -> pd.DataFrame:
    """All logical dates from start through end inclusive (one row per date)."""
    return pd.DataFrame({"logical_date": pd.date_range(start, end, freq="D").date})


def count_days_with_evening_caffeine(in_range: pd.DataFrame) -> int:
    if in_range.empty:
        return 0
    mask = evening_caffeine_window_mask(in_range["consumed_at_local"], in_range["logical_date"])
    return int(in_range.loc[mask, "logical_date"].nunique())


def latest_caffeine_per_logical_day(
    df: pd.DataFrame,
    start: dt.date,
    end: dt.date,
    tz: str,
    in_range: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    all_days = logical_dates_in_range(start, end)

    if df.empty:
        return all_days.assign(
            latest_consumed_at_local=pd.NaT,
            caffeine_mg=float("nan"),
            item="",
        )

    if in_range is None:
        in_range = caffeine_intakes_in_logical_date_range(df, start, end, tz)

    if in_range.empty:
        return all_days.assign(
            latest_consumed_at_local=pd.NaT,
            caffeine_mg=float("nan"),
            item="",
        )

    latest_idx = in_range.groupby("logical_date")["consumed_at"].idxmax()
    latest = in_range.loc[latest_idx].reset_index(drop=True)

    out = latest[
        [
            "logical_date",
            "consumed_at_local",
            "caffeine_mg",
            "item",
        ]
    ].rename(columns={"consumed_at_local": "latest_consumed_at_local"})

    merged = all_days.merge(out, on="logical_date", how="left")
    return merged.sort_values("logical_date").reset_index(drop=True)


def month_start_end(year: int, month: int) -> Tuple[dt.date, dt.date]:
    start = dt.date(year, month, 1)
    _, last = calendar.monthrange(year, month)
    end = dt.date(year, month, last)
    return start, end


def iter_months_ending_at(end_year: int, end_month: int, n: int) -> List[Tuple[int, int]]:
    """n consecutive calendar months ending at (end_year, end_month), inclusive, newest first."""
    out = []
    y, m = end_year, end_month
    for _ in range(n):
        out.append((y, m))
        if m == 1:
            y -= 1
            m = 12
        else:
            m -= 1
    return out


def iter_calendar_months_inclusive(
    start_year: int,
    start_month: int,
    end_year: int,
    end_month: int,
) -> List[Tuple[int, int]]:
    """Every calendar month from (start_year, start_month) through (end_year, end_month), in order."""
    out: List[Tuple[int, int]] = []
    y, m = start_year, start_month
    while (y < end_year) or (y == end_year and m <= end_month):
        out.append((y, m))
        if m == 12:
            y += 1
            m = 1
        else:
            m += 1
    return out


def pooled_evening_over_calendar_months(
    df: pd.DataFrame,
    tz: str,
    months: List[Tuple[int, int]],
) -> Dict[str, object]:
    """Sum evening-caffeine days and total logical days across listed calendar months."""
    per_month: List[Dict[str, object]] = []
    x = 0
    n = 0
    for y, mo in months:
        s = month_evening_summary(df, y, mo, tz)
        per_month.append(s)
        x += int(s["days_with_evening_caffeine"])
        n += int(s["days_in_month"])
    return {
        "evening_days": x,
        "total_days": n,
        "rate": x / n if n else float("nan"),
        "per_month": per_month,
    }


def two_proportion_fisher_or_z(
    x1: int,
    n1: int,
    x2: int,
    n2: int,
) -> Dict[str, object]:
    """2×2 Fisher exact (two-sided) if scipy available; else normal two-sided z-test for p1 − p2."""
    out: Dict[str, object] = {
        "x1": x1,
        "n1": n1,
        "x2": x2,
        "n2": n2,
        "p1": x1 / n1 if n1 else float("nan"),
        "p2": x2 / n2 if n2 else float("nan"),
    }
    if n1 == 0 or n2 == 0:
        out["p_value"] = float("nan")
        out["method"] = "n/a (empty stratum)"
        return out

    if fisher_exact is not None:
        _, p = fisher_exact([[x1, n1 - x1], [x2, n2 - x2]])
        out["p_value"] = float(p)
        out["method"] = "scipy.stats.fisher_exact (two-sided)"
        return out

    p1, p2 = x1 / n1, x2 / n2
    p_pool = (x1 + x2) / (n1 + n2)
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    z = (p1 - p2) / se if se > 0 else 0.0
    out["p_value"] = float(2 * (1 - 0.5 * (1 + math.erf(abs(z) / math.sqrt(2)))))
    out["method"] = "two-sided z-test for difference in proportions (install scipy for Fisher)"
    return out


def compare_12mo_before_dec2025_vs_jan_apr_2026(
    df: pd.DataFrame,
    tz: str,
) -> Dict[str, object]:
    """
    Baseline: Dec 2024 through Nov 2025 (12 months before Dec 2025; Dec 2025 excluded as mixed).
    Comparison: Jan–Apr 2026 pooled.
    """
    baseline_months = iter_calendar_months_inclusive(2024, 12, 2025, 11)
    follow_months = [(2026, 1), (2026, 2), (2026, 3), (2026, 4)]
    baseline = pooled_evening_over_calendar_months(df, tz, baseline_months)
    follow = pooled_evening_over_calendar_months(df, tz, follow_months)
    test = two_proportion_fisher_or_z(
        int(baseline["evening_days"]),
        int(baseline["total_days"]),
        int(follow["evening_days"]),
        int(follow["total_days"]),
    )
    return {
        "label_baseline": "Dec 2024 – Nov 2025 (12 mo; excludes Dec 2025)",
        "label_follow": "Jan – Apr 2026",
        "baseline": baseline,
        "follow": follow,
        "test": test,
    }


def month_evening_summary(
    df: pd.DataFrame,
    year: int,
    month: int,
    tz: str,
) -> Dict[str, object]:
    start, end = month_start_end(year, month)
    in_range = caffeine_intakes_in_logical_date_range(df, start, end, tz)
    n_days = (end - start).days + 1
    n_evening = count_days_with_evening_caffeine(in_range)
    return {
        "year": year,
        "month": month,
        "start": start,
        "end": end,
        "days_in_month": n_days,
        "days_with_evening_caffeine": n_evening,
        "rate": n_evening / n_days if n_days else float("nan"),
    }


def summarize_months_backward(
    df: pd.DataFrame,
    end_year: int,
    end_month: int,
    n_months: int,
    tz: str,
) -> List[Dict[str, object]]:
    months = iter_months_ending_at(end_year, end_month, n_months)
    return [month_evening_summary(df, y, m, tz) for y, m in reversed(months)]


def binomial_april_vs_prior_three(
    summaries: List[Dict[str, object]],
    april_year: int,
    april_month: int = 4,
) -> Optional[Dict[str, object]]:
    """
    One-sided binomial test: H0: April evening-day probability equals pooled rate from
    the three calendar months immediately before April (Mar, Feb, Jan of the same year
    when April is month 4).
    """
    by_ym = {(s["year"], s["month"]): s for s in summaries}
    key_april = (april_year, april_month)
    if key_april not in by_ym:
        return None

    m_prev = april_month - 1
    y_prev = april_year
    if m_prev < 1:
        m_prev = 12
        y_prev -= 1
    keys_prior = []
    y, m = y_prev, m_prev
    for _ in range(3):
        keys_prior.append((y, m))
        if m == 1:
            y -= 1
            m = 12
        else:
            m -= 1

    sm = by_ym[key_april]
    x_a = int(sm["days_with_evening_caffeine"])
    n_a = int(sm["days_in_month"])

    x_p = 0
    n_p = 0
    for k in keys_prior:
        if k not in by_ym:
            return None
        s = by_ym[k]
        x_p += int(s["days_with_evening_caffeine"])
        n_p += int(s["days_in_month"])

    if n_p == 0 or n_a == 0:
        return None

    p0 = x_p / n_p
    result: Dict[str, object] = {
        "april": key_april,
        "april_evening_days": x_a,
        "april_days": n_a,
        "april_rate": x_a / n_a,
        "prior_months": list(reversed(keys_prior)),
        "prior_evening_days": x_p,
        "prior_days": n_p,
        "prior_rate": p0,
    }

    if binomtest is not None:
        bt = binomtest(x_a, n_a, p=p0, alternative="less")
        result["p_value"] = float(bt.pvalue)
        result["method"] = "scipy.stats.binomtest(..., alternative='less')"
    else:
        result["method"] = "normal approximation Φ(z), z=(p̂−p0)/SE (install scipy for binomtest)"
        if p0 <= 0:
            result["p_value"] = 0.0 if x_a == 0 else 1.0
        elif p0 >= 1:
            result["p_value"] = 1.0 if x_a == n_a else 0.0
        else:
            se = math.sqrt(p0 * (1 - p0) / n_a)
            z = ((x_a / n_a) - p0) / se if se > 0 else 0.0
            result["p_value"] = float(0.5 * (1.0 + math.erf(z / math.sqrt(2.0))))

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--start",
        type=parse_iso_date,
        help="Inclusive logical start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end",
        type=parse_iso_date,
        help="Inclusive logical end date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--april-year",
        type=int,
        metavar="YEAR",
        help="Shorthand: April 1–30 of this year",
    )
    parser.add_argument("--year", type=int, help=argparse.SUPPRESS)
    parser.add_argument(
        "--tz",
        default=os.environ.get("INTAKE_TZ", "America/Los_Angeles"),
        help="IANA timezone for logical day and evening window",
    )
    parser.add_argument("--csv", metavar="PATH", help="Write per-day latest-caffeine table to CSV")
    parser.add_argument(
        "--summary-through",
        type=parse_year_month,
        metavar="YYYY-MM",
        help="With --summary-months, last calendar month in the summary window",
    )
    parser.add_argument(
        "--summary-months",
        type=int,
        default=0,
        metavar="N",
        help="Print evening-caffeine day counts for N calendar months ending at --summary-through",
    )
    parser.add_argument(
        "--binomial-april",
        action="store_true",
        help="With monthly summary including April, test if April rate < pooled prior 3 months",
    )
    parser.add_argument(
        "--binomial-april-year",
        type=int,
        default=None,
        help="Calendar year of April for --binomial-april (default: year from --summary-through)",
    )
    parser.add_argument(
        "--compare-experiment-windows",
        action="store_true",
        help="Compare evening caffeine: Dec 2024–Nov 2025 (12 mo before Dec 2025, Dec 2025 omitted) vs Jan–Apr 2026",
    )
    args = parser.parse_args()
    if args.year is not None and args.april_year is None:
        args.april_year = args.year

    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    if not dijible.login(session):
        print("Login failed.", file=sys.stderr)
        return 1

    df = fetch_caffeine_intakes(session)

    start: Optional[dt.date] = None
    end: Optional[dt.date] = None
    if args.start is not None or args.end is not None:
        if args.start is None or args.end is None:
            parser.error("Use both --start and --end, or neither")
        start, end = args.start, args.end
        if end < start:
            print("--end must be on or after --start", file=sys.stderr)
            return 1
    elif args.april_year is not None:
        start = dt.date(args.april_year, 4, 1)
        end = dt.date(args.april_year, 4, 30)

    want_summary = bool(args.summary_months and args.summary_through)
    want_compare = bool(args.compare_experiment_windows)
    if start is None and end is None and not want_summary and not want_compare:
        parser.error(
            "Provide --start/--end, or --april-year, or --summary-through with --summary-months, "
            "or --compare-experiment-windows"
        )

    pd.set_option("display.max_rows", 400)
    pd.set_option("display.width", 120)
    pd.set_option("display.max_colwidth", 60)

    if start is not None and end is not None:
        in_range = caffeine_intakes_in_logical_date_range(df, start, end, args.tz)
        n_evening = count_days_with_evening_caffeine(in_range)
        result = latest_caffeine_per_logical_day(df, start, end, args.tz, in_range=in_range)

        print(
            f"Logical days {start} .. {end} ({args.tz}), "
            f"evening = 18:00–04:00 local within each logical day\n"
        )
        print(result.to_string(index=False))
        n_logical = (end - start).days + 1
        print(
            f"\nDays with ≥1 evening caffeine intake (18:00–04:00 local, tied to logical day): "
            f"{n_evening} / {n_logical}"
        )

        if args.csv:
            result.to_csv(args.csv, index=False)
            print(f"\nWrote {args.csv}")

    if args.summary_months and args.summary_through:
        ey, em = args.summary_through
        rows = summarize_months_backward(df, ey, em, args.summary_months, args.tz)
        print(f"\nEvening caffeine days by calendar month (logical days; {args.tz}):")
        print(f"Evening window: 18:00 same calendar date as logical day through 04:00 next calendar date.\n")
        for s in rows:
            print(
                f"  {s['year']}-{s['month']:02d}: {s['days_with_evening_caffeine']}/{s['days_in_month']} days "
                f"(rate {s['rate']:.4f})"
            )

        if args.binomial_april:
            april_year = args.binomial_april_year if args.binomial_april_year is not None else ey
            if em != 4:
                print(
                    f"\nNote: --binomial-april uses April ({april_year}-04); "
                    f"summary-through month is {ey}-{em:02d}.",
                    file=sys.stderr,
                )
            bt = binomial_april_vs_prior_three(rows, april_year, 4)
            if bt is None:
                print("\nCould not run binomial test (need April and three prior months in summary).", file=sys.stderr)
            else:
                print(
                    f"\nBinomial test (April {april_year} vs pooled Jan–Feb–Mar immediately before):\n"
                    f"  April: {bt['april_evening_days']}/{bt['april_days']} = {bt['april_rate']:.4f}\n"
                    f"  Prior 3 months: {bt['prior_evening_days']}/{bt['prior_days']} = {bt['prior_rate']:.4f}\n"
                    f"  H0: April probability = prior rate; H1: April probability is lower (one-sided)\n"
                    f"  p-value ≈ {bt['p_value']:.4g} ({bt['method']})"
                )

    if args.compare_experiment_windows:
        cmp = compare_12mo_before_dec2025_vs_jan_apr_2026(df, args.tz)
        b, f = cmp["baseline"], cmp["follow"]
        t = cmp["test"]
        print(f"\n{cmp['label_baseline']} vs {cmp['label_follow']} ({args.tz}, evening window as above)\n")
        print("Baseline months:")
        for s in b["per_month"]:
            print(
                f"  {s['year']}-{s['month']:02d}: {s['days_with_evening_caffeine']}/{s['days_in_month']} "
                f"(rate {s['rate']:.4f})"
            )
        print(f"  Pooled: {b['evening_days']}/{b['total_days']} = {b['rate']:.4f}\n")
        print("Jan–Apr 2026:")
        for s in f["per_month"]:
            print(
                f"  {s['year']}-{s['month']:02d}: {s['days_with_evening_caffeine']}/{s['days_in_month']} "
                f"(rate {s['rate']:.4f})"
            )
        print(f"  Pooled: {f['evening_days']}/{f['total_days']} = {f['rate']:.4f}\n")
        print(
            f"Two-sample comparison (evening-day counts vs non-evening days):\n"
            f"  H0: same underlying rate; two-sided p-value ≈ {t['p_value']:.4g} ({t['method']})"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
