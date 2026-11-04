# Language, OCR, and Web IQ assessment

## Findings

The mixed-language display had four independent causes:

1. The frontend accepted only `en` and `fr`; any other locale fell back to English.
2. Several vision and analysis prompts explicitly required French, even when the API
   received an English display locale.
3. reconstructed application titles used French claim prefixes.
4. OCR text, extracted values, derived summaries, and UI labels were treated as one
   display layer.

The last point is the most important distinction. OCR and source text are evidence and
must remain faithful to the source document. Translating that evidence in place would
make citations and human review unreliable. User-facing labels, reconstructed titles,
agent answers, image descriptions, and analysis fields can and should follow the
requested display language.

## Implemented language contract

- Supported locale codes are `en`, `fr`, and `de`.
- Regional locale codes are normalized to their supported base language; unsupported API locales are rejected explicitly.
- The frontend sends its locale to analysis, chat, and workflow endpoints.
- Workflow, chat, vision, underwriting, and mortgage prompts use one shared language
  instruction.
- Reconstructed claim prefixes are localized.
- German has the same static translation-key coverage as English and French.
- Raw OCR/source panes remain in the document language. Derived AI content is generated
  in the selected display language.

Existing analyses are persisted canonical content. Changing the UI locale translates
only human-readable derived fields on demand and caches the localized presentation by
application, source-analysis revision, and locale. It never rewrites raw OCR, citations,
policy references, identifiers, URLs, numbers, or canonical analysis data.

## Web intelligence decision

Microsoft Web IQ is integrated as a dedicated Streamable HTTP MCP connection through
Microsoft Agent Framework's `MCPStreamableHTTPTool`.

- Endpoint: `https://api.microsoft.ai/v3/mcp`
- Authentication: `x-apikey`, sourced from Key Vault secret `webiq-api-key`
- Allowed tools: `web`, `news`, and `browse`
- Runtime tool names: `webiq_web`, `webiq_news`, and `webiq_browse`

This matches the Microsoft Web IQ MCP contract. The previous Foundry Agent Service
`WebSearchTool`/Bing path and Azure OpenAI `web_search_preview` path were removed.
Missing Web IQ configuration is now explicit; it does not silently change providers.

Use `infra/set-webiq-secret.ps1` to enter the new key without printing it or committing
it. Then deploy through `infra/deploy.ps1` with Web IQ secret wiring enabled in the
chosen IaC configuration.

API-key authentication is the selected demo path. Microsoft recommends API keys for
evaluation and Microsoft Entra ID for production workloads. A future production-hardening
step can replace the `x-apikey` header with an Entra access token without moving web
intelligence back into the Foundry project.

## Web IQ access-denied diagnosis

The Microsoft sign-in page can report "You don't have access to this" after authentication
has succeeded. That message is an authorization failure, not proof that the password or
application runtime is incorrect.

Check these boundaries independently:

1. **Tenant context**: sign out of other Microsoft accounts and sign in with the account
   invited to the tenant that owns the Web IQ profile. Confirm the tenant in the sign-in
   URL and in `az account show` before Azure operations.
2. **Web IQ entitlement**: confirm that the account can open Profile Management and has an
   active Web IQ account/key. Azure subscription Owner or Contributor does not grant Web IQ
   product access.
3. **Allowed service list**: the MCP server exposes only tools enabled for the Web IQ
   account. Confirm that `web`, `news`, and `browse` appear; request enablement from the
   Microsoft representative when a required tool is absent.
4. **Azure runtime RBAC**: separately confirm that the app managed identity has
   `Key Vault Secrets User` and that the operator storing the key has
   `Key Vault Secrets Officer`. These roles do not grant access to the Web IQ portal.
5. **Application configuration**: after storing the key, verify that the Container App
   secret is a Key Vault reference and that `WEBIQ_API_KEY` is a `secretref`, never a
   literal environment value.

Do not paste keys or passwords into chat, source files, command history, screenshots, or
frontend configuration. Rotate any credential that has been displayed in clear text.

## Demo asset classification

The former ambiguous folders (`habitation2`, `carcrash2`, `dental`, and `sante`) were
reclassified by persona and scenario. The in-app demo guide now references the new
paths. See `assets/demo-prevaiq/README.md` for the folder map.

## Remaining behavior to expect

- A French source document remains visibly French in the raw OCR/source view.
- The same dossier's generated summary and agent response follow EN, FR, or DE.
- Web intelligence is unavailable until a valid Web IQ key is stored and deployed.
