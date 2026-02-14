# Tool Selection Matrix

Detailed decision criteria for choosing between n8n, Python, or hybrid approaches.

---

## The Fundamental Question

Before writing a single line of code or dragging a single node:

> **What tool is appropriate for this specific problem, and who will maintain it?**

---

## Decision Matrix

### Authentication Complexity

| Scenario | Recommended Tool | Rationale |
|----------|------------------|-----------|
| Simple API key | Either | Trivial either way |
| OAuth 2.0 (Google, Slack, HubSpot) | **n8n** | Managed token lifecycle, refresh handling |
| Custom OAuth implementation | Python | Full control needed |
| Multi-tenant OAuth | Hybrid | n8n per-tenant, Python for management |

**The OAuth Reality Check:**
- Redirect URLs
- Authorization codes
- Access tokens
- Refresh tokens
- Token expiration
- Secure storage
- Rotation handling

n8n handles ALL of this. Python implementations often store tokens in plaintext.

---

### Maintainability Assessment

| Maintenance Team | Recommended Tool | Why |
|------------------|------------------|-----|
| Non-technical business users | **n8n** | Visual = self-documenting |
| Mixed technical/non-technical | **Hybrid** | n8n for UI, Python for logic |
| Dedicated dev team | Either | Choose based on other factors |
| Solo developer, future handoff unknown | **n8n** | Lower barrier for successor |
| Offshore/contractor rotation | **n8n** | Reduces ramp-up time |

**The Handoff Test:**
> "If I get hit by a bus, can someone else figure this out within a day?"

---

### Process Duration

| Process Span | Recommended Tool | Implementation |
|--------------|------------------|----------------|
| Seconds to minutes | Either | Standard execution |
| Hours | **n8n** | Wait node |
| Days to weeks | **n8n** | Wait node with resume |
| Human approval required | **n8n** | Webhook + Wait pattern |
| Complex state machine | Hybrid | n8n orchestration, DB state |

**Why Wait Matters:**

Python "waiting":
```python
# Option A: Server stays running (expensive)
time.sleep(259200)  # 3 days

# Option B: Complex state management
# - Save state to database
# - Set up scheduler
# - Reconstruct context on resume
# - Handle edge cases
```

n8n waiting:
```
[Trigger] → [Process] → [Wait 3 days] → [Continue]
```

---

### Data Volume Thresholds

| Data Characteristic | Threshold | Recommended Tool |
|--------------------|-----------|------------------|
| Records per execution | < 5,000 | n8n |
| Records per execution | > 5,000 | **Python** |
| File size | < 20 MB | n8n |
| File size | > 20 MB | **Python** |
| In-memory processing | < 500 MB | n8n (with caution) |
| In-memory processing | > 500 MB | **Python** |
| Streaming required | Yes | **Python** |
| Batch processing | Large batches | **Python** |

**Memory Crash Prevention:**

n8n runs on Node.js with default memory limits. These operations will crash:
- Loading 50MB PDF into memory
- Iterating 10,000 rows while holding all in memory
- Processing video files
- Large JSON payloads

Python solutions:
- `pandas` with chunked reading
- Generator-based streaming
- Memory-mapped files
- Explicit garbage collection

---

### Logic Complexity

| Complexity Indicator | Threshold | Recommended Tool |
|---------------------|-----------|------------------|
| Conditional branches | 1-2 | n8n IF/Switch |
| Conditional branches | 3-4 | Code block in n8n |
| Conditional branches | 5+ | **Python** |
| Nested conditionals | Any | **Python** |
| Algorithmic processing | Any | **Python** |
| Fuzzy matching | Complex | **Python** |
| Mathematical transformations | Complex | **Python** |
| State accumulation in loops | Yes | **Python** |

**The Visual Complexity Ceiling:**

You've crossed it when:
- Canvas looks like spaghetti
- Lines crossing everywhere
- Nodes stacked incomprehensibly
- Must zoom out to see structure
- Can't read node labels at usable zoom

**The 20-Line Test:**
> "Can this logic be expressed in 20 lines of readable code?"
> If yes → Use a Code node
> If it would take 50+ nodes → Definitely use code

---

### Innovation Requirements

| Requirement | Recommended Tool |
|-------------|------------------|
| Standard SaaS integrations | n8n |
| Latest AI libraries (released < 6 months) | **Python** |
| Experimental frameworks | **Python** |
| GraphRAG, advanced RAG patterns | **Python** |
| Custom ML models | **Python** |
| Stable, well-documented APIs | Either |

**The Lag Reality:**
n8n team must evaluate → integrate → test → document before new libraries appear as nodes.

If you need something released last month → use Python.

---

## Hybrid Architecture Patterns

### Pattern 1: n8n Orchestration + Python Microservice

```
┌──────────────────────────────────────────────────┐
│                    n8n Layer                      │
│  ┌─────────┐   ┌─────────┐   ┌─────────┐        │
│  │ Webhook │ → │ HTTP    │ → │ Slack   │        │
│  │ Trigger │   │ Request │   │ Notify  │        │
│  └─────────┘   └────┬────┘   └─────────┘        │
│                     │                            │
└─────────────────────┼────────────────────────────┘
                      │ API Call
                      ▼
┌──────────────────────────────────────────────────┐
│               Python Microservice                 │
│  ┌─────────────────────────────────────────────┐ │
│  │ • Complex data processing                   │ │
│  │ • AI/ML operations                          │ │
│  │ • Heavy computation                         │ │
│  │ • Returns JSON result                       │ │
│  └─────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────┘
```

**Use when**: Need Python capabilities but want n8n's integrations

### Pattern 2: n8n Code Nodes

```
┌──────────────────────────────────────────────────┐
│                    n8n Workflow                   │
│                                                   │
│  ┌─────────┐   ┌─────────┐   ┌─────────┐        │
│  │ Trigger │ → │ Code    │ → │ Output  │        │
│  │         │   │ (JS/Py) │   │ Node    │        │
│  └─────────┘   └─────────┘   └─────────┘        │
│                                                   │
└──────────────────────────────────────────────────┘
```

**Use when**: Logic is complex but contained, no external service needed

### Pattern 3: Event-Driven Handoff

```
n8n Workflow A              Python Service              n8n Workflow B
┌───────────────┐          ┌───────────────┐          ┌───────────────┐
│ Trigger       │          │               │          │ Webhook       │
│ → Validate    │  ──────► │ Process       │ ──────►  │ → Transform   │
│ → Queue job   │          │ → Compute     │          │ → Notify      │
└───────────────┘          │ → Callback    │          └───────────────┘
                           └───────────────┘
```

**Use when**: Long-running Python processes, async patterns

---

## Decision Flowchart

```
                    START
                      │
                      ▼
              ┌───────────────┐
              │ OAuth needed? │
              └───────┬───────┘
                 Yes  │  No
          ┌───────────┴───────────┐
          ▼                       ▼
    Use n8n for auth      ┌───────────────┐
          │               │ > 5000 records │
          │               │ or > 20MB file?│
          │               └───────┬───────┘
          │                  Yes  │  No
          │           ┌───────────┴───────────┐
          │           ▼                       ▼
          │     Use Python for          ┌───────────────┐
          │     processing              │ > 20 nodes of │
          │           │                 │ business logic?│
          │           │                 └───────┬───────┘
          │           │                    Yes  │  No
          │           │             ┌───────────┴───────────┐
          │           │             ▼                       ▼
          │           │       Use Code nodes          ┌───────────────┐
          │           │       in n8n                  │ Non-tech      │
          │           │             │                 │ maintainers?  │
          │           │             │                 └───────┬───────┘
          │           │             │                    Yes  │  No
          │           │             │             ┌───────────┴───────────┐
          │           │             │             ▼                       ▼
          │           │             │        Use n8n               Use either
          │           │             │             │                 (preference)
          │           │             │             │                       │
          └───────────┴─────────────┴─────────────┴───────────────────────┘
                                          │
                                          ▼
                                   IMPLEMENTATION
```

---

## Anti-Patterns to Avoid

### 1. "n8n Can Do Everything"
**Reality**: Visual workflows have limits. Forcing complex logic creates unmaintainable spaghetti.

### 2. "Python Is Always Better"
**Reality**: Python requires more infrastructure, harder handoff, reinventing OAuth wheels.

### 3. "We'll Optimize Later"
**Reality**: Architecture decisions compound. Wrong tool choice at start = painful migration later.

### 4. "It Works in Testing"
**Reality**: Production has volume, edge cases, failures. Test with realistic data.

### 5. "The Demo Looked Great"
**Reality**: Demos show happy paths. Production needs error handling, monitoring, recovery.

---

## Quick Reference Card

| Factor | n8n | Python | Hybrid |
|--------|-----|--------|--------|
| OAuth services | ✅ | ⚠️ | ✅ |
| Non-tech maintainers | ✅ | ❌ | ⚠️ |
| Multi-day waits | ✅ | ⚠️ | ✅ |
| Large data (5k+ rows) | ❌ | ✅ | ✅ |
| Large files (20MB+) | ❌ | ✅ | ✅ |
| Complex algorithms | ⚠️ | ✅ | ✅ |
| Cutting-edge AI | ❌ | ✅ | ✅ |
| Standard integrations | ✅ | ⚠️ | ✅ |
| Rapid prototyping | ✅ | ⚠️ | ⚠️ |
| Long-term maintenance | ✅ | ⚠️ | ✅ |

**Legend**: ✅ Recommended | ⚠️ Possible with caveats | ❌ Not recommended

---

## Related Skills

- **n8n-code-javascript** - When Code nodes are the answer
- **n8n-code-python** - For Python Code nodes
- **n8n-workflow-patterns** - Once tool is chosen, pick the right pattern
