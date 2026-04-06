# 2. Lovable Prompt

You are designing and generating a **premium B2B SaaS frontend** for a closed-source product forked from Webly.

Product name: **Webly Cloud** (placeholder, can refine).  
Core product: businesses create and manage **website-grounded AI chatbots**.  
This is not a Streamlit app. This should look launch-ready for serious companies.

## Product framing
Build the frontend for this product story:
- Business signs up
- Creates workspace + project (chatbot)
- Connects website source(s)
- Configures crawl/index behavior
- Runs async indexing jobs
- Monitors job status/health
- Tests bot in playground
- Customizes bot behavior + branding
- Publishes deployment
- Copies embed snippet to install on website
- Monitors analytics, usage, team, billing

Audience:
- Customer success teams
- Product/operations managers
- Non-technical admins
- Technical implementers for setup/install

Brand personality:
- Calm, credible, precise, trustworthy
- Helpful but non-hypey
- “Operational AI platform”, not consumer chatbot toy

## Visual direction (must-follow)
- Premium B2B SaaS aesthetic
- Modern, clean, restrained
- No hackathon style
- No Streamlit-like layout
- No neon gradients or gimmicky AI imagery
- No cluttered developer-console feeling

## Design system (concrete tokens)
Use these tokens consistently:
- Primary: `#1D4ED8` (Blue 700)
- Secondary: `#0F766E` (Teal 700)
- Accent: `#7C3AED` (Violet 600, sparing use)
- Success: `#15803D`
- Warning: `#B45309`
- Error: `#B91C1C`
- Background: `#F8FAFC`
- Surface/Card: `#FFFFFF`
- Border: `#E2E8F0`
- Text Primary: `#0F172A`
- Text Secondary: `#475569`

Typography:
- Headings: `Manrope` (600/700)
- Body/UI: `Inter` (400/500)
- Monospace (snippets/logs): `JetBrains Mono`

UI foundation:
- Radius: 10px cards, 8px inputs/buttons, 12px modals
- Shadow: subtle (`0 1px 2px rgba(15,23,42,.06)`, `0 8px 24px rgba(15,23,42,.08)` for overlays)
- Spacing scale: 4/8/12/16/24/32/40/48
- Icon set: clean line icons (Lucide or equivalent)
- Density: medium-compact (enterprise dashboard friendly)

## Information architecture
Create a complete multi-page app with:
1. Public marketing site
2. Auth pages
3. Logged-in SaaS app

### Public marketing site (required)
- Landing
- Features
- Pricing
- FAQ
- Login / Signup
- Footer with Contact Sales CTA and legal links

Landing sections:
- Hero with clear value prop
- Trust section (security/reliability)
- “How it works” (Connect → Index → Test → Deploy)
- Feature grid
- Product screenshot strip
- CTA block (start free trial / book demo)

## Logged-in SaaS app pages (required)
- Dashboard
- Projects/Chatbots list
- Create Project wizard
- Source setup
- Crawl/Index configuration
- Index Jobs / Status timeline page
- Playground chat page
- Chatbot behavior config (prompt modes/retrieval controls)
- Branding customization page
- Embed/Install page
- Analytics pages
- Usage/Billing page
- Workspace/Team/Settings page
- Audit logs page

## Core happy path UX (must be explicit in UI)
1. Sign up
2. Create workspace
3. Create first project
4. Add website source
5. Configure crawl policy
6. Launch indexing job
7. Watch job progress and status transitions
8. Open playground and test questions
9. Tune chatbot behavior/branding
10. Publish deployment
11. Copy embed snippet
12. Monitor analytics and usage

## Backend contract to design against
Design frontend data flows around these endpoints (use realistic mock service layer):
- Auth: `/v1/auth/*`
- Workspaces/team: `/v1/workspaces`, `/v1/workspaces/:id/members`, `/v1/workspaces/:id/invitations`
- Projects: `/v1/workspaces/:id/projects`, `/v1/projects/:id`
- Sources: `/v1/projects/:id/sources`, `/verify`, `/preview-urls`
- Ingestion config: `/v1/projects/:id/ingestion-config`
- Jobs: `/v1/projects/:id/index-jobs`, `/:jobId`, `/:jobId/events`, `/:jobId/logs`
- Index versions: `/v1/projects/:id/index-versions`
- Chatbot config: `/v1/projects/:id/chatbot-config`
- Playground/query: `/v1/projects/:id/playground/query`, `/query-stream`, `/retrieve`
- Conversations/messages: `/v1/projects/:id/conversations`, `/messages`, `/feedback`
- Deploy/embed: `/v1/projects/:id/deployments`, `/publish`, `/embed-snippet`
- Analytics: `/v1/projects/:id/analytics/*`
- Usage/billing: `/v1/workspaces/:id/usage`, `/billing`, `/invoices`
- Settings/secrets/webhooks: `/v1/workspaces/:id/settings`, `/secrets`, `/webhooks`

## Domain-specific UI behavior to support
Mirror Webly-style controls, but production quality:
- Crawl controls: `start_url`, `allowed_domains`, `allow_subdomains`, `respect_robots`, `max_depth`, `rate_limit_delay`, `allowed_paths`, `blocked_paths`, regex allow/block patterns, `seed_urls`, crawl scope
- Indexing controls: chunk size/overlap, summarization model + prompt, embedding model/provider
- Chatbot controls: answering mode, prompt override, retrieval mode (`classic` vs `builder`), builder rounds, memory window
- Job run modes: `crawl_only`, `index_only`, `both`, and `force_recrawl`

## UX quality requirements (non-negotiable)
- Strong onboarding and first-run guidance
- Excellent empty states for no projects/no sources/no index/no conversations
- Loading skeletons on table/card-heavy pages
- Explicit progress states and stage labels for jobs
- Retry and cancel actions for failed/running jobs
- Safe destructive confirmations (delete project/source/deployment)
- Clear toasts/alerts for success, warning, failure
- Friendly but precise error copy
- Source-grounding trust indicators in playground answers (`supported`, source URLs/chunks)
- Quota usage banners and near-limit warnings

## Analytics and operational visibility
Include real dashboard widgets for:
- Total conversations
- Questions per day/week
- Helpful vs unhelpful ratio
- Unanswered question count
- Top questions
- Crawl/index health (pages crawled, indexed pages, crawl errors)
- Freshness (`last indexed at`)
- Latency trends
- Plan usage trends (requests, indexed pages, storage)

## Embed/install experience
Install page must include:
- Deployment status
- Environment selector (staging/prod)
- Domain allowlist editor
- Generated script snippet
- Copy-to-clipboard
- Framework-agnostic install instructions
- Widget preview panel
- Theme controls (primary color, welcome message, launcher style)

## Copywriting style
- Concise
- Premium
- Calm
- Human
- Useful
- No exaggerated AI claims
- No buzzword-heavy hype

## Technical frontend output requirements
Generate:
- A realistic, multi-page responsive SaaS frontend
- Reusable component system
- Clean forms/tables/cards
- Tabs, drawers, modals, toasts
- Empty/loading/error/success states everywhere needed
- Realistic charts and KPI cards
- Route-level layouts with clear navigation
- Mock API layer aligned to endpoint contract above
- Credible UI that looks ready for investor/customer demos

Important constraints:
- This is a **business SaaS**, not a consumer chat app
- Trust and operational clarity are core
- Must serve non-technical admins and power users
- Must feel scalable into enterprise maturity (team, billing, analytics, security)

Now generate the full frontend experience accordingly.
