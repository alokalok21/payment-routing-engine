"""Generate synthetic historical settlement data for training the interchange model.

The model predicts interchange rate (%) from:
    scheme_id, card_type, card_product, mcc, amount, merchant_country, card_country, cross_border

Each scheme/card_type pair has a realistic base rate (loosely modelled on published
EU-regulated + US unregulated tier structures). The base rate is then modified by:
    - card_product premium (CLASSIC < GOLD < PLATINUM < INFINITE)
    - cross-border multiplier (~2.5x)
    - MCC risk modifier (travel/hospitality slightly higher)
    - small amount-based effect
    - gaussian noise

The data is "synthetic but plausible" — sufficient for the academic showcase.
"""

import csv
import random
from pathlib import Path

import numpy as np

SCHEMES = ["VISA", "MASTERCARD", "CB", "DISCOVER", "AMEX", "UNIONPAY", "MAESTRO"]
CARD_TYPES = ["CREDIT", "DEBIT", "PREPAID"]
CARD_PRODUCTS = ["CLASSIC", "GOLD", "PLATINUM", "INFINITE"]
COUNTRIES = ["FR", "US", "DE", "CN", "GB", "ES", "IT", "JP", "BR", "IN"]
MCCS = ["5411", "5812", "4722", "5732", "5999", "5311", "7011", "5912", "8011", "4111"]

BASE_RATES = {
    ("VISA",       "CREDIT"):  0.50,
    ("VISA",       "DEBIT"):   0.20,
    ("VISA",       "PREPAID"): 0.40,
    ("MASTERCARD", "CREDIT"):  0.50,
    ("MASTERCARD", "DEBIT"):   0.20,
    ("MASTERCARD", "PREPAID"): 0.40,
    ("CB",         "CREDIT"):  0.30,
    ("CB",         "DEBIT"):   0.20,
    ("CB",         "PREPAID"): 0.30,
    ("DISCOVER",   "CREDIT"):  1.50,
    ("DISCOVER",   "DEBIT"):   0.80,
    ("AMEX",       "CREDIT"):  2.50,
    ("UNIONPAY",   "CREDIT"):  0.45,
    ("UNIONPAY",   "DEBIT"):   0.18,
    ("MAESTRO",    "DEBIT"):   0.20,
}

PRODUCT_MULTIPLIER = {
    "CLASSIC":  1.00,
    "GOLD":     1.50,
    "PLATINUM": 2.20,
    "INFINITE": 3.00,
}

MCC_MULTIPLIER = {
    "5411": 0.85,  # grocery — regulated low
    "5812": 1.00,  # restaurants
    "4722": 1.15,  # travel agencies — risk premium
    "5732": 1.00,  # electronics
    "5999": 1.00,  # misc retail
    "5311": 0.95,  # department stores
    "7011": 1.10,  # hotels
    "5912": 0.85,  # drug stores
    "8011": 0.90,  # medical
    "4111": 1.00,  # transportation
}

CROSS_BORDER_MULTIPLIER = 2.5


def _valid_scheme_card_type(rng: random.Random):
    """Pick a (scheme, card_type) combo that's commercially valid."""
    scheme = rng.choice(SCHEMES)
    if scheme == "AMEX":
        card_type = "CREDIT"
    elif scheme == "MAESTRO":
        card_type = "DEBIT"
    elif scheme == "DISCOVER":
        card_type = rng.choices(["CREDIT", "DEBIT"], weights=[0.7, 0.3])[0]
    else:
        card_type = rng.choices(CARD_TYPES, weights=[0.6, 0.35, 0.05])[0]
    return scheme, card_type


def _valid_card_product(rng: random.Random, scheme: str) -> str:
    if scheme == "AMEX":
        return rng.choices(["GOLD", "PLATINUM"], weights=[0.4, 0.6])[0]
    if scheme == "MAESTRO":
        return "CLASSIC"
    return rng.choices(CARD_PRODUCTS, weights=[0.55, 0.25, 0.15, 0.05])[0]


def generate_row(rng: random.Random, rng_np: np.random.Generator) -> dict:
    scheme, card_type = _valid_scheme_card_type(rng)
    card_product = _valid_card_product(rng, scheme)
    merchant_country = rng.choice(COUNTRIES)
    card_country = rng.choice(COUNTRIES)
    cross_border = merchant_country != card_country
    mcc = rng.choice(MCCS)
    amount = float(max(1.0, rng_np.lognormal(mean=3.5, sigma=1.0)))

    base = BASE_RATES.get((scheme, card_type), 1.0)
    multiplier = PRODUCT_MULTIPLIER[card_product] * MCC_MULTIPLIER[mcc]
    if cross_border:
        multiplier *= CROSS_BORDER_MULTIPLIER
    multiplier *= 1.0 + min(0.1, amount / 10000.0)

    rate = base * multiplier + float(rng_np.normal(0, 0.05))
    rate = max(0.05, min(rate, 4.5))

    return {
        "scheme_id":        scheme,
        "card_type":        card_type,
        "card_product":     card_product,
        "mcc":              mcc,
        "amount":           round(amount, 2),
        "merchant_country": merchant_country,
        "card_country":     card_country,
        "cross_border":     int(cross_border),
        "interchange_rate": round(rate, 4),
    }


def main(n_rows: int = 25_000, seed: int = 42):
    rng = random.Random(seed)
    rng_np = np.random.default_rng(seed)

    out_dir = Path(__file__).parent / "data"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / "synthetic_interchange.csv"

    rows = [generate_row(rng, rng_np) for _ in range(n_rows)]
    fieldnames = list(rows[0].keys())

    with open(out_file, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {n_rows:,} rows to {out_file}")
    avg = sum(r["interchange_rate"] for r in rows) / n_rows
    cb = sum(1 for r in rows if r["cross_border"]) / n_rows
    print(f"  Mean interchange rate: {avg:.3f}%")
    print(f"  Cross-border share:    {cb:.1%}")


if __name__ == "__main__":
    main()
