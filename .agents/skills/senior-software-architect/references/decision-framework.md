# Architecture Decision Framework

Use only the criteria relevant to the current decision.

## Criteria

- **Correctness:** Which invariants can the design enforce, and where?
- **Failure behavior:** What happens on retry, timeout, duplicate, reordering, partial success, dependency loss, or process death?
- **Consistency:** What must be atomic, what may be eventually consistent, and how are conflicts detected?
- **Security:** What crosses a trust boundary, what is authorized, and what data must not be stored or exposed?
- **Operability:** Can an operator detect, explain, contain, and recover the failure?
- **Evolution:** Can schemas, APIs, and deployments change without destructive coordination?
- **Performance:** What workload matters, where is contention likely, and how will it be measured?
- **Complexity:** What new components, skills, failure modes, and ongoing costs are introduced?

## Decision record shape

Capture:

- context and constraints;
- chosen approach;
- credible alternatives;
- consequences and risks;
- validation evidence;
- rollback or migration path;
- explicit revisit trigger.

## Warning signs

Reconsider a design when its justification is primarily résumé value, hypothetical scale, vendor fashion, symmetry, or avoiding a small amount of clear application code. A technology choice is not an architecture until its data ownership, failure semantics, and operating model are defined.
