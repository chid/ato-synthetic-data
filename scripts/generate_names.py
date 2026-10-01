"""Generate seeded fictional names with Faker's Australian English provider."""
import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

NAME_COLUMNS = ["first_name", "last_name", "full_name"]


def generate_names(n: int, seed=42, sexes=None) -> pd.DataFrame:
    if n < 0:
        raise ValueError("number of names must be nonnegative")
    sexes = [None] * n if sexes is None else list(sexes)
    if len(sexes) != n:
        raise ValueError("sexes must have one value per name")

    if isinstance(seed, np.random.SeedSequence):
        seed = int(seed.generate_state(1)[0])
    fake = Faker("en_AU")
    fake.seed_instance(int(seed))
    first_names = {"Male": fake.first_name_male, "Female": fake.first_name_female}
    rows = []
    for sex in sexes:
        first = first_names.get(sex, fake.first_name)()
        last = fake.last_name()
        rows.append((first, last, f"{first} {last}"))
    return pd.DataFrame(rows, columns=NAME_COLUMNS)


def add_names(population: pd.DataFrame, seed=42) -> pd.DataFrame:
    out = population.copy()
    if "agent_id" in out:
        people = out[["agent_id", "sex"]].drop_duplicates("agent_id")
        lookup = generate_names(len(people), seed, people["sex"])
        lookup.index = people["agent_id"].to_numpy()
        for column in NAME_COLUMNS:
            out[column] = out["agent_id"].map(lookup[column])
    else:
        names = generate_names(len(out), seed, out["sex"] if "sex" in out else None)
        out[NAME_COLUMNS] = names.to_numpy()
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--n", type=int, default=10, help="number of fictional names")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--sex", choices=["Male", "Female"], help="optional given-name category")
    parser.add_argument("--out", type=Path, help="CSV output path; defaults to stdout")
    args = parser.parse_args()
    if args.n < 0:
        parser.error("--n must be nonnegative")
    names = generate_names(args.n, args.seed, [args.sex] * args.n)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
    names.to_csv(args.out or sys.stdout, index=False)


if __name__ == "__main__":
    main()
