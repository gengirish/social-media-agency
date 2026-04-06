"use strict";

const fs = require("fs");
const path = require("path");
const {
  Document,
  Packer,
  Paragraph,
  TextRun,
  Table,
  TableRow,
  TableCell,
  WidthType,
  AlignmentType,
  BorderStyle,
  ShadingType,
  VerticalAlign,
  PageBreak,
  Header,
  Footer,
  PageNumber,
  convertInchesToTwip,
} = require("docx");

const BLUE = "1A365D";
const HEADER_FILL = "D5E8F0";
const BORDER = "BBBBBB";
const margin = convertInchesToTwip(1);

const bodyRun = (text, extra = {}) =>
  new TextRun({ text, font: "Arial", size: 22, color: "000000", ...extra });

const bodyP = (text, spacing = { after: 160 }) =>
  new Paragraph({ spacing, children: [bodyRun(text)] });

const headingP = (text) =>
  new Paragraph({
    spacing: { before: 360, after: 200 },
    children: [new TextRun({ text, font: "Arial", size: 44, bold: true, color: BLUE })],
  });

const tableBorders = {
  top: { style: BorderStyle.SINGLE, size: 1, color: BORDER },
  bottom: { style: BorderStyle.SINGLE, size: 1, color: BORDER },
  left: { style: BorderStyle.SINGLE, size: 1, color: BORDER },
  right: { style: BorderStyle.SINGLE, size: 1, color: BORDER },
  insideHorizontal: { style: BorderStyle.SINGLE, size: 1, color: BORDER },
  insideVertical: { style: BorderStyle.SINGLE, size: 1, color: BORDER },
};

function headerCell(text, opts = {}) {
  const size = opts.size || 22;
  return new TableCell({
    shading: { fill: HEADER_FILL, type: ShadingType.CLEAR, color: "auto" },
    verticalAlign: VerticalAlign.CENTER,
    margins: { top: 120, bottom: 120, left: 140, right: 140 },
    borders: tableBorders,
    children: [
      new Paragraph({
        children: [new TextRun({ text, font: "Arial", size, bold: true, color: BLUE })],
      }),
    ],
  });
}

function bodyCell(text, opts = {}) {
  const size = opts.size || 22;
  return new TableCell({
    verticalAlign: VerticalAlign.TOP,
    margins: { top: 120, bottom: 120, left: 140, right: 140 },
    borders: tableBorders,
    children: [new Paragraph({ children: [new TextRun({ text, font: "Arial", size, color: "000000" })] })],
  });
}

function makeTable(headerTexts, rows, opts = {}) {
  const headerSize = opts.headerSize || 22;
  const cellSize = opts.cellSize || 22;
  return new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    rows: [
      new TableRow({
        tableHeader: true,
        children: headerTexts.map((t) => headerCell(t, { size: headerSize })),
      }),
      ...rows.map(
        (cells) =>
          new TableRow({
            children: cells.map((c) => bodyCell(c, { size: cellSize })),
          })
      ),
    ],
  });
}

const headerBlock = new Header({
  children: [
    new Paragraph({
      alignment: AlignmentType.RIGHT,
      children: [
        new TextRun({
          text: "CampaignForge AI \u2014 YC Application S2027",
          font: "Arial",
          size: 22,
          color: "666666",
        }),
      ],
    }),
  ],
});

const footerBlock = new Footer({
  children: [
    new Paragraph({
      alignment: AlignmentType.RIGHT,
      children: [
        new TextRun({
          children: ["Page ", PageNumber.CURRENT, " of ", PageNumber.TOTAL_PAGES],
          font: "Arial",
          size: 22,
          color: "666666",
        }),
      ],
    }),
  ],
});

const children = [
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 400 },
    children: [
      new TextRun({ text: "CampaignForge AI", font: "Arial", size: 64, bold: true, color: BLUE }),
    ],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 240 },
    children: [
      new TextRun({
        text: "YC Application \u2014 S2027 Batch",
        font: "Arial",
        size: 44,
        bold: true,
        color: BLUE,
      }),
    ],
  }),
  new Paragraph({
    alignment: AlignmentType.CENTER,
    spacing: { after: 200 },
    children: [
      new TextRun({
        text: "Replace your marketing agency with 7 AI agents",
        font: "Arial",
        size: 22,
        italics: true,
        color: "000000",
      }),
    ],
  }),
  new Paragraph({ children: [new PageBreak()] }),


  headingP("Company Details"),
  bodyP("Company: CampaignForge AI"),
  bodyP(
    "One-liner: Replace your marketing agency with 7 AI agents. One brief. Complete campaign. 5 minutes. $49/month."
  ),
  bodyP("URL: https://campaignforge-ai-three.vercel.app"),
  bodyP("API: https://campaignforge-api.fly.dev"),
  headingP("1. Company Description"),
  bodyP(
    "CampaignForge is an AI-native marketing platform where 7 specialized agents (Strategist, SEO Researcher, Content Writer, Ad Copywriter, Human Review, QA/Brand, Analytics) collaborate in a visible LangGraph pipeline. Users type one brief, watch agents think and generate in real time via SSE streaming, review output at a human-in-the-loop checkpoint, then publish across platforms \u2014 all in under 5 minutes. It costs $49/month instead of $5,000/month for a marketing agency."
  ),

  headingP("2. The Problem"),
  bodyP(
    "Small businesses and freelance marketers spend $3,000-10,000/month on marketing agencies or 15-20 hours/week doing it manually. Existing AI marketing tools (Jasper, Copy.ai, Uplane, Rankai) are single-purpose: one does ads, another does SEO, another does content. None replaces the full agency workflow. They're black boxes that generate isolated outputs without strategy, quality control, or brand consistency."
  ),

  headingP("3. The Solution"),
  bodyP(
    "CampaignForge mirrors how real agencies work \u2014 specialized roles, parallel execution, quality gates \u2014 at 1/50th the cost and 100x the speed. Key differentiators:"
  ),
  bodyP(
    "\u2022 Full-stack pipeline: Strategy \u2192 SEO \u2192 Content \u2192 Ads \u2192 QA (not just one function)"
  ),
  bodyP("\u2022 Transparent agents: Users see what each agent thinks in real time (not a black box)"),
  bodyP("\u2022 Human-in-the-loop: Built-in review checkpoint before anything ships"),
  bodyP("\u2022 Brand voice enforcement: Deep brand profiles that get smarter with every campaign"),
  bodyP("\u2022 Multi-platform publishing: Direct to X, LinkedIn, Facebook, Instagram"),

  headingP("4. The Unique Insight"),
  bodyP(
    "\"Marketing agencies are teams, not individuals. Single-model AI tools fail because they try to do strategy, writing, SEO, ads, and QA with one prompt. CampaignForge's multi-agent architecture mirrors how real agencies work \u2014 specialized roles, parallel execution, quality gates \u2014 producing enterprise-quality output at SMB prices.\""
  ),

  headingP("5. Market Size"),
  bodyP("\u2022 TAM: $26.9B by 2034 (AI Marketing Software)"),
  bodyP("\u2022 SAM: $3.49B (2026, SMB marketing automation)"),
  bodyP("\u2022 SOM: $50M (freelance marketers + small agencies in US/UK)"),
  bodyP("\u2022 Growth: 28.6% CAGR"),

  headingP("6. Product \u2014 What's Built (live, deployed, tested)"),
  makeTable(
    ["Feature", "Details"],
    [
      ["83 API endpoints across 20 routers", "Live production REST API; 20 routers"],
      [
        "11 LangGraph agent nodes",
        "Orchestrator, Strategy, SEO, Content Writer, Ad Copy, Human Review, QA/Brand, Analytics, Competitive Intel, Autonomous Operator, Video Script",
      ],
      ["17 PostgreSQL tables with multi-tenant isolation", "Multi-tenant data model"],
      ["20 backend services", "Service layer behind the API"],
      ["19 frontend pages", "Next.js dashboard and flows"],
      ["Stripe billing with 4 tiers", "Free $0, Starter $49, Growth $149, Agency $399"],
      ["OAuth platform connections", "X, LinkedIn, Meta"],
      ["Real-time SSE streaming of agent pipeline", "Live agent progress in the UI"],
      ["White-label client portal", "Agency-ready client experience"],
      ["Template marketplace", "Reusable campaign templates"],
      ["Slack bot integration", "Workflows and alerts in Slack"],
      ["REST API with API key authentication", "Developer access and automation"],
      ["Enterprise audit logging", "Compliance-oriented activity trail"],
      ["Notification system", "In-app and outbound notifications"],
      ["Competitive intelligence agent", "Automated competitor signals"],
      ["Visual content generation via fal.ai", "Integrated image generation"],
      ["RAG knowledge base from 171 marketing skills", "Grounded marketing playbooks"],
      ["Multi-language content generation", "Localized campaign outputs"],
      ["A/B content variant generation", "Experiment-ready variants"],
    ]
  ),

  headingP("7. Competitive Landscape"),
  makeTable(
    ["Capability", "Uplane (YC F25)", "Rankai (YC S23)", "Sprites (YC W22)", "CampaignForge"],
    [
      ["Multi-agent orchestration", "Hidden", "Hidden", "Hidden", "Live dashboard"],
      ["Full-stack campaign", "Ads only", "SEO only", "Acquisition", "Full pipeline"],
      ["Brand voice enforcement", "Basic", "No", "No", "Deep profiles"],
      ["Human-in-the-loop review", "No", "No", "No", "Built-in"],
      ["Transparent AI", "Black box", "Black box", "Black box", "Open pipeline"],
      ["Multi-platform publishing", "Ad platforms", "Blog/web", "Varied", "4 social platforms"],
      ["Agency white-label", "No", "No", "No", "Yes"],
    ],
    { headerSize: 18, cellSize: 18 }
  ),

  headingP("8. Business Model"),
  makeTable(
    ["Plan", "Price", "Clients", "Posts/mo", "Target"],
    [
      ["Free", "$0", "2", "30", "Trial users"],
      ["Starter", "$49/mo", "5", "100", "Freelancers"],
      ["Growth", "$149/mo", "15", "500", "Growing teams"],
      ["Agency", "$399/mo", "Unlimited", "Unlimited", "Agencies"],
    ]
  ),
  bodyP(
    "Unit economics: LLM cost ~$0.15-0.30/campaign (Gemini Flash). Infrastructure <$50/mo at 100 users. 90%+ gross margin at scale.",
    { after: 160, before: 240 }
  ),

  headingP("9. Tech Stack"),
  makeTable(
    ["Layer", "Stack"],
    [
      ["Frontend", "Next.js 14 + Clerk Auth \u2192 Vercel Edge"],
      ["Backend", "FastAPI + LangGraph \u2192 Fly.io"],
      ["Database", "PostgreSQL \u2192 Neon Serverless"],
      ["AI Brain", "Claude Sonnet (orchestrator/QA) \u2192 Anthropic"],
      ["AI Workers", "Gemini 2.0 Flash (content) \u2192 Google"],
      ["Payments", "Stripe subscriptions"],
      ["Email", "AgentMail"],
      ["CI/CD", "GitHub Actions, 9 E2E tests passing"],
    ]
  ),

  headingP("10. Go-to-Market"),
  bodyP(
    "Phase 1 (Weeks 1-4): Ship publishing, scheduling, payments. Get first 5 paying beta users from freelance marketers."
  ),
  bodyP(
    "Phase 2 (Weeks 5-8): Product Hunt launch, X/Twitter daily threads, LinkedIn case studies. Target: 20 paying users, $2K MRR."
  ),
  bodyP(
    "Phase 3 (Weeks 9-14): Brand learning moat, agency-mode white-label, template marketplace. Target: 100 users, $10K MRR."
  ),

  headingP("11. The Ask"),
  bodyP(
    "Raising $500K on a SAFE at YC standard terms. Use of funds: 60% Engineering (full-time hire + LLM costs); 20% GTM (Product Hunt, content marketing, cold outreach); 20% Runway (12 months at current burn)."
  ),

  headingP("12. Why Now"),
  bodyP("\u2022 LLM costs dropped 90% in 18 months (Gemini Flash = $0.15/campaign)"),
  bodyP("\u2022 Multi-agent frameworks matured (LangGraph, CrewAI)"),
  bodyP("\u2022 SMBs priced out of agencies post-2024 recession"),
  bodyP("\u2022 Social platforms opened APIs for programmatic publishing"),
  bodyP("\u2022 Existing YC-funded competitors proved market demand but only solve single functions"),

  headingP("Company Details"),
  bodyP("Company: CampaignForge AI"),
  bodyP(
    "One-liner: Replace your marketing agency with 7 AI agents. One brief. Complete campaign. 5 minutes. $49/month."
  ),
  bodyP("URL: https://campaignforge-ai-three.vercel.app"),
  bodyP("API: https://campaignforge-api.fly.dev"),
];

const doc = new Document({
  sections: [
    {
      properties: {
        page: {
          margin: { top: margin, right: margin, bottom: margin, left: margin },
        },
      },
      headers: { default: headerBlock },
      footers: { default: footerBlock },
      children,
    },
  ],
});

const outputPath = path.join(__dirname, "..", "docs", "CampaignForge-YC-Pitch.docx");

Packer.toBuffer(doc).then((buffer) => { require("fs").writeFileSync(outputPath, buffer); console.log("Wrote:", outputPath); }).catch((err) => { console.error(err); process.exit(1); });


