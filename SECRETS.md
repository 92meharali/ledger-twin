# Ledger Twin — Keys & Secrets (with direct links)

Copy `.env.example` → `.env`, then fill each value below. **Never commit `.env`.**

---

## Required for the hackathon build

### 1. Anthropic (Claude) — agent reasoning
| Env var | What it is |
|---|---|
| `ANTHROPIC_API_KEY` | API key for Claude |
| `ANTHROPIC_MODEL` | Model id (default in `.env.example` is fine) |

**Get it here:** https://console.anthropic.com/settings/keys

---

### 2. Stripe (Test Mode) — payments & webhooks
| Env var | What it is |
|---|---|
| `STRIPE_SECRET_KEY` | Test secret key (`sk_test_…`) |
| `STRIPE_PUBLISHABLE_KEY` | Test publishable key (`pk_test_…`) |
| `STRIPE_WEBHOOK_SECRET` | Signing secret for your webhook endpoint (`whsec_…`) |

**Get API keys:** https://dashboard.stripe.com/test/apikeys  
**Create webhook endpoint:** https://dashboard.stripe.com/test/webhooks  

Webhook URL (after you have a public URL):  
`{PUBLIC_BASE_URL}/webhooks/stripe`  

Events to subscribe: `payment_intent.succeeded`, `invoice.paid`

---

### 3. Airtable — canonical ledger
| Env var | What it is |
|---|---|
| `AIRTABLE_API_KEY` | Personal Access Token (`pat…`) |
| `AIRTABLE_BASE_ID` | Base id (`app…`) from the base URL |

**Create token:** https://airtable.com/create/tokens  
Scopes needed: `data.records:read`, `data.records:write`, `schema.bases:read` (limit to your base).  

**Open / create a base:** https://airtable.com/  

Tables to create: `Clients`, `Invoices`, `Payments`, `EventLog`

---

### 4. Slack — human-in-the-loop approvals
| Env var | What it is |
|---|---|
| `SLACK_BOT_TOKEN` | Bot User OAuth Token (`xoxb-…`) |
| `SLACK_SIGNING_SECRET` | App signing secret (verify interactivity) |
| `SLACK_CHANNEL_ID` | Channel id where approval cards post (`C…`) |

**Create / manage apps:** https://api.slack.com/apps  

In your app:
1. **OAuth & Permissions** → Bot Token Scopes → add `chat:write` → Install to workspace  
2. **Basic Information** → App Credentials → copy **Signing Secret**  
3. **Interactivity & Shortcuts** → enable → Request URL: `{PUBLIC_BASE_URL}/webhooks/slack/interact`  

**Find a channel ID:** open the channel in Slack → channel details → copy Channel ID  
(or right-click channel → View channel details)

---

### 5. Axiom — agent observability
| Env var | What it is |
|---|---|
| `AXIOM_TOKEN` | API token with **ingest** permission (`xaat-…`) |
| `AXIOM_DATASET` | Dataset name (e.g. `ledger-twin`) |
| `AXIOM_ORG_ID` | Only if using a personal token (optional for API tokens) |
| `AXIOM_EDGE` | Optional region edge host |

**Sign up / console:** https://app.axiom.co/  
**API tokens:** https://app.axiom.co/settings/api-tokens  
**Datasets:** https://app.axiom.co/datasets  

Create a dataset named `ledger-twin`, then create an API token with ingest access to that dataset.

Docs (ingest): https://axiom.co/docs/restapi/ingest

---

### 6. Temp mail (mail.tm) — disposable payment inbox
No vendor API key. You create an inbox, then store its credentials.

| Env var | What it is |
|---|---|
| `TEMP_MAIL_API_BASE` | `https://api.mail.tm` (default) |
| `TEMP_MAIL_ADDRESS` | e.g. `ledgerdemo@<domain from /domains>` |
| `TEMP_MAIL_PASSWORD` | Password you chose at account create |
| `TEMP_MAIL_TOKEN` | Bearer token from `POST /token` (app can refresh) |

**Docs / API:** https://docs.mail.tm/  
**OpenAPI:** https://docs.mail.tm/openapi.yml  

Quick create (terminal):

```bash
# 1) list domains
curl https://api.mail.tm/domains

# 2) create account (use a domain from step 1)
curl -X POST https://api.mail.tm/accounts \
  -H 'Content-Type: application/json' \
  -d '{"address":"YOURNAME@DOMAIN","password":"YOUR_PASSWORD"}'

# 3) get token
curl -X POST https://api.mail.tm/token \
  -H 'Content-Type: application/json' \
  -d '{"address":"YOURNAME@DOMAIN","password":"YOUR_PASSWORD"}'
```

Paste `address`, `password`, and `token` into `.env`.

---

### 7. Public URL (required for Stripe + Slack callbacks)
| Env var | What it is |
|---|---|
| `PUBLIC_BASE_URL` | HTTPS URL reachable from the internet |

**ngrok download:** https://ngrok.com/download  
**ngrok dashboard / auth token:** https://dashboard.ngrok.com/get-started/your-authtoken  

```bash
ngrok http 8000
# set PUBLIC_BASE_URL to the https://….ngrok-free.app URL
```

---

## Optional (not required for tickets 01–04)

### Gmail (optional polish — receipts / real inbox)
| Env var | What it is |
|---|---|
| `GOOGLE_CLIENT_ID` | OAuth client id |
| `GOOGLE_CLIENT_SECRET` | OAuth client secret |
| `GOOGLE_REFRESH_TOKEN` | Refresh token after OAuth consent |
| `GMAIL_USER` | Usually `me` |

**Google Cloud Console:** https://console.cloud.google.com/  
**Enable Gmail API:** https://console.cloud.google.com/apis/library/gmail.googleapis.com  
**Credentials (OAuth client):** https://console.cloud.google.com/apis/credentials  

Temp mail covers the email path for the hackathon demo — do Gmail only if you have spare time.

---

## Minimum checklist (copy/paste)

- [ ] https://console.anthropic.com/settings/keys → `ANTHROPIC_API_KEY`
- [ ] https://dashboard.stripe.com/test/apikeys → `STRIPE_SECRET_KEY` + `STRIPE_PUBLISHABLE_KEY`
- [ ] https://dashboard.stripe.com/test/webhooks → `STRIPE_WEBHOOK_SECRET`
- [ ] https://airtable.com/create/tokens → `AIRTABLE_API_KEY` + base → `AIRTABLE_BASE_ID`
- [ ] https://api.slack.com/apps → `SLACK_BOT_TOKEN` + `SLACK_SIGNING_SECRET` + `SLACK_CHANNEL_ID`
- [ ] https://app.axiom.co/settings/api-tokens → `AXIOM_TOKEN` + dataset → `AXIOM_DATASET`
- [ ] https://docs.mail.tm/ → create inbox → `TEMP_MAIL_*`
- [ ] https://dashboard.ngrok.com/get-started/your-authtoken → run ngrok → `PUBLIC_BASE_URL`
