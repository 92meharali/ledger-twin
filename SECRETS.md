# Ledger Twin — Keys & Secrets (with direct links)

Copy `.env.example` → `.env`, then fill each value below. **Never commit `.env`.**

---

## Required for the hackathon build

### 1. OpenAI (LLM) — agent reasoning
| Env var | What it is |
|---|---|
| `LLM_PROVIDER` | Set to `openai` |
| `OPENAI_API_KEY` | OpenAI API key (`sk-proj-…` or `sk-…`) |
| `OPENAI_MODEL` | e.g. `gpt-4o-mini` |

**Get it here:** https://platform.openai.com/api-keys  

(Groq / Anthropic in `.env.example` are optional fallbacks — **not required**.)

---

### 2. Stripe (Test Mode) — payments & webhooks
| Env var | What it is |
|---|---|
| `STRIPE_SECRET_KEY` | Test secret key (`sk_test_…`) |
| `STRIPE_PUBLISHABLE_KEY` | Test publishable key (`pk_test_…`) |
| `STRIPE_WEBHOOK_SECRET` | Signing secret — **get later via Stripe CLI** (`whsec_…`) |

**Get API keys:** https://dashboard.stripe.com/test/apikeys  

**Webhook:** skip the Dashboard endpoint for now. After the app runs:

```bash
stripe listen --forward-to localhost:8000/webhooks/stripe
```

Paste the printed `whsec_…` into `STRIPE_WEBHOOK_SECRET`.

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
| `SLACK_APP_TOKEN` | App-Level Token (`xapp-…`) — **Socket Mode for local Approve buttons** |

**Create / manage apps:** https://api.slack.com/apps  

In your app:
1. **OAuth & Permissions** → Bot Token Scopes → add `chat:write` → Install to workspace  
2. **Basic Information** → App Credentials → copy **Signing Secret**  
3. **Basic Information** → App-Level Tokens → Generate → scope `connections:write` → copy `xapp-…`  
4. **Socket Mode** → Enable  
5. **Interactivity & Shortcuts** → Enable (Request URL not required when Socket Mode is on)  

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

- [x] https://platform.openai.com/api-keys → `OPENAI_API_KEY` (+ `LLM_PROVIDER=openai`)
- [x] https://dashboard.stripe.com/test/apikeys → `STRIPE_SECRET_KEY` + `STRIPE_PUBLISHABLE_KEY`
- [ ] `STRIPE_WEBHOOK_SECRET` — later via `stripe listen` (not needed yet)
- [x] Airtable → `AIRTABLE_API_KEY` + `AIRTABLE_BASE_ID=apphXdxfzsOQ2a4G2`
- [x] Axiom → `AXIOM_TOKEN` + `AXIOM_DATASET=ledger-twin` + `AXIOM_EDGE=us-east-1.aws.edge.axiom.co`
- [x] https://api.slack.com/apps → Slack bot token + signing secret + channel
- [ ] https://docs.mail.tm/ → temp mail (ticket 03)
- [ ] Public URL / ngrok — optional if using Stripe CLI locally
