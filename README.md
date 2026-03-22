# Social Media Agency - AI Skills Hub

An AI-powered digital marketing agency workspace equipped with 70+ specialized skills, 20 marketing agents, and 90+ commands for Cursor IDE.

## Installed Skill Sources

### 1. AgentKits Marketing Kit
- **28 marketing skills** (SEO, CRO, copywriting, email marketing, pricing strategy, etc.)
- **20 specialized agents** (attraction specialist, SEO specialist, copywriter, email wizard, etc.)
- **93 slash commands** across campaign, content, SEO, CRO, analytics, and more
- **Workflows** for marketing, sales, and CRM orchestration
- Source: [github.com/aitytech/agentkits-marketing](https://github.com/aitytech/agentkits-marketing)

### 2. Marketing Skills Library (kostja94)
- **160+ markdown skills** for SEO, content, 40+ page types, paid ads, channels, and growth strategies
- Source: [github.com/kostja94/marketing-skills](https://github.com/kostja94/marketing-skills)

### 3. Individual Skills (agentskill.sh)

| Skill | Source | Description |
|-------|--------|-------------|
| `crosspost` | affaan-m | Multi-platform content distribution (X, LinkedIn, Threads, Bluesky) |
| `x-api` | affaan-m | X/Twitter API interactions (post, read timelines, analytics) |
| `article-writing` | affaan-m | Long-form article and guide creation |
| `deep-research` | affaan-m | Research reports from web sources with citations |
| `fal-ai-media` | affaan-m | Generate images, videos, audio with fal.ai |
| `video-editing` | affaan-m | AI-powered video cutting and enhancement |
| `frontend-slides` | affaan-m | Create HTML presentations from scratch or PPTX |
| `exa-search` | affaan-m | Neural search via Exa MCP |
| `market-research` | affaan-m | Market research and competitive analysis |
| `investor-materials` | affaan-m | Pitch decks and financial models |
| `brand-guidelines` | anthropics | Brand colors and typography consistency |
| `pptx` | anthropics | Create/edit PowerPoint presentations |
| `docx` | anthropics | Create/edit Word documents |
| `internal-comms` | anthropics | Internal communications templates |
| `doc-coauthoring` | anthropics | Collaborative document authoring workflows |
| `theme-factory` | anthropics | Professional themes and visual identity |
| `slack-gif-creator` | anthropics | Animated GIFs for Slack |
| `typefully` | typefully | Draft, schedule, publish social media content |
| `xurl` | openclaw | Authenticated X/Twitter API requests |

## Directory Structure

```
.cursor/
  agents/          # 20 specialized marketing AI agents
  commands/        # 93+ slash commands organized by category
  skills/          # 70+ marketing skills
  training/        # Interactive training modules
  workflows/       # Marketing, sales, CRM workflows
```

## Getting Started

1. Copy `.env.example` to `.env` and fill in your API keys
2. Review `.cursor/mcp.json.example` for MCP integration setup (Google Analytics, Search Console, SendGrid, etc.)
3. Start using skills by referencing them in Cursor chat

## License

Skills are sourced from open-source MIT-licensed repositories.
