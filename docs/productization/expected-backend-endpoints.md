# 1. Expected Backend Endpoints

## API shape assumptions
- Base path: `/v1`
- Auth: JWT access token + refresh token
- Multi-tenant scope: every project belongs to a workspace
- IDs: `ws_`, `prj_`, `src_`, `job_`, `bot_`, `conv_`, `msg_`, `dep_`
- Time format: ISO-8601 UTC
- Pagination: `?cursor=&limit=` with `{items, next_cursor}`
- Async jobs return `202 Accepted` + `job_id`
- Streaming query support via SSE/WebSocket for playground and live widget

## Suggested resource model (grounded in Webly’s current architecture)
- `Workspace`: tenant boundary, billing, members
- `User`: identity + workspace roles
- `Project`: one chatbot knowledge base (maps to Webly project folder concept)
- `Source`: website ingestion source with crawl policy (`start_url`, domains, patterns, robots, depth, seeds)
- `IngestionConfig`: chunking/summarization/embedding/index controls
- `IndexJob`: async crawl/index pipeline run (`crawl_only | index_only | both`, force recrawl)
- `IndexVersion`: immutable index artifact + metadata snapshot
- `ChatbotConfig`: answer behavior, prompt policy, retrieval mode (`classic|builder`), memory window
- `Conversation` + `Message`: playground and optionally production transcript storage
- `Deployment`: embeddable bot runtime config + domain restrictions + snippet
- `AnalyticsEvent` aggregates: question quality, usage, pipeline health
- `Plan/Usage`: quotas and billing state

## Job lifecycle states (index jobs)
- `queued`
- `validating_config`
- `crawling`
- `processing`
- `chunking`
- `summarizing`
- `embedding`
- `indexing`
- `finalizing`
- `completed`
- `failed`
- `canceled`
- `completed_with_warnings`

Each job should expose:
- `status`
- `current_stage`
- `progress_pct`
- `counts` (`pages_seen`, `pages_saved`, `chunks`, `segments`, `errors`)
- `warnings` (robots blocked, disallowed domain, empty results)
- `error_code`, `error_message`
- `started_at`, `finished_at`

## Sync vs async expectations
- Synchronous: auth, CRUD, config reads/writes, embed snippet retrieval, analytics reads, usage reads
- Asynchronous: crawl/index runs, reindex schedules, large exports, webhook test deliveries
- Frontend polling needs: job status endpoint, job events/log endpoint, deployment status endpoint

## Persisted state that backend must own
- Workspace/member/billing data
- Project/source/config/versioned settings
- Crawl outputs summary + index versions
- Chatbot config + branding + deployment config
- Conversations/messages + feedback labels
- Analytics aggregates + raw event counters
- API keys/secrets/webhook secrets (encrypted at rest)

---

## Auth

| Method | Path | Purpose | Main request | Main response | Why this exists (Webly grounding) |
|---|---|---|---|---|---|
| POST | `/auth/signup` | Create account | `{name,email,password}` | `{user, workspace, access_token, refresh_token}` | Webly is local; SaaS needs tenant bootstrap. |
| POST | `/auth/login` | Login | `{email,password}` | `{access_token,refresh_token,user}` | Required for non-Streamlit SaaS sessions. |
| POST | `/auth/refresh` | Refresh token | `{refresh_token}` | `{access_token}` | Long-lived dashboard sessions. |
| POST | `/auth/logout` | Revoke refresh token | `{refresh_token}` | `{ok:true}` | Session hygiene. |
| GET | `/auth/me` | Current user profile | none | `{user, memberships[]}` | Needed for workspace switcher and role-based UI. |
| POST | `/auth/forgot-password` | Start reset | `{email}` | `{ok:true}` | Production account recovery. |
| POST | `/auth/reset-password` | Complete reset | `{token,new_password}` | `{ok:true}` | Production auth baseline. |
| GET | `/auth/sso/providers` | List enabled SSO | none | `{providers:[...]}` | B2B enterprise readiness. |
| POST | `/auth/sso/saml/callback` | SSO callback | provider payload | `{access_token,refresh_token}` | Enterprise customers. |

## Workspaces & Team

| Method | Path | Purpose | Main request | Main response | Why |
|---|---|---|---|---|---|
| GET | `/workspaces` | List accessible workspaces | query pagination | `{items:[workspace],next_cursor}` | Multi-workspace UX. |
| POST | `/workspaces` | Create workspace | `{name}` | `{workspace}` | Team separation + billing unit. |
| GET | `/workspaces/:workspaceId` | Workspace detail | none | `{workspace,plan,usage_snapshot}` | Dashboard context. |
| PATCH | `/workspaces/:workspaceId` | Update workspace | `{name,logo_url,timezone}` | `{workspace}` | Admin settings. |
| DELETE | `/workspaces/:workspaceId` | Soft delete workspace | `{confirm_name}` | `{ok:true}` | Safe destructive action. |
| GET | `/workspaces/:workspaceId/members` | List members | pagination | `{items:[member]}` | Team management. |
| POST | `/workspaces/:workspaceId/invitations` | Invite member | `{email,role}` | `{invitation}` | B2B onboarding. |
| PATCH | `/workspaces/:workspaceId/members/:memberId` | Change role | `{role}` | `{member}` | RBAC. |
| DELETE | `/workspaces/:workspaceId/members/:memberId` | Remove member | none | `{ok:true}` | Access control. |
| GET | `/workspaces/:workspaceId/audit-logs` | Org audit trail | filters | `{items:[event]}` | Enterprise trust/compliance. |

## Projects (chatbots)

| Method | Path | Purpose | Main request | Main response | Why |
|---|---|---|---|---|---|
| GET | `/workspaces/:workspaceId/projects` | List projects | pagination/filter | `{items:[project]}` | Webly “projects” become first-class SaaS objects. |
| POST | `/workspaces/:workspaceId/projects` | Create project | `{name,description}` | `{project}` | Start chatbot creation flow. |
| GET | `/projects/:projectId` | Project detail | none | `{project,health}` | Main app shell data. |
| PATCH | `/projects/:projectId` | Update project meta | `{name,description,status}` | `{project}` | Rename/archive controls. |
| DELETE | `/projects/:projectId` | Soft delete project | `{confirm_name}` | `{ok:true}` | Data safety. |
| POST | `/projects/:projectId/archive` | Archive | none | `{project}` | Lifecycle control. |
| POST | `/projects/:projectId/unarchive` | Unarchive | none | `{project}` | Recovery. |

## Website Sources

| Method | Path | Purpose | Main request | Main response | Why |
|---|---|---|---|---|---|
| GET | `/projects/:projectId/sources` | List configured sources | none | `{items:[source]}` | Webly currently assumes one source; SaaS should support many. |
| POST | `/projects/:projectId/sources` | Add website source | `{type:"website",start_url,allowed_domains[]}` | `{source}` | Mirrors Webly start URL + domain model. |
| GET | `/projects/:projectId/sources/:sourceId` | Source detail | none | `{source}` | Source setup page. |
| PATCH | `/projects/:projectId/sources/:sourceId` | Update crawl source config | `start_url, allowed_domains, allow_subdomains, respect_robots, max_depth, rate_limit_delay, allowed_paths, blocked_paths, allow_url_patterns, block_url_patterns, seed_urls, crawl_entire_site` | `{source}` | Direct map from Atlas/BaseAgent config surface. |
| DELETE | `/projects/:projectId/sources/:sourceId` | Remove source | none | `{ok:true}` | Source lifecycle. |
| POST | `/projects/:projectId/sources/:sourceId/verify` | Validate reachability + policy sanity | optional test URL | `{reachable,robots_ok,domain_match,warnings[]}` | Prevent empty crawls before jobs. |
| GET | `/projects/:projectId/sources/:sourceId/preview-urls` | Preview URL inclusion/exclusion | none | `{included[],excluded[]}` | Explain allow/block patterns before running jobs. |

## Ingestion & Index Config

| Method | Path | Purpose | Main request | Main response | Why |
|---|---|---|---|---|---|
| GET | `/projects/:projectId/ingestion-config` | Read ingest settings | none | `{config}` | UI settings form hydration. |
| PATCH | `/projects/:projectId/ingestion-config` | Update ingest settings | `{chunker:{type,max_words,overlap}, summarization:{enabled,model,prompt_template,max_input_chars}, embedding:{provider,model}, indexing:{index_backend:"faiss",index_type}, debug:{save_raw_chunks,save_summaries}}` | `{config}` | Grounded in Webly chunker/summarizer/embed/index behavior. |
| POST | `/projects/:projectId/ingestion-config/validate` | Validate config for runability | `{config?}` | `{valid,errors[],warnings[]}` | Catch model/API issues early. |

## Crawl / Index Jobs

| Method | Path | Purpose | Main request | Main response | Why |
|---|---|---|---|---|---|
| POST | `/projects/:projectId/index-jobs` | Start job | `{mode:"both|crawl_only|index_only", source_ids[], force_recrawl:boolean, config_override?}` | `202 {job_id,status:"queued"}` | Mirrors `IngestPipeline.run()` modes directly. |
| GET | `/projects/:projectId/index-jobs` | List jobs | filters/pagination | `{items:[job]}` | Jobs table/history UI. |
| GET | `/projects/:projectId/index-jobs/:jobId` | Job status detail | none | `{job}` | Polling target for progress UI. |
| GET | `/projects/:projectId/index-jobs/:jobId/events` | Stage/event stream | cursor | `{items:[event],next_cursor}` | Timeline + troubleshooting. |
| GET | `/projects/:projectId/index-jobs/:jobId/logs` | Human-readable logs | level filter | `{items:[log_line]}` | Operational debugging (crawl failures, model errors). |
| POST | `/projects/:projectId/index-jobs/:jobId/cancel` | Cancel running job | none | `{job}` | Safe cancellation. |
| POST | `/projects/:projectId/index-jobs/:jobId/retry` | Retry with same config | optional overrides | `202 {job_id}` | Common failed-job action. |
| GET | `/projects/:projectId/index-jobs/:jobId/report` | Run summary | none | `{summary, warnings, disallowed_reasons, output_metrics}` | Webly already creates disallowed report/debug artifacts. |

## Index Versions

| Method | Path | Purpose | Main request | Main response | Why |
|---|---|---|---|---|---|
| GET | `/projects/:projectId/index-versions` | List index artifacts | none | `{items:[index_version],active_version_id}` | Production rollbacks and freshness tracking. |
| POST | `/projects/:projectId/index-versions/:versionId/activate` | Switch active index | none | `{active_version_id}` | Zero-downtime rollback after bad ingest. |
| DELETE | `/projects/:projectId/index-versions/:versionId` | Delete old version | none | `{ok:true}` | Storage control. |

## Chatbot Config & Branding

| Method | Path | Purpose | Main request | Main response | Why |
|---|---|---|---|---|---|
| GET | `/projects/:projectId/chatbot-config` | Read bot behavior config | none | `{config}` | Playground and deployment settings. |
| PATCH | `/projects/:projectId/chatbot-config` | Update bot behavior | `{chat_model,answering_mode,system_prompt,system_prompt_custom_override,allow_generated_examples,retrieval_mode,builder_max_rounds,leave_last_k}` | `{config}` | Maps to Webly prompt/retrieval knobs. |
| GET | `/projects/:projectId/branding` | Read widget branding | none | `{branding}` | SaaS customization surface. |
| PATCH | `/projects/:projectId/branding` | Update branding | `{bot_name,logo_url,primary_color,border_radius,launcher_icon,welcome_message}` | `{branding}` | Embed/widget personalization. |

## Playground / Querying

| Method | Path | Purpose | Main request | Main response | Why |
|---|---|---|---|---|---|
| POST | `/projects/:projectId/playground/query` | Single-turn test query | `{query,memory_context?,conversation_id?,options:{retrieval_mode_override?,debug?}}` | `{answer,supported,sources[],latency_ms,retrieval_trace?}` | Mirrors QueryPipeline + support flag behavior. |
| POST | `/projects/:projectId/playground/query-stream` | Streaming test query | same as above | SSE tokens + final payload | Better UX for longer answers. |
| POST | `/projects/:projectId/playground/retrieve` | Retrieval-only debug | `{query,top_k}` | `{results:[{chunk_id,url,score,hierarchy,snippet}]}` | Quality tuning for grounding. |
| POST | `/projects/:projectId/playground/rewrite` | Show rewrite/follow-up plan | `{query,memory_context?}` | `{route,rewrites,concepts}` | Exposes builder logic for trust/debug. |

## Conversations / Chat History / Feedback

| Method | Path | Purpose | Main request | Main response | Why |
|---|---|---|---|---|---|
| GET | `/projects/:projectId/conversations` | List conversations | pagination/filter | `{items:[conversation]}` | Replaces local JSON chat files with API-backed history. |
| POST | `/projects/:projectId/conversations` | Create conversation | `{title?,channel:"playground|widget"}` | `{conversation}` | Chat session creation. |
| GET | `/projects/:projectId/conversations/:conversationId` | Conversation detail | none | `{conversation,messages[]}` | Inspector panel. |
| PATCH | `/projects/:projectId/conversations/:conversationId` | Update title/meta | `{title,archived}` | `{conversation}` | Chat management. |
| DELETE | `/projects/:projectId/conversations/:conversationId` | Delete conversation | none | `{ok:true}` | Privacy + cleanup. |
| POST | `/projects/:projectId/conversations/:conversationId/messages` | Add user message and get answer | `{content,stream?:boolean}` | `{user_message,assistant_message,sources[]}` | Core persisted chat flow. |
| POST | `/projects/:projectId/conversations/:conversationId/memory/reset` | Reset memory marker | none | `{conversation}` | Equivalent to Webly “clear memory” behavior. |
| POST | `/projects/:projectId/messages/:messageId/feedback` | Helpful/unhelpful signal | `{rating:"helpful|unhelpful",reason?,comment?}` | `{ok:true}` | Needed for quality analytics loop. |

## Embed / Deployment

| Method | Path | Purpose | Main request | Main response | Why |
|---|---|---|---|---|---|
| GET | `/projects/:projectId/deployments` | List deployment environments | none | `{items:[deployment]}` | Staging/prod control. |
| POST | `/projects/:projectId/deployments` | Create deployment | `{name,environment,domain_allowlist[]}` | `{deployment}` | Production publish model. |
| PATCH | `/projects/:projectId/deployments/:deploymentId` | Update deployment config | `{domain_allowlist,rate_limits,widget_config_snapshot}` | `{deployment}` | Runtime safety + restrictions. |
| POST | `/projects/:projectId/deployments/:deploymentId/publish` | Publish current config/index | none | `{deployment,status}` | Explicit launch action. |
| GET | `/projects/:projectId/deployments/:deploymentId/embed-snippet` | Retrieve JS snippet | none | `{script_tag,init_payload}` | Install page primary output. |
| POST | `/projects/:projectId/deployments/:deploymentId/rotate-public-key` | Rotate widget key | none | `{public_key}` | Security incident response. |
| POST | `/widget/events` | Public widget ingest endpoint | `{deployment_key,conversation_id?,event}` | `{ok:true}` | Captures production chat usage/analytics. |
| POST | `/widget/query` | Public widget query endpoint | `{deployment_key,conversation_id,query}` | `{answer,sources[]}` | Live customer-facing chatbot runtime. |

## Analytics

| Method | Path | Purpose | Main request | Main response | Why |
|---|---|---|---|---|---|
| GET | `/projects/:projectId/analytics/overview` | KPI summary | `from,to` | `{conversations,questions,helpful_rate,unanswered_rate,avg_latency,last_indexed_at}` | Core dashboard. |
| GET | `/projects/:projectId/analytics/questions/top` | Top asked questions | `from,to,limit` | `{items:[{question,count,helpful_rate}]}` | Product insight. |
| GET | `/projects/:projectId/analytics/questions/unanswered` | Missed intents | filters | `{items:[{question,count,suggested_source_gap}]}` | Drives recrawl/reindex priorities. |
| GET | `/projects/:projectId/analytics/sources` | Source/index coverage | none | `{pages_crawled,pages_indexed,chunks,segments,crawl_errors[]}` | Grounded in ingest metrics. |
| GET | `/projects/:projectId/analytics/quality` | Response quality trends | `from,to` | `{helpful_vs_unhelpful,unsupported_answers,retrieval_mode_split}` | Tune builder/classic behavior. |
| GET | `/projects/:projectId/analytics/usage-trends` | Time-series usage | granularity | `{series:[...]} ` | Operational planning. |

## Usage / Billing

| Method | Path | Purpose | Main request | Main response | Why |
|---|---|---|---|---|---|
| GET | `/workspaces/:workspaceId/usage` | Quota and current usage | none | `{plan,limits,usage,percent_used}` | Show remaining capacity. |
| GET | `/workspaces/:workspaceId/billing` | Billing summary | none | `{plan,status,renewal_date,payment_method}` | Billing page. |
| GET | `/workspaces/:workspaceId/billing/invoices` | Invoice history | pagination | `{items:[invoice]}` | Finance workflow. |
| POST | `/workspaces/:workspaceId/billing/checkout-session` | Upgrade/downgrade flow | `{target_plan}` | `{checkout_url}` | SaaS monetization. |
| POST | `/workspaces/:workspaceId/billing/portal-session` | Manage subscription | none | `{portal_url}` | Self-service billing. |
| GET | `/workspaces/:workspaceId/billing/usage-events` | Raw usage line items | filters | `{items:[usage_event]}` | Debug plan disputes. |

## Webhooks / Integrations

| Method | Path | Purpose | Main request | Main response | Why |
|---|---|---|---|---|---|
| GET | `/workspaces/:workspaceId/webhooks` | List webhook endpoints | none | `{items:[webhook]}` | Ops integrations. |
| POST | `/workspaces/:workspaceId/webhooks` | Create webhook | `{url,events[],secret?}` | `{webhook}` | Push job/usage events to customer systems. |
| PATCH | `/workspaces/:workspaceId/webhooks/:webhookId` | Update webhook | `{events,active}` | `{webhook}` | Integration management. |
| DELETE | `/workspaces/:workspaceId/webhooks/:webhookId` | Delete webhook | none | `{ok:true}` | Cleanup. |
| POST | `/workspaces/:workspaceId/webhooks/:webhookId/test` | Send test event | none | `{delivery_result}` | Validate setup in UI. |

Recommended webhook events:
- `index_job.completed`
- `index_job.failed`
- `index_job.completed_with_warnings`
- `usage.threshold_reached`
- `billing.payment_failed`
- `deployment.published`

## Settings / Secrets

| Method | Path | Purpose | Main request | Main response | Why |
|---|---|---|---|---|---|
| GET | `/workspaces/:workspaceId/settings` | Workspace settings | none | `{settings}` | Retention/security defaults. |
| PATCH | `/workspaces/:workspaceId/settings` | Update settings | `{data_retention_days,default_locale,security_flags}` | `{settings}` | Enterprise controls. |
| GET | `/workspaces/:workspaceId/secrets` | List masked secrets | none | `{items:[{id,type,masked_value}]}` | Model/provider credential mgmt. |
| POST | `/workspaces/:workspaceId/secrets` | Add secret | `{type,value,label}` | `{secret_id}` | Needed for OpenAI and future providers. |
| DELETE | `/workspaces/:workspaceId/secrets/:secretId` | Revoke secret | none | `{ok:true}` | Rotation/revocation. |

---

## Major frontend polling/fetch/mutate map
- Poll: `GET /projects/:id/index-jobs/:jobId`, `/events`, `/logs`
- Mutate: source config, ingestion config, chatbot config, branding, deployments
- Fetch for dashboards: analytics overview + usage + recent jobs + project health
- Query path: playground query endpoints and conversation message endpoints
- Install path: deployment publish + embed snippet + domain restrictions
