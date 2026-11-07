# Proof — Durable Project Memory

Last updated: 2026-11-07

## Identity

- **Name:** Proof
- **Tagline:** Every cent accounted for.
- **Category:** Backend-first payment ledger and reconciliation platform.
- **Primary stack:** Python, FastAPI, PostgreSQL, Redis where justified, SQLAlchemy, Alembic, Docker, OpenTelemetry, Prometheus, and a focused TypeScript operations console.
- **Portfolio owner:** Fabiyi Pelumi (`Cipher126`), a Python/FastAPI backend developer specializing in reliable APIs and distributed systems.

## Why this project exists

Proof must help its owner get hired for backend, platform, fintech, payment-infrastructure, API, and distributed-systems roles. It should demonstrate that he can keep a business-critical system correct when requests are repeated, operations run concurrently, dependencies fail, and external provider records disagree.

Existing projects already demonstrate distributed job execution (Forge), AI tooling (Koda), and secure product development (Family Vault). Proof must add financial-domain correctness and an immediately understandable commercial story instead of repeating those projects.

## Product promise

Proof provides verifiable answers to four questions:

1. What money movement was requested?
2. What immutable accounting entries resulted?
3. What did the external provider report?
4. Why do the records agree or disagree?

## Portfolio narrative

> I build reliable Python systems that remain correct when requests are duplicated, services fail, and money is involved.

Every significant feature should strengthen that sentence.

## Fixed scope

Proof will demonstrate:

- immutable double-entry journals and derived balances;
- accounts, transfers, holds, fees, refunds, and settlement batches;
- idempotent commands and safe concurrent writes;
- authenticated, signed provider webhooks with replay protection;
- a transactional outbox and durable asynchronous processing;
- provider-statement ingestion and automated reconciliation;
- explainable discrepancy detection and operator resolution;
- tenant isolation, scoped credentials, RBAC, and audit trails;
- observable failure simulations and recovery;
- a recruiter-friendly operations console and guided demo.

## Explicit non-goals

- Holding, transmitting, or claiming to transmit real money.
- Connecting to a production bank or payment processor during the core build.
- PCI card-data handling.
- Cryptocurrency or trading functionality.
- A consumer banking application.
- Premature microservices, Kubernetes, or infrastructure added only for résumé keywords.
- AI features without a concrete, testable operational benefit.
- A large frontend that competes with backend correctness for attention.

## Experience target

The canonical demo uses fictional tenants, providers, customers, and funds. A visitor can initiate a transfer, inspect balanced ledger entries, replay a duplicate request safely, inject a provider mismatch, run reconciliation, and see an explainable incident and resolution trail.

## Decision posture

- Correctness before throughput claims.
- Measured evidence before performance language.
- Explicit state machines before ad hoc status fields.
- Database constraints before application-only assumptions.
- A modular monolith before networked services.
- Durable records before caches and queues.
- Clear tradeoffs before fashionable technology.

## Definition of success

Proof succeeds when a hiring manager can understand its value in two minutes, run or view the guided demo, inspect credible engineering evidence, and ask substantive interview questions about concurrency, accounting invariants, failure recovery, security, and architectural tradeoffs.
