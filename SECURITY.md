# Security

Proof is a simulated payment system. Use fictional data and dedicated sandbox
databases. Developer mode exposes fixture endpoints and is intended for loopback.
Use sandbox mode for the public demo and operations mode for named credentials.

Report suspected vulnerabilities privately to the maintainer. Include the affected
commit, a synthetic reproduction, and the expected and observed behavior. Redact
bearer tokens, database URLs, provider secrets, and personal information.

See the [threat model](docs/THREAT_MODEL.md) for boundaries and the
[deployment guide](docs/DEPLOYMENT.md) for runtime and migration privileges.
