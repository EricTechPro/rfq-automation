# Business Stack Analysis Guide

Common SaaS integrations, their n8n support, and architectural recommendations.

---

## Stack Categories

### E-Commerce Platforms

| Platform | n8n Node | Auth Type | Webhook Support | Recommended Pattern |
|----------|----------|-----------|-----------------|---------------------|
| **Shopify** | `nodes-base.shopify` | OAuth | Yes | Webhook Processing |
| **WooCommerce** | `nodes-base.wooCommerce` | OAuth | Yes | Webhook Processing |
| **BigCommerce** | `nodes-base.bigCommerce` | OAuth | Yes | Webhook Processing |
| **Magento** | HTTP Request | API Key | Yes | HTTP API Integration |
| **Stripe** | `nodes-base.stripe` | API Key | Yes | Webhook Processing |
| **Square** | HTTP Request | OAuth | Yes | HTTP API Integration |

**Common E-commerce Automations:**
1. Order → Fulfillment notification
2. New customer → CRM sync
3. Abandoned cart → Email sequence trigger
4. Inventory update → Multi-channel sync
5. Refund → Support ticket + accounting

**Stack Example: Shopify + Klaviyo + Slack**
```
Verdict: Pure n8n
Rationale:
- All have native nodes
- Standard webhook patterns
- Low data volume per event
- OAuth managed automatically
```

---

### CRM Systems

| Platform | n8n Node | Auth Type | Real-time Sync | Recommended Pattern |
|----------|----------|-----------|----------------|---------------------|
| **HubSpot** | `nodes-base.hubspot` | OAuth | Webhooks | Webhook Processing |
| **Salesforce** | `nodes-base.salesforce` | OAuth | Streaming API | HTTP API Integration |
| **Zoho CRM** | `nodes-base.zohoCrm` | OAuth | Webhooks | Webhook Processing |
| **Pipedrive** | `nodes-base.pipedrive` | API Key | Webhooks | Webhook Processing |
| **Copper** | HTTP Request | API Key | Webhooks | HTTP API Integration |
| **Close** | HTTP Request | API Key | Webhooks | HTTP API Integration |

**Common CRM Automations:**
1. Lead form → CRM + Sales notification
2. Deal stage change → Task creation
3. Contact update → Email list sync
4. Meeting scheduled → Calendar + prep email
5. Deal won → Onboarding workflow trigger

**Stack Example: HubSpot + Typeform + Notion**
```
Verdict: Pure n8n
Rationale:
- HubSpot OAuth handled natively
- Typeform webhook integration
- Notion API for database updates
- Visual workflow for sales team
```

---

### Marketing Automation

| Platform | n8n Node | Auth Type | Bulk Operations | Recommended Pattern |
|----------|----------|-----------|-----------------|---------------------|
| **Mailchimp** | `nodes-base.mailchimp` | OAuth | Yes | Scheduled Tasks |
| **Klaviyo** | `nodes-base.klaviyo` | API Key | Yes | Webhook Processing |
| **ActiveCampaign** | `nodes-base.activeCampaign` | API Key | Yes | HTTP API Integration |
| **Brevo (Sendinblue)** | `nodes-base.sendInBlue` | API Key | Yes | Scheduled Tasks |
| **ConvertKit** | `nodes-base.convertKit` | API Key | Limited | HTTP API Integration |
| **Customer.io** | HTTP Request | API Key | Yes | HTTP API Integration |

**Common Marketing Automations:**
1. New signup → Welcome sequence
2. Purchase → Post-purchase campaign
3. Engagement score → List segmentation
4. Event attendance → Follow-up sequence
5. Cart abandonment → Recovery email

**Stack Example: Klaviyo + Shopify + Google Sheets**
```
Verdict: Pure n8n
Rationale:
- Klaviyo API key auth (simple)
- Shopify webhooks for triggers
- Google Sheets for reporting (OAuth managed)
- No complex processing needed
```

---

### Productivity & Collaboration

| Platform | n8n Node | Auth Type | Real-time | Recommended Pattern |
|----------|----------|-----------|-----------|---------------------|
| **Notion** | `nodes-base.notion` | OAuth | Polling | Database Operations |
| **Airtable** | `nodes-base.airtable` | API Key | Webhooks (paid) | Database Operations |
| **Google Sheets** | `nodes-base.googleSheets` | OAuth | Polling | Database Operations |
| **Coda** | `nodes-base.coda` | API Key | Webhooks | Database Operations |
| **Monday.com** | `nodes-base.mondayCom` | API Key | Webhooks | Webhook Processing |
| **ClickUp** | `nodes-base.clickUp` | OAuth | Webhooks | Webhook Processing |
| **Asana** | `nodes-base.asana` | OAuth | Webhooks | Webhook Processing |

**Common Productivity Automations:**
1. Task completed → Status update + notification
2. Database update → Cross-platform sync
3. Form submission → Task creation
4. Project milestone → Report generation
5. Team assignment → Calendar + notification

**Stack Example: Notion + Slack + Calendar**
```
Verdict: Pure n8n
Rationale:
- Notion OAuth for secure access
- Slack for notifications
- Google Calendar for scheduling
- Standard database sync patterns
```

---

### Communication Platforms

| Platform | n8n Node | Auth Type | Message Handling | Recommended Pattern |
|----------|----------|-----------|------------------|---------------------|
| **Slack** | `nodes-base.slack` | OAuth | Slash commands, Events | Webhook Processing |
| **Discord** | `nodes-base.discord` | OAuth | Webhooks, bots | Webhook Processing |
| **Microsoft Teams** | `nodes-base.microsoftTeams` | OAuth | Webhooks | Webhook Processing |
| **Telegram** | `nodes-base.telegram` | API Token | Webhooks | Webhook Processing |
| **WhatsApp Business** | HTTP Request | API Key | Webhooks | HTTP API Integration |
| **Twilio** | `nodes-base.twilio` | API Key | Webhooks | Webhook Processing |

**Common Communication Automations:**
1. Slash command → Data lookup + response
2. Channel message → Task creation
3. Alert → Multi-channel notification
4. Form submission → Chat notification
5. Scheduled report → Channel post

---

### Support & Service

| Platform | n8n Node | Auth Type | Ticket Management | Recommended Pattern |
|----------|----------|-----------|-------------------|---------------------|
| **Zendesk** | `nodes-base.zendesk` | OAuth | Full | Webhook Processing |
| **Intercom** | `nodes-base.intercom` | OAuth | Full | Webhook Processing |
| **Freshdesk** | `nodes-base.freshdesk` | API Key | Full | Webhook Processing |
| **Help Scout** | HTTP Request | API Key | Full | HTTP API Integration |
| **Crisp** | HTTP Request | API Key | Full | HTTP API Integration |

**Common Support Automations:**
1. New ticket → Priority routing
2. Ticket escalation → Manager notification
3. SLA breach → Alert + auto-escalate
4. Customer feedback → NPS tracking
5. Ticket resolved → Follow-up survey

---

### AI & Analytics

| Platform | n8n Node | Auth Type | Rate Limits | Recommended Pattern |
|----------|----------|-----------|-------------|---------------------|
| **OpenAI** | `nodes-langchain.openAi` | API Key | Yes | AI Agent Workflow |
| **Anthropic** | `nodes-langchain.anthropic` | API Key | Yes | AI Agent Workflow |
| **Google AI** | `nodes-langchain.googleAi` | API Key | Yes | AI Agent Workflow |
| **Pinecone** | HTTP Request | API Key | Yes | AI Agent Workflow |
| **Google Analytics** | `nodes-base.googleAnalytics` | OAuth | Yes | Scheduled Tasks |
| **Mixpanel** | HTTP Request | API Key | Yes | HTTP API Integration |

**Common AI Automations:**
1. Customer inquiry → AI classification + routing
2. Content received → AI summarization
3. Lead form → AI qualification scoring
4. Support ticket → AI response draft
5. Document upload → AI extraction + storage

**Stack Example: OpenAI + HubSpot + Slack**
```
Verdict: Hybrid
Rationale:
- HubSpot/Slack via n8n (OAuth)
- AI processing in Code node or external service
- Complex prompts may need Python for management
- Cost tracking important
```

---

## Multi-Stack Decision Framework

### Analysis Template

When user describes their stack, gather:

```markdown
## Stack Inventory

### Primary Systems (Core Business)
1. [System] - [Role] - [Data Volume]
2. ...

### Secondary Systems (Support Functions)
1. [System] - [Role] - [Frequency]
2. ...

### Integration Points Needed
1. [System A] → [System B]: [Trigger] → [Action]
2. ...

### Data Characteristics
- Records per day: [estimate]
- Peak load: [when]
- Data sensitivity: [PII/financial/standard]

### Team Capabilities
- Technical level: [non-tech/mixed/dev team]
- Maintenance owner: [role]
```

### Complexity Scoring

| Factor | Low (1) | Medium (2) | High (3) |
|--------|---------|------------|----------|
| Number of systems | 2-3 | 4-5 | 6+ |
| OAuth integrations | 0-1 | 2-3 | 4+ |
| Data volume (daily) | < 1000 | 1000-10000 | > 10000 |
| Real-time requirements | None | Some | Critical |
| AI/ML involvement | None | Classification | Generative |
| Maintenance team tech level | Dev team | Mixed | Non-tech |

**Score Interpretation:**
- 6-9: Pure n8n recommended
- 10-14: Hybrid likely needed
- 15-18: Significant Python component required

---

## Common Stack Combinations

### SaaS Startup Stack
**Stripe + HubSpot + Slack + Notion + Intercom**

```
Verdict: Pure n8n
Complexity: Medium
Key Automations:
1. Payment → CRM update + Slack notification
2. New customer → Onboarding workflow
3. Support ticket → Priority routing
4. Churn signal → Retention workflow

Pattern: Multiple webhook-triggered workflows
```

### E-commerce Operations
**Shopify + Klaviyo + ShipStation + QuickBooks**

```
Verdict: Pure n8n (possibly hybrid for inventory)
Complexity: Medium-High
Key Automations:
1. Order → Fulfillment + customer notification
2. Shipment → Tracking update
3. Return → Refund processing
4. Daily → Sales sync to accounting

Pattern: Webhook processing + scheduled sync
Warning: High volume may need batch processing
```

### AI-Powered Service Business
**Typeform + OpenAI + Airtable + Calendly + Zoom**

```
Verdict: Hybrid
Complexity: High
Key Automations:
1. Form → AI analysis → Qualification score
2. Qualified lead → Auto-schedule meeting
3. Meeting → AI summary → CRM update
4. Follow-up → Personalized outreach

Pattern: AI Agent workflow with human checkpoints
Warning: AI costs, need caching strategy
```

### Enterprise Data Pipeline
**Salesforce + Snowflake + Tableau + Slack**

```
Verdict: Python-primary with n8n triggers
Complexity: High
Key Automations:
1. Scheduled → Data extraction
2. Transform → Load to warehouse
3. Anomaly detected → Alert
4. Daily → Report distribution

Pattern: Scheduled tasks + batch processing
Warning: Volume requires Python streaming
```

---

## Integration Gotchas by Platform

### Shopify
- Webhook payload is nested
- Rate limit: 2 calls/second (burst), 40/minute (sustained)
- Consider: Inventory sync can be high volume

### HubSpot
- Association lookups require multiple calls
- Rate limit: 100 calls/10 seconds
- Consider: Property history can bloat payloads

### Salesforce
- SOQL queries have limits
- Bulk API for large operations
- Consider: Streaming API for real-time

### Google Sheets
- 300 requests/minute
- No webhooks (must poll)
- Consider: Use Airtable for real-time needs

### Slack
- Socket mode vs webhooks
- Rate limits vary by endpoint
- Consider: Thread replies for context

### OpenAI/Claude
- Token costs add up quickly
- Rate limits by tier
- Consider: Caching, model selection

---

## Related Skills

- **n8n-node-configuration** - Configure specific platform nodes
- **n8n-workflow-patterns** - Implementation patterns
- **n8n-mcp-tools-expert** - Find platform-specific nodes
