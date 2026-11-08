# Local Benchmark Evidence

Start the API from source in development mode on port 8000 with a local test
database. Then run:

```powershell
uv run python scripts/benchmark_api.py --requests 100 --concurrency 8
```

The script creates a fictional test tenant and writes the result to
`artifacts/benchmarks/latest.json` by default. A failed request makes the command
exit nonzero after saving the report. The sandbox deployment disables the
fixture endpoints needed for this benchmark.

## Recorded observation

- 100 of 100 fictional transfers returned HTTP 201.
- Eight concurrent clients deliberately contended on one protected source account.
- Observed throughput was 11.14 transfers/second.
- Mean latency was 690.37 ms and p95 was 988.17 ms.

The [recorded run](local-latest.json) used a Windows laptop and localhost.
It includes synchronous API work, PostgreSQL row-lock serialization, balance
derivation from journal entries, and test-client overhead. Results are specific
to that synthetic workload and build.

## Interpretation

The test confirms correctness under a deliberately contended workload, not high throughput. ADR-005 predicts the source account will serialize competing spending. Before optimizing, the next investigation should separate:

1. HTTP/client overhead;
2. source-account lock wait;
3. derived-balance aggregation cost;
4. journal and outbox insert cost.

A projected balance may reduce aggregation cost, but it must remain reproducible from immutable entries and be validated against lock-wait and query-plan evidence before adoption.
