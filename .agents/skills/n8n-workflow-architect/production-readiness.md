# Production Readiness Checklist

Detailed guidance for deploying automation that survives contact with reality.

---

## The Production Gap

> The gap between a workflow that works in testing and one that runs reliably in production is larger than most people realize.

This document covers the operational concerns that separate professional automation from amateur hour.

---

## 1. Observability

### Why It Matters

Default behavior: **Silent failure**
- Workflow errors at 2:47 AM
- Nobody knows until Monday
- Customer complaints reveal the problem
- Hours of processing lost
- No idea how many executions failed

### Required Components

#### A. Error Notification Workflow

Every production workflow needs an error handler.

```
Error Trigger (for main workflow)
    │
    ▼
┌─────────────────────────────┐
│ Prepare Error Notification  │
│ - Workflow name             │
│ - Error message             │
│ - Timestamp                 │
│ - Execution link            │
└─────────────────────────────┘
    │
    ▼
┌─────────────────────────────┐
│ Send to Monitored Channel   │
│ - Slack                     │
│ - Email                     │
│ - PagerDuty                 │
└─────────────────────────────┘
```

**Implementation:**
```javascript
// In Error Trigger workflow - Set node
{
  "workflow": "{{ $json.workflow.name }}",
  "error": "{{ $json.execution.error.message }}",
  "timestamp": "{{ $now.toISO() }}",
  "execution_url": "{{ $json.execution.url }}",
  "severity": "{{ $json.workflow.name.includes('critical') ? 'high' : 'normal' }}"
}
```

#### B. Execution Logging

Create a dedicated logging table:

```sql
CREATE TABLE workflow_executions (
  id SERIAL PRIMARY KEY,
  workflow_id VARCHAR(255),
  workflow_name VARCHAR(255),
  status VARCHAR(50),  -- success, failure, running
  started_at TIMESTAMP,
  finished_at TIMESTAMP,
  error_message TEXT,
  input_summary JSONB,
  execution_url VARCHAR(500),
  created_at TIMESTAMP DEFAULT NOW()
);
```

**Log at workflow start and end:**
- Start: Insert with status='running'
- Success: Update status='success', set finished_at
- Failure: Update status='failure', set error_message

#### C. Health Checks

Daily heartbeat workflow for critical systems:

```
Schedule (daily 6 AM)
    │
    ├─► Check credential validity
    │   └─► Test API call to each service
    │
    ├─► Check database connections
    │   └─► Simple SELECT query
    │
    ├─► Check external API health
    │   └─► Status endpoints
    │
    └─► Report Results
        ├─► All healthy → Quiet (or optional Slack)
        └─► Any failure → Alert immediately
```

#### D. Structured Alerting

| Severity | Response Time | Channel | Examples |
|----------|--------------|---------|----------|
| Critical | Immediate | PagerDuty/Phone | Payment processing failure |
| High | Within 1 hour | Slack + Email | Customer data sync failure |
| Medium | Same business day | Slack | Internal report failure |
| Low | Next business day | Log only | Non-critical notification skip |

---

## 2. Idempotency

### Why It Matters

Real-world triggers fire multiple times:
- Webhooks retry on slow response
- Users double-click submit
- Network hiccups cause duplicates

**Consequences of non-idempotent workflows:**
- Duplicate CRM entries (embarrassing)
- Duplicate invoices (erodes trust)
- Duplicate charges (legal liability)

### Implementation Patterns

#### A. Unique Request Identification

Most webhooks include a unique ID. Store and check.

```javascript
// At workflow start
const requestId = $json.body.request_id || $json.headers['x-request-id'];

// Check if already processed
const existing = await $getWorkflowStaticData('global');
if (existing.processedIds?.includes(requestId)) {
  return []; // Skip - already processed
}

// After successful processing
const staticData = await $getWorkflowStaticData('global');
staticData.processedIds = staticData.processedIds || [];
staticData.processedIds.push(requestId);
// Keep only last 1000 to prevent memory bloat
if (staticData.processedIds.length > 1000) {
  staticData.processedIds = staticData.processedIds.slice(-1000);
}
```

For persistent tracking (recommended for production):

```sql
CREATE TABLE processed_requests (
  request_id VARCHAR(255) PRIMARY KEY,
  workflow_name VARCHAR(255),
  processed_at TIMESTAMP DEFAULT NOW(),
  result_summary JSONB
);

-- Before processing
SELECT 1 FROM processed_requests WHERE request_id = $1;
-- If exists, return cached result or skip

-- After processing
INSERT INTO processed_requests (request_id, workflow_name, result_summary)
VALUES ($1, $2, $3)
ON CONFLICT (request_id) DO NOTHING;
```

#### B. Check-Before-Create

```javascript
// Before creating a contact in CRM
const existingContact = await hubspotApi.searchContacts({
  email: newLead.email
});

if (existingContact.results.length > 0) {
  // Update existing instead of creating duplicate
  return await hubspotApi.updateContact(existingContact.results[0].id, newLead);
} else {
  return await hubspotApi.createContact(newLead);
}
```

#### C. Upsert Operations

When available, use "update or create":

```sql
-- PostgreSQL
INSERT INTO customers (email, name, updated_at)
VALUES ($1, $2, NOW())
ON CONFLICT (email)
DO UPDATE SET name = $2, updated_at = NOW();
```

```javascript
// Airtable
// Use Update Record with "Upsert" enabled
```

#### D. Idempotency Keys for APIs

Payment APIs especially support this:

```javascript
// Stripe example
const paymentIntent = await stripe.paymentIntents.create({
  amount: 2000,
  currency: 'usd',
  idempotency_key: `order_${orderId}_payment`
});
// Same key = same result, no duplicate charge
```

### The Idempotency Test

> "If this webhook fires three times in a row with identical data, what happens?"

- ✅ Same result, single record, single charge
- ❌ Three records, three charges

---

## 3. Cost Management

### The AI Tax

Single GPT-4 call: ~$0.03
10,000 form submissions/month: $300/month ongoing

This isn't an argument against AI. It's an argument for treating AI costs as first-class architectural concerns.

### Cost Control Strategies

#### A. Calculate Before Building

```markdown
## AI Cost Projection: Lead Qualification

Monthly leads: 5,000
Processing per lead:
- Classification: 1 call @ $0.01 (GPT-3.5)
- Scoring analysis: 1 call @ $0.03 (GPT-4)
- Summary generation: 1 call @ $0.03 (GPT-4)

Monthly AI cost: 5,000 × $0.07 = $350/month

Alternative with caching (60% cache hit rate):
Actual calls: 5,000 × 0.4 = 2,000
Monthly AI cost: 2,000 × $0.07 = $140/month
```

Share projections with stakeholders BEFORE building.

#### B. Question the Necessity

| Task | AI Needed? | Alternative |
|------|------------|-------------|
| Keyword classification | Maybe | Keyword matching, lookup table |
| Email categorization | Maybe | Rule-based routing |
| Phone format validation | No | Regex |
| Sentiment analysis | Usually | Simple scoring or skip |
| Content summarization | Yes | - |
| Complex reasoning | Yes | - |

#### C. Cache Aggressively

```javascript
// Document summarization with caching
const documentHash = crypto.createHash('md5')
  .update(document.content)
  .digest('hex');

// Check cache
const cached = await db.query(
  'SELECT summary FROM document_cache WHERE hash = $1',
  [documentHash]
);

if (cached.rows.length > 0) {
  return cached.rows[0].summary;
}

// Generate and cache
const summary = await openai.summarize(document.content);
await db.query(
  'INSERT INTO document_cache (hash, summary) VALUES ($1, $2)',
  [documentHash, summary]
);
return summary;
```

#### D. Right-Size Models

| Task | Model | Approx Cost |
|------|-------|-------------|
| Simple classification | GPT-3.5 / Haiku | ~$0.001 |
| Standard analysis | GPT-4o-mini / Sonnet | ~$0.01 |
| Complex reasoning | GPT-4 / Opus | ~$0.05 |

Don't use Opus for tasks Haiku can handle.

#### E. Monitor Spend

Set up cost alerts:
- Daily usage tracking
- Threshold notifications (80%, 100%, 120% of budget)
- Per-workflow cost attribution

---

## 4. Rate Limit Handling

### The Problem

5,000 leads to enrich, API allows 100/minute.

**Naive approach**: Process all immediately
**Result**: Thousands of 429 errors, crashed workflow, unknown state

### Solutions

#### A. Know Your Limits

Before integrating, document:

| API | Rate Limit | Burst | Consequence |
|-----|------------|-------|-------------|
| HubSpot | 100/10sec | 110 | 429 + retry-after header |
| Shopify | 40/min sustained | 2/sec burst | Leaky bucket |
| OpenAI | Varies by tier | - | 429 + exponential backoff |
| Stripe | 100/sec (most) | - | 429 |

#### B. Batch with Delays

```javascript
// n8n Split In Batches configuration
{
  "batchSize": 80,  // Under the 100/min limit
  "options": {
    "reset": false
  }
}

// Add Wait node after batch
// Wait: 65 seconds (buffer over 60)
```

#### C. Implement Retry Logic

```javascript
// In Code node - retry wrapper
async function withRetry(fn, maxRetries = 3) {
  for (let attempt = 1; attempt <= maxRetries; attempt++) {
    try {
      return await fn();
    } catch (error) {
      if (error.status === 429 && attempt < maxRetries) {
        const waitTime = Math.pow(2, attempt) * 1000; // Exponential backoff
        await new Promise(resolve => setTimeout(resolve, waitTime));
        continue;
      }
      throw error;
    }
  }
}
```

#### D. Track Progress for Resumability

```sql
CREATE TABLE bulk_job_progress (
  job_id UUID PRIMARY KEY,
  workflow_name VARCHAR(255),
  total_items INT,
  processed_items INT DEFAULT 0,
  last_processed_id VARCHAR(255),
  status VARCHAR(50) DEFAULT 'running',
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- Update after each batch
UPDATE bulk_job_progress
SET processed_items = processed_items + $1,
    last_processed_id = $2,
    updated_at = NOW()
WHERE job_id = $3;
```

If workflow fails at item 3,000 of 5,000, resume from 3,001.

---

## 5. Manual Overrides

### The Problem

Automation runs without intervention. This is a weakness when:
- Requirements change suddenly
- PR crisis requires pause
- Legal hold on communications
- Bug discovered in production

### Solutions

#### A. Kill Switches

Simple toggle accessible to non-technical staff:

```
Option 1: Airtable/Notion Toggle
- Create "System Controls" table
- Row: { workflow: "email-sequence", enabled: true }
- Workflow checks at start: if not enabled, exit

Option 2: Slack Slash Command
- /pause-emails
- Updates toggle in database
- Confirms in channel

Option 3: Simple Admin Page
- Password-protected web page
- Toggle buttons for each workflow
- Audit log of changes
```

**Workflow Check:**
```javascript
// First node after trigger
const controls = await airtable.getRecord('System Controls', 'email-sequence');
if (!controls.fields.enabled) {
  // Log the skip
  await logExecution('skipped', 'Workflow disabled via kill switch');
  return []; // Empty = stop execution
}
```

#### B. Approval Queues

For high-stakes actions:

```
Trigger
    │
    ▼
Process & Prepare Action
    │
    ▼
Insert into Pending Queue (database)
    │
    ▼
Notify Approver (Slack with approve/reject buttons)
    │
    ▼
Wait for Webhook (approval response)
    │
    ├─► Approved → Execute Action
    └─► Rejected → Log & Notify
```

#### C. Comprehensive Audit Trails

Log WHAT happened, not just THAT it happened:

```sql
CREATE TABLE audit_log (
  id SERIAL PRIMARY KEY,
  workflow_name VARCHAR(255),
  action_type VARCHAR(100),
  action_details JSONB,
  affected_entity_type VARCHAR(100),
  affected_entity_id VARCHAR(255),
  performed_at TIMESTAMP DEFAULT NOW(),
  execution_id VARCHAR(255)
);

-- Example entry
{
  "workflow_name": "customer-emails",
  "action_type": "email_sent",
  "action_details": {
    "to": "customer@example.com",
    "subject": "Your Order Confirmation",
    "template": "order_confirm_v2"
  },
  "affected_entity_type": "customer",
  "affected_entity_id": "cust_12345",
  "performed_at": "2024-01-15T10:32:00Z"
}
```

#### D. Configuration Externalization

Don't hardcode values that might change:

```javascript
// Bad: Hardcoded
const notifyEmail = "sales@company.com";

// Good: External configuration
const config = await airtable.getRecord('Config', 'notification-settings');
const notifyEmail = config.fields.sales_notification_email;
```

Configuration table:
| Key | Value | Last Updated | Updated By |
|-----|-------|--------------|------------|
| sales_notification_email | sales@company.com | 2024-01-15 | Admin |
| daily_report_recipients | team@company.com,ceo@company.com | 2024-01-10 | Admin |
| max_retries | 3 | 2024-01-01 | System |

---

## Pre-Launch Checklist Summary

### Tool Selection
- [ ] OAuth authentication → Using n8n
- [ ] > 5,000 records or > 20MB files → Using Python
- [ ] > 20 nodes of logic → Consolidated to code blocks
- [ ] Non-technical maintainers → Using n8n with documentation

### System Design
- [ ] All input validated before processing
- [ ] Workflow delivers business value (not just processes data)
- [ ] State management planned for multi-execution memory

### Production Readiness
- [ ] Error notification workflow configured
- [ ] Execution logging to database
- [ ] Idempotency implemented (duplicate handling)
- [ ] AI/API costs calculated and approved
- [ ] Rate limits respected (batching, delays, retries)
- [ ] Kill switch accessible to operations team
- [ ] Audit trail logging all actions
- [ ] Configuration externalized for easy updates

---

## The Production Mindset

> The shortcuts that save an hour today create the emergencies that cost days later.

Professional automation isn't about building things quickly. It's about building things that last.

When tempted to skip error handling because "it probably won't fail" or ignore rate limits because "we'll fix it later" - remember that production has:

- More volume than testing
- Edge cases you didn't imagine
- Failures at the worst possible times
- Users who don't read instructions
- Integrations that change without notice

Plan for all of it.

---

## Related Skills

- **n8n-validation-expert** - Catch issues before deployment
- **n8n-workflow-patterns** - Error handling patterns
- **n8n-expression-syntax** - Correct data access in error handlers
