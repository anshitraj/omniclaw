# Compliance Architecture

> How OmniClaw answers the question agentic payments were always going to ask: **who authorized this transaction — and is that provable?**

---

## The Problem Traditional Compliance Wasn't Built For

Classical payment compliance assumes a human is somewhere in the loop. A person initiates a wire. A person approves a trade. A person is held accountable.

Agentic payments break this assumption. When an AI agent pays for compute, settles a microtransaction, or routes funds across chains — autonomously, at speed, without a human confirmation step — the compliance question shifts:

- Who authorized the agent to act?
- What were the bounds of that authorization?
- When something goes wrong, where does the audit trail start?

These are not new questions in compliance. They are the same questions that govern trust accounts, TPPP relationships, and correspondent banking. The difference is that agentic systems generate them at a scale and speed that manual review can't keep up with.

OmniClaw is designed to make these questions answerable.

---

## The Authorization Layer

OmniClaw sits between agent intent and settled payment. That position is deliberate.

Every payment call in OmniClaw is:

1. **Tied to an explicit agent identity** — the Financial Policy Engine requires the calling agent to be identifiable at the operator level. Anonymous agents cannot initiate payments.

2. **Bound by operator-defined policy** — spending limits, velocity controls, permitted counterparties, and trust thresholds are set at the operator level before any agent executes. The agent operates within a policy envelope, not around one.

3. **Simulated before execution** — `simulate()` runs the full payment logic and surfaces the expected outcome before funds move. This creates a pre-execution compliance checkpoint that operators or automated monitors can act on.

4. **Logged with a traceable authorization event** — every settled payment has a record of: which agent requested it, which policy allowed it, and which operator is accountable for that policy.

This structure separates three concerns that are often collapsed in agentic system designs:

| Concern | Who owns it |
|---|---|
| Execution | The agent |
| Policy | The operator |
| Enforcement | OmniClaw |

Keeping these separate is what makes the system auditable.

---

## Regulatory Alignment

### CLARITY Act

The CLARITY Act draws a line between *passive* yield (interest that accrues without user action) and *active* payment flows (transactions that result from an explicit instruction).

OmniClaw operates exclusively on the active side of this line. Every transaction in OmniClaw is the result of an explicit `pay()` call bound to an agent identity and operator policy. There is no passive accumulation. There is no yield without an authorization event.

For products built on OmniClaw: the authorization chain is built in.

### Travel Rule & Counterparty Identification

Agentic payments frequently involve agent-to-agent transfers where neither party is a natural person. OmniClaw's trust gate — integrating ERC-8004-style trust evaluation — provides a framework for attaching verifiable trust signals to agent identities before transfers occur.

This does not replace Travel Rule compliance for regulated transfers. It provides the identity infrastructure that makes Travel Rule compliance tractable at agent scale.

### Operator Accountability Model

Under most existing frameworks, liability for an unauthorized payment traces to the entity that controlled the payment initiation. OmniClaw's architecture makes this explicit:

- Operators set policy
- Agents execute within that policy
- OmniClaw enforces the boundary

An operator who sets a policy permitting a payment bears accountability for payments made under that policy. An agent that attempts to exceed its policy envelope is blocked before execution.

This maps more cleanly onto existing principal-agent liability frameworks than architectures where the agent has unbounded payment authority.

---

## What This Means for Builders

If you are building an agentic application that touches payments, the compliance questions will come. They will come from your legal team, your banking partners, your enterprise customers, and eventually from regulators.

OmniClaw gives you an architecture that anticipates those questions:

- **Audit trail is built in**, not bolted on
- **Policy is operator-controlled**, not hardcoded in agent logic
- **Authorization is explicit and traceable** at every step
- **Simulation creates a checkpoint** before any irreversible action

You do not need to solve the compliance layer yourself. That is what OmniClaw is for.

---

## Further Reading

- [OmniClaw README](../README.md)
- [CONTRIBUTING.md](../CONTRIBUTING.md)
- [CLARITY Act overview](https://www.congress.gov/bill/119th-congress/house-bill/1234) *(link to be updated as bill progresses)*
- [ERC-8004 Agent Trust Standard](https://eips.ethereum.org/EIPS/eip-8004)
- [Circle Payment Intents documentation](https://developers.circle.com)

---

*This document reflects the compliance design philosophy of OmniClaw as of March 2026. Regulatory frameworks for agentic payments are evolving. This is not legal advice.*
