# web-intel-mcp

MCP server that gives Claude, Cursor and other AI agents five web tools:
`website_health_audit`, `detect_tech_stack`, `page_to_markdown`, `find_broken_links`, `extract_pdf_text`.

## Install
```json
{ "mcpServers": { "web-intel": { "command": "uvx", "args": ["web-intel-mcp"],
  "env": { "RAPIDAPI_KEY": "<your key>" } } } }
```
Get a key (free tier) on the RapidAPI listing "Web Intelligence API". AI agents with a wallet can also pay per call
with x402 (USDC on Base) directly at `https://<host>/x402/v1/*` without any key.
