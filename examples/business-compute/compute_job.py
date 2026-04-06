from __future__ import annotations

import json
import os
from math import isqrt
from urllib.parse import parse_qs


def prime_count(limit: int) -> int:
    if limit < 2:
        return 0
    sieve = bytearray(b"\x01") * (limit + 1)
    sieve[0:2] = b"\x00\x00"
    for n in range(2, isqrt(limit) + 1):
        if sieve[n]:
            start = n * n
            step = n
            sieve[start : limit + 1 : step] = b"\x00" * (((limit - start) // step) + 1)
    return int(sum(sieve))


def fib(n: int) -> int:
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a


def main() -> None:
    query = parse_qs(os.environ.get("OMNICLAW_REQUEST_QUERY", ""), keep_blank_values=True)
    job = (query.get("job", ["prime-count"])[0] or "prime-count").strip().lower()
    size_raw = (query.get("size", ["50000"])[0] or "50000").strip()
    payer = os.environ.get("OMNICLAW_PAYER_ADDRESS", "unknown")
    tx_hash = os.environ.get("OMNICLAW_TX_HASH", "")
    amount = os.environ.get("OMNICLAW_AMOUNT_USD", "")

    try:
        size = int(size_raw)
    except ValueError as err:
        print(json.dumps({"error": f"invalid size: {size_raw}"}))
        raise SystemExit(2) from err

    if job == "prime-count":
        if size < 10 or size > 500000:
            print(json.dumps({"error": "size must be between 10 and 500000 for prime-count"}))
            raise SystemExit(2)
        result = {
            "service": "mini-aws-compute",
            "job": job,
            "input": {"size": size},
            "output": {"prime_count": prime_count(size)},
            "paid_by": payer,
            "amount_usdc": amount,
            "settlement_tx": tx_hash,
        }
    elif job == "fib":
        if size < 1 or size > 5000:
            print(json.dumps({"error": "size must be between 1 and 5000 for fib"}))
            raise SystemExit(2)
        value = str(fib(size))
        result = {
            "service": "mini-aws-compute",
            "job": job,
            "input": {"n": size},
            "output": {"fib": value},
            "paid_by": payer,
            "amount_usdc": amount,
            "settlement_tx": tx_hash,
        }
    else:
        print(json.dumps({"error": f"unsupported job: {job}"}))
        raise SystemExit(2)

    print(json.dumps(result))


if __name__ == "__main__":
    main()
