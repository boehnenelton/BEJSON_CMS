# AI Agentic Loops

## Core Architecture, Schema & Structural Invariants

## Core Architecture: The GSRES Framework

The **GSRES** (*Goal State Resolution & Execution System*) architecture decouples intent specification from execution mechanics. In an agentic loop, non-deterministic model outputs must be bounded by deterministic software constraints. The system achieves this by encapsulating execution inside an immutable, event-driven **FSM** (*Finite State Machine*) governed by explicit target states, trajectory vectors, and cryptographically verifiable trace logs.

```
       ┌────────────────────────────────────────────────────────┐
       │                                                        │
       ▼                                                        │
┌──────────────┐   Evaluate    ┌──────────────┐   Dispatch   ┌──┴───────────┐
│  INITIALIZED ├──────────────►│  EVALUATING  ├─────────────►│   ACTING     │
└──────────────┘               └──────┬───────┘              └──┬───────────┘
                                      │                         │
                                Target│Reached           Result │Returned
                                      ▼                         ▼
┌──────────────┐   Reject Gate ┌──────────────┐  Verify Gate ┌──────────────┐
│ DEAD_LETTER  │◄──────────────┤ CONVERGED    │◄─────────────┤  VERIFYING   │
└──────────────┘               └──────────────┘              └──────────────┘
```

### State Machine Transition Contracts

Every agent loop step advances through a strict set of transitions. Invalid state jumps immediately halt execution and trigger a telemetry fault.

| Source State | Trigger Event | Guard Condition | Target State | Invariant Side Effect |
| :--- | :--- | :--- | :--- | :--- |
| `INITIALIZED` | `EV_PLAN` | Valid Goal Schema & Context Payload | `EVALUATING` | Mint root hash `H0` |
| `EVALUATING` | `EV_DISPATCH` | Proposed Action satisfies Static Policy | `ACTING` | Append intent to Ledger |
| `ACTING` | `EV_RECEIVE` | Execution Payload returned within SLA | `VERIFYING` | Record IO snapshot |
| `VERIFYING` | `EV_PASS` | Goal Delta Metric $\le \epsilon$ | `CONVERGED` | Emit completion block |
| `VERIFYING` | `EV_RETRY` | Iteration Count < Max Retry Threshold | `EVALUATING` | Increment iteration counter |
| `ANY` | `EV_FAIL` | Unrecoverable Policy or Schema Violation | `DEAD_LETTER` | Freeze state & notify alert bus |

---

## Schema Specifications

To guarantee system-wide interoperability within the BEJSON CMS infrastructure, goal inputs, agent trajectories, and audit entries follow rigid TypeScript interfaces.

```typescript
/**
 * Represents a goal-oriented execution payload.
 * Target state metrics must be defined as declarative constraints.
 */
export interface GoalPayload {
  readonly goalId: string; // UUIDv4 primary key
  readonly namespace: string; // Tenant/Domain isolation tag
  readonly declarativeState: Record<string, unknown>; // Expected terminal state
  readonly maxIterations: number; // Hard loop exit boundary
  readonly errorTolerance: number; // Epsilon threshold for convergence
  readonly createdAt: number; // Epoch timestamp (ms)
}

/**
 * Single step execution record within an agent loop.
 */
export interface ExecutionNode {
  readonly nodeId: string;
  readonly parentNodeId: string | null; // Null for root step
  readonly stepSequence: number; // Monotonically increasing index
  readonly actionName: string; // Target tool or internal operation
  readonly parameters: Record<string, unknown>; // Sanitized input vector
  readonly outputSnapshot: Record<string, unknown>; // Captured response payload
  readonly durationMs: number; // Execution latency
}

/**
 * GSRES Cryptographic Audit Ledger Entry.
 * Ensures non-repudiation via SHA-256 hash chains.
 */
export interface AuditBlock {
  readonly index: number;
  readonly timestamp: number;
  readonly goalId: string;
  readonly executionNode: ExecutionNode;
  readonly previousHash: string; // SHA-256 hash of block (n-1)
  readonly currentHash: string; // SHA-256(index + previousHash + Payload)
}
```

---

## Structural Invariants

Architectural invariants are non-negotiable structural assertions enforced at the runtime kernel layer. A failure of any invariant causes an immediate system abort.

1. **Monotonic Sequence Ordering:** 
   An execution sequence $S = \{s_0, s_1, \dots, s_n\}$ must satisfy $s_i = s_{i-1} + 1$. Sequence gaps or duplicated steps represent state corruption.
2. **Cryptographic Chain Continuity:** 
   For every block $B_i$ in the audit ledger where $i > 0$, $B_i.\text{previousHash} \equiv \text{SHA256}(B_{i-1})$.
3. **Epistemic Isolation:** 
   Tool execution contexts in state `ACTING` cannot directly mutate state machine state variables. Writes are restricted to isolated memory regions, verified prior to state state ingestion (`VERIFYING`).
4. **Deterministic Convergence Gating:** 
   The transition from `VERIFYING` to `CONVERGED` requires explicit assertion pass vectors from an external **Verification Oracle** (*a deterministic evaluator function*), preventing LLM self-certification loops.

> [!IMPORTANT]
> Never allow an agent to self-certify its own goal completion state. The `VERIFYING` state must invoke an independent, deterministic evaluator or human-in-the-loop gate before issuing the `EV_PASS` event.

## Verification, Edge Cases & Operational Takeaways

Modern agentic loops operating under the **GSRES** (Goal-State-Reasoning-Execution-State verification) pattern require formal verification mechanisms to prevent non-deterministic state drift and infinite recursion loops. This section outlines the verification architecture, failure recovery protocols, telemetry metrics, and core architectural takeaways.

---

## 1. Formal Verification Gates & State Validation

A **GSRES Verification Gate** is an immutable evaluation layer that executes immediately following the execution phase. It asserts that the system's updated state ($S_{t+1}$) satisfies the invariants defined by the target sub-goal ($G_k$) before allowing the state machine to transition.

```
       +------------------+
       |  Execution Phase |
       +--------+---------+
                |
                v
  +---------------------------+
  |  GSRES Verification Gate   |
  |  (State Validation AST)   |
  +-------------+-------------+
                |
       +--------+--------+
       |                 |
  [ Validated ]    [ Invalid / Drift ]
       |                 |
       v                 v
+--------------+  +-------------------+
| Commit State |  | Fallback & Retry  |
+--------------+  +-------------------+
```

### Deterministic State Invariants

Verification must not rely solely on probabilistic LLM (Large Language Model) self-grading. It combines two validation primitives:

1. **Deterministic Structural Assertions**: Schema validation using JSON Schema / Zod to ensure tool payloads match target types.
2. **Semantic Goal Satisfaction**: LLM-as-a-Judge or static analyzer checking context consistency against defined bounds.

---

## 2. Failure Modes & Remediation Matrix

When operating dynamic agentic loops, systems encounter failure conditions unique to probabilistic state machines.

| Failure Mode | Root Cause | Detection Mechanism | Remediation Strategy |
| :--- | :--- | :--- | :--- |
| **Loop Divergence** | Reasoning model generates repetitive tool calls without state convergence. | Context Entropy Monitor (repetition count > 3). | Prune context history, inject explicit divergence alert, step down step limit. |
| **Hallucinated Completion** | Agent emits a terminal `SUCCESS` flag without executing required mutations. | Verification Gate assertion failure ($S_{t+1} == S_t$). | Reject state transition; force re-evaluating execution delta. |
| **Audit Trace Hash Drift** | Cryptographic audit logs misalign due to uncaptured asynchronous side-effects. | Merkle tree validation mismatch across state steps. | Halt agent transaction, rollback execution context, isolate step. |
| **Tool Failure Cascade** | External API endpoints return partial mutations with 500-series errors. | Non-idempotent error responses from tool bus. | Execute inverse compensation functions (Saga pattern rollback). |

> [!IMPORTANT]
> Never permit an agentic loop to self-terminate under `SUCCESS` without passing an out-of-band validation check. Self-reported success from probabilistic models exhibits up to a 14% false-positive rate under complex multi-tool workflows.

---

## 3. Production Verification Engine Pattern

The following TypeScript implementation demonstrates an production-grade GSRES verification engine featuring deterministic state assertions and automatic fallback routing.

```typescript
import { z } from "zod";

// Define strict GSRES state schemas
export const GoalStateSchema = z.object({
  goalId: z.string().uuid(),
  targetInvariant: z.string(),
  maxDepth: z.number().int().positive(),
  currentDepth: z.number().int().nonnegative(),
});

export const ExecutionResultSchema = z.object({
  stepId: z.string().uuid(),
  toolUsed: z.string(),
  mutationHash: z.string(),
  stateDelta: z.record(z.unknown()),
});

export type GoalState = z.infer<typeof GoalStateSchema>;
export type ExecutionResult = z.infer<typeof ExecutionResultSchema>;

export interface VerificationOutcome {
  isValid: boolean;
  reason?: string;
  divergenceDetected: boolean;
}

export class GSRESVerificationEngine {
  private executionHistoryHashes: Set<string> = new Set();

  public async verifyStateTransition(
    goal: GoalState,
    result: ExecutionResult,
    assertStatePredicate: (delta: Record<string, unknown>) => boolean
  ): Promise<VerificationOutcome> {
    // 1. Boundary Guard Checks
    if (goal.currentDepth >= goal.maxDepth) {
      return { isValid: false, reason: "Max execution depth exceeded.", divergenceDetected: true };
    }

    // 2. Loop Divergence Check via Mutation Hashing
    if (this.executionHistoryHashes.has(result.mutationHash)) {
      return { 
        isValid: false, 
        reason: `Loop divergence detected: Identical mutation hash ${result.mutationHash}`, 
        divergenceDetected: true 
      };
    }
    this.executionHistoryHashes.add(result.mutationHash);

    // 3. Deterministic Predicate Evaluation
    const predicatePassed = assertStatePredicate(result.stateDelta);
    if (!predicatePassed) {
      return { 
        isValid: false, 
        reason: "State invariant assertion returned false.", 
        divergenceDetected: false 
      };
    }

    return { isValid: true, divergenceDetected: false };
  }
}
```

---

## 4. Operational Telemetry & Performance SLAs

To maintain high throughput without exhausting token budgets or introducing latency spikes, monitor these metrics:

| Metric Name | Target SLA (p95) | Alert Threshold | Operational Implication |
| :--- | :--- | :--- | :--- |
| **Convergence Latency** | $< 2,500 \text{ ms}$ | $> 5,000 \text{ ms}$ | Indicates excessive sub-goal decomposition or model stalling. |
| **Context Entropy Index** | $< 0.45$ | $> 0.70$ | High entropy implies redundant tokens and risk of context degradation. |
| **Verification Gate Pass Rate**| $> 96.5\%$ | $< 90.0\%$ | Low pass rate signals bad system prompts or failing external tools. |
| **Audit Hash Overhead** | $< 12 \text{ ms}$ | $> 50 \text{ ms}$ | High latency indicates bottlenecks in cryptographically signing execution steps. |

> [!TIP]
> Implement aggressive prompt-caching and context-pruning algorithms at every step threshold. Storing only state diffs rather than full raw conversation threads reduces execution costs by up to 60%.

---

## 5. Summary of Architectural Takeaways

1. **Decouple Planning from Verification**: Never allow the reasoning engine to validate its own output without external constraint checks.
2. **Treat State updates as Cryptographic Ledgers**: Employ append-only logs signed with SHA-256 state hashes to simplify post-mortem auditing.
3. **Enforce Deterministic Safeguards**: Wrap probabilistic agents with strict step limits, circuit breakers, and schema validations.
