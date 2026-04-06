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
  Header,
  Footer,
  PageNumber,
  PageBreak,
} = require("docx");

const TEAL = "0d4f4f";
const HEADER_FILL = "d0e8e8";
const BLACK = "000000";
const BORDER_GRAY = "aaaaaa";

const MARGIN_TWIP = 1440;

const SZ_TITLE = 64;
const SZ_HEADING = 40;
const SZ_BODY = 22;

function gridWidths(pcts) {
  const total = 9360;
  const sum = pcts.reduce((a, b) => a + b, 0);
  return pcts.map((p) => Math.round((p / sum) * total));
}

const headerShading = {
  fill: HEADER_FILL,
  type: ShadingType.CLEAR,
  color: "auto",
};

const tableBorder = {
  style: BorderStyle.SINGLE,
  size: 1,
  color: BORDER_GRAY,
};

const tableBorders = {
  top: tableBorder,
  bottom: tableBorder,
  left: tableBorder,
  right: tableBorder,
  insideHorizontal: tableBorder,
  insideVertical: tableBorder,
};

function bodyRun(text, opts = {}) {
  return new TextRun({
    text,
    font: "Arial",
    size: SZ_BODY,
    color: BLACK,
    ...opts,
  });
}

function bodyParagraph(text, extra = {}) {
  return new Paragraph({
    spacing: { after: 160 },
    children: [bodyRun(text)],
    ...extra,
  });
}

function headingParagraph(text) {
  return new Paragraph({
    spacing: { before: 240, after: 120 },
    children: [
      new TextRun({
        text,
        font: "Arial",
        size: SZ_HEADING,
        bold: true,
        color: TEAL,
      }),
    ],
  });
}

function bulletParagraph(text) {
  return new Paragraph({
    bullet: { level: 0 },
    spacing: { after: 80 },
    children: [bodyRun(text)],
  });
}

function tableCell(text, { header = false } = {}) {
  return new TableCell({
    shading: header ? headerShading : undefined,
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    borders: {
      top: tableBorder,
      bottom: tableBorder,
      left: tableBorder,
      right: tableBorder,
    },
    children: [
      new Paragraph({
        children: [
          new TextRun({
            text,
            font: "Arial",
            size: SZ_BODY,
            bold: header,
            color: BLACK,
          }),
        ],
      }),
    ],
  });
}

function makeTable(columnPct, rows) {
  const columnWidths = gridWidths(columnPct);
  return new Table({
    width: { size: 100, type: WidthType.PERCENTAGE },
    columnWidths,
    borders: tableBorders,
    rows: rows.map((cells, idx) => {
      const isHeader = idx === 0;
      return new TableRow({
        tableHeader: isHeader,
        children: cells.map((c) => tableCell(c, { header: isHeader })),
      });
    }),
  });
}

const outputPath = path.join(
  __dirname,
  "..",
  "docs",
  "CampaignForge-Beta-Testing-Plan.docx",
);

const doc = new Document({
  features: {
    updateFields: true,
  },
  sections: [
    {
      properties: {
        page: {
          margin: {
            top: MARGIN_TWIP,
            right: MARGIN_TWIP,
            bottom: MARGIN_TWIP,
            left: MARGIN_TWIP,
          },
        },
      },
      headers: {
        default: new Header({
          children: [
            new Paragraph({
              alignment: AlignmentType.RIGHT,
              children: [
                new TextRun({
                  text: "CampaignForge AI — Beta Testing Plan v1.0",
                  font: "Arial",
                  size: SZ_BODY,
                  color: BLACK,
                }),
              ],
            }),
          ],
        }),
      },
      footers: {
        default: new Footer({
          children: [
            new Paragraph({
              alignment: AlignmentType.CENTER,
              children: [
                new TextRun({
                  text: "Page ",
                  font: "Arial",
                  size: SZ_BODY,
                  color: BLACK,
                }),
                new TextRun({
                  children: [PageNumber.CURRENT],
                  font: "Arial",
                  size: SZ_BODY,
                  color: BLACK,
                }),
                new TextRun({
                  text: " of ",
                  font: "Arial",
                  size: SZ_BODY,
                  color: BLACK,
                }),
                new TextRun({
                  children: [PageNumber.TOTAL_PAGES],
                  font: "Arial",
                  size: SZ_BODY,
                  color: BLACK,
                }),
              ],
            }),
          ],
        }),
      },
      children: [
        new Paragraph({ spacing: { after: 400 } }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 200 },
          children: [
            new TextRun({
              text: "CampaignForge AI — Beta Testing Plan",
              font: "Arial",
              size: SZ_TITLE,
              bold: true,
              color: TEAL,
            }),
          ],
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 120 },
          children: [
            new TextRun({
              text: "Version 1.0 | March 2026",
              font: "Arial",
              size: SZ_BODY,
              color: BLACK,
            }),
          ],
        }),
        new Paragraph({
          alignment: AlignmentType.CENTER,
          spacing: { after: 400 },
          children: [
            new TextRun({
              text: "Confidential",
              font: "Arial",
              size: SZ_BODY,
              bold: true,
              color: BLACK,
            }),
          ],
        }),
        new Paragraph({ children: [new PageBreak()] }),

        headingParagraph("1. Executive Summary"),
        bodyParagraph(
          "CampaignForge AI is seeking 20-50 beta testers to validate our multi-agent marketing platform before public launch.",
        ),
        bodyParagraph(
          "Beta testers will get free access to the Growth plan ($149/mo value) for 3 months in exchange for weekly feedback, 2 user interviews, and permission to use their testimonials.",
        ),
        bodyParagraph("Beta program runs April-June 2026."),

        headingParagraph("2. Beta Program Goals"),
        bulletParagraph(
          "Validate product-market fit with real users running real campaigns",
        ),
        bulletParagraph(
          "Identify UX friction points in the campaign creation workflow",
        ),
        bulletParagraph(
          "Test platform publishing reliability across X, LinkedIn, Facebook, Instagram",
        ),
        bulletParagraph(
          "Measure key metrics: time-to-first-campaign, campaign completion rate, content approval rate",
        ),
        bulletParagraph(
          "Collect 10+ publishable testimonials for Product Hunt launch",
        ),
        bulletParagraph("Achieve NPS > 40 among beta cohort"),

        headingParagraph("3. Target Beta Testers (Ideal Profile)"),
        makeTable([18, 32, 32, 18], [
          ["Segment", "Description", "Why They Matter", "# Target"],
          [
            "Freelance Marketers",
            "Solo marketers managing 2-5 clients",
            "Core ICP, highest pain",
            "10",
          ],
          [
            "Small Agency Owners",
            "2-10 person agencies",
            "Validates agency-mode",
            "5",
          ],
          [
            "Startup Founders",
            "Technical founders doing their own marketing",
            "Early adopters, word-of-mouth",
            "10",
          ],
          [
            "Marketing Managers",
            "In-house at SMBs (10-50 employees)",
            "Enterprise signal",
            "5",
          ],
          [
            "Content Creators",
            "YouTubers, podcasters, newsletter writers",
            "Content repurpose use case",
            "5",
          ],
        ]),
        bodyParagraph(
          "Disqualifying criteria: Enterprise companies (>500 employees), agencies with existing AI tools, users who can't commit to weekly feedback.",
        ),

        headingParagraph("4. Beta Tester Recruitment Channels"),
        makeTable([22, 48, 30], [
          ["Channel", "Tactic", "Expected Signups"],
          [
            "X/Twitter",
            "\"Looking for 20 marketers to test our AI agency\" thread + DMs to marketing influencers",
            "15",
          ],
          [
            "LinkedIn",
            "Personal posts + marketing group posts",
            "10",
          ],
          [
            "Reddit",
            "r/marketing, r/SaaS, r/startups — \"Built an AI marketing platform, need beta testers\"",
            "10",
          ],
          [
            "Product Hunt",
            "\"Coming Soon\" page with waitlist",
            "5",
          ],
          [
            "Indie Hackers",
            "Community post + founder story",
            "5",
          ],
          [
            "Cold Email",
            "Targeted outreach to freelance marketers via AgentMail",
            "10",
          ],
          ["Personal Network", "Friends, colleagues, past clients", "5"],
        ]),

        headingParagraph("5. Beta Testing Phases"),
        headingParagraph("Phase 1: Alpha (Week 1-2) — 5 testers"),
        bodyParagraph(
          "Goal: Smoke test core flow (signup → brief → agents → review → approve)",
        ),
        bodyParagraph(
          "Scope: Campaign creation, content generation, basic approval",
        ),
        bodyParagraph(
          "What to test: Onboarding flow, campaign wizard, agent pipeline, content quality",
        ),
        bodyParagraph(
          "Success criteria: 80% complete a campaign without support intervention",
        ),
        headingParagraph("Phase 2: Closed Beta (Week 3-6) — 20 testers"),
        bodyParagraph(
          "Goal: Validate full feature set with diverse user types",
        ),
        bodyParagraph(
          "Scope: All features including publishing, scheduling, calendar, analytics, team",
        ),
        bodyParagraph(
          "What to test: Platform publishing, content repurpose, scheduling, team collaboration, billing",
        ),
        bodyParagraph(
          "Success criteria: 60% create 3+ campaigns, NPS > 30",
        ),
        headingParagraph("Phase 3: Open Beta (Week 7-10) — 50 testers"),
        bodyParagraph(
          "Goal: Scale testing, stress test infrastructure, collect testimonials",
        ),
        bodyParagraph(
          "Scope: Full platform including white-label, templates, API",
        ),
        bodyParagraph(
          "What to test: Performance at scale, edge cases, advanced features",
        ),
        bodyParagraph(
          "Success criteria: <1% error rate, 90% uptime, 10+ testimonials collected",
        ),

        headingParagraph("6. What Beta Testers Get"),
        bulletParagraph("Free Growth plan ($149/mo) for 3 months"),
        bulletParagraph("Direct Slack channel with founding team"),
        bulletParagraph("Priority feature requests"),
        bulletParagraph(
          "\"Founding Member\" badge (permanent 30% discount after beta)",
        ),
        bulletParagraph("Early access to new features"),
        bulletParagraph(
          "Co-marketing opportunities (featured case study)",
        ),

        headingParagraph("7. What We Ask From Beta Testers"),
        bulletParagraph("Create at least 3 campaigns per week"),
        bulletParagraph(
          "Complete weekly 5-minute survey (Google Form)",
        ),
        bulletParagraph(
          "Participate in 2 user interviews (30 min each, Zoom)",
        ),
        bulletParagraph(
          "Report bugs via dedicated Slack channel or in-app feedback",
        ),
        bulletParagraph(
          "Permission to use anonymized usage data for product improvement",
        ),
        bulletParagraph(
          "Optional: Record a 60-second testimonial video",
        ),
        bulletParagraph(
          "Optional: Write a review on G2/Capterra after public launch",
        ),

        headingParagraph("8. Feedback Collection Framework"),
        makeTable([20, 18, 22, 40], [
          ["Method", "Frequency", "Tool", "Owner"],
          ["In-app NPS", "After every 5th campaign", "Built-in modal", "Product"],
          ["Weekly survey", "Every Friday", "Google Forms", "Product"],
          ["Bug reports", "Continuous", "Slack #bugs channel", "Engineering"],
          [
            "User interviews",
            "2 per tester",
            "Zoom + Notion notes",
            "Product",
          ],
          [
            "Usage analytics",
            "Continuous",
            "PostHog / internal",
            "Data",
          ],
          [
            "Feature requests",
            "Continuous",
            "Slack #requests",
            "Product",
          ],
        ]),

        headingParagraph("9. Key Metrics to Track"),
        makeTable([28, 22, 50], [
          ["Metric", "Target", "How Measured"],
          [
            "Time to first campaign",
            "<5 minutes",
            "Backend timestamp diff",
          ],
          [
            "Campaign completion rate",
            ">80%",
            "Completed / Started campaigns",
          ],
          [
            "Content approval rate",
            ">70%",
            "Approved / Generated content pieces",
          ],
          [
            "Publishing success rate",
            ">95%",
            "Published / Attempted publishes",
          ],
          [
            "Weekly active users",
            ">60% of beta cohort",
            "Users with 1+ campaign/week",
          ],
          ["NPS score", ">40", "In-app survey"],
          [
            "Bug reports per user per week",
            "<2",
            "Slack channel count",
          ],
          ["Session duration", ">10 minutes", "Analytics"],
          [
            "Feature adoption",
            ">50% use publishing",
            "Feature usage tracking",
          ],
          [
            "Churn (beta quit rate)",
            "<20%",
            "Users inactive >2 weeks",
          ],
        ]),

        headingParagraph("10. Bug Severity Classification"),
        makeTable([14, 28, 18, 40], [
          ["Severity", "Definition", "Response Time", "Examples"],
          [
            "P0 Critical",
            "System down, data loss, security breach",
            "2 hours",
            "Login broken, campaigns lost, API keys exposed",
          ],
          [
            "P1 High",
            "Core feature broken, no workaround",
            "24 hours",
            "Agent pipeline stuck, content not saving, publishing fails",
          ],
          [
            "P2 Medium",
            "Feature impaired, workaround exists",
            "3 days",
            "Calendar drag-drop glitchy, analytics show wrong data",
          ],
          [
            "P3 Low",
            "Cosmetic, minor UX issue",
            "Next sprint",
            "Typo, alignment off, tooltip missing",
          ],
        ]),

        headingParagraph(
          "11. Beta Testing Checklist (What Testers Should Try)",
        ),
        new Paragraph({
          spacing: { before: 80, after: 80 },
          children: [
            new TextRun({
              text: "Onboarding:",
              font: "Arial",
              size: SZ_BODY,
              bold: true,
              color: TEAL,
            }),
          ],
        }),
        bulletParagraph("Sign up with email via Clerk"),
        bulletParagraph("Complete profile setup"),
        bulletParagraph("Create first client with brand profile"),
        new Paragraph({
          spacing: { before: 160, after: 80 },
          children: [
            new TextRun({
              text: "Campaign Creation:",
              font: "Arial",
              size: SZ_BODY,
              bold: true,
              color: TEAL,
            }),
          ],
        }),
        bulletParagraph("Create campaign using wizard (3-step flow)"),
        bulletParagraph("Try Magic Brief (paste website URL for auto-extraction)"),
        bulletParagraph("Use a campaign template"),
        bulletParagraph(
          "Watch agents work in real-time via SSE dashboard",
        ),
        bulletParagraph(
          "Review and approve/revise content at human review checkpoint",
        ),
        new Paragraph({
          spacing: { before: 160, after: 80 },
          children: [
            new TextRun({
              text: "Content Management:",
              font: "Arial",
              size: SZ_BODY,
              bold: true,
              color: TEAL,
            }),
          ],
        }),
        bulletParagraph("Approve, edit, and reject content pieces"),
        bulletParagraph("Repurpose content to different platforms"),
        bulletParagraph("Generate A/B variants"),
        bulletParagraph("Generate AI images for content"),
        bulletParagraph("Add comments on content pieces"),
        new Paragraph({
          spacing: { before: 160, after: 80 },
          children: [
            new TextRun({
              text: "Publishing & Scheduling:",
              font: "Arial",
              size: SZ_BODY,
              bold: true,
              color: TEAL,
            }),
          ],
        }),
        bulletParagraph("Connect X/LinkedIn/Facebook via OAuth"),
        bulletParagraph("Publish content directly to connected platforms"),
        bulletParagraph("Schedule content via calendar"),
        bulletParagraph("Drag-and-drop reschedule on calendar"),
        bulletParagraph("Switch between month and week views"),
        new Paragraph({
          spacing: { before: 160, after: 80 },
          children: [
            new TextRun({
              text: "Analytics & Intelligence:",
              font: "Arial",
              size: SZ_BODY,
              bold: true,
              color: TEAL,
            }),
          ],
        }),
        bulletParagraph("View campaign analytics"),
        bulletParagraph("Check trending topics"),
        bulletParagraph("Review cross-campaign insights"),
        bulletParagraph("Run competitive intelligence scan"),
        new Paragraph({
          spacing: { before: 160, after: 80 },
          children: [
            new TextRun({
              text: "Team & Settings:",
              font: "Arial",
              size: SZ_BODY,
              bold: true,
              color: TEAL,
            }),
          ],
        }),
        bulletParagraph("Invite team member"),
        bulletParagraph("Change member roles"),
        bulletParagraph("Update org settings"),
        bulletParagraph("Create and manage API keys"),
        bulletParagraph("Set up notifications"),
        new Paragraph({
          spacing: { before: 160, after: 80 },
          children: [
            new TextRun({
              text: "Billing:",
              font: "Arial",
              size: SZ_BODY,
              bold: true,
              color: TEAL,
            }),
          ],
        }),
        bulletParagraph("View pricing plans"),
        bulletParagraph("Upgrade via Stripe checkout"),

        headingParagraph("12. Timeline"),
        makeTable([22, 78], [
          ["Date", "Milestone"],
          ["Apr 1, 2026", "Beta program announced, recruitment begins"],
          ["Apr 7", "Alpha testing starts (5 testers)"],
          ["Apr 14", "Alpha feedback review, bug fixes"],
          ["Apr 21", "Closed beta starts (20 testers)"],
          ["May 5", "Mid-beta survey, first user interviews"],
          ["May 19", "Feature freeze for beta feedback"],
          ["Jun 2", "Open beta starts (50 testers)"],
          ["Jun 16", "Final survey, testimonial collection"],
          ["Jun 23", "Beta program ends"],
          ["Jun 30", "Public launch + Product Hunt"],
        ]),

        headingParagraph("13. Risks & Mitigations"),
        makeTable([28, 72], [
          ["Risk", "Mitigation"],
          [
            "Low tester engagement",
            "Weekly Slack reminders, gamification (leaderboard), personal DMs",
          ],
          [
            "Too many bug reports",
            "Triage with severity levels, daily standup on P0/P1s",
          ],
          [
            "Negative feedback",
            "Treat as gift; rapid iteration; transparent changelog",
          ],
          [
            "Testers churning",
            "Personal onboarding call, check-in if inactive >5 days",
          ],
          [
            "LLM quality issues",
            "QA agent catches most; human review gate; prompt tuning from feedback",
          ],
          [
            "Publishing API failures",
            "Retry logic (3 attempts), graceful error messages, manual fallback instructions",
          ],
          [
            "Data privacy concerns",
            "Clear privacy policy, anonymized analytics, no sharing of campaign content",
          ],
        ]),

        headingParagraph("14. Contact"),
        bodyParagraph("Founder: [Founder Name]"),
        bodyParagraph("Email: beta@campaignforge.ai"),
        bodyParagraph("Slack: CampaignForge Beta Community"),
        bodyParagraph("Website: https://campaignforge-ai-three.vercel.app"),
      ],
    },
  ],
});

Packer.toBuffer(doc).then((buffer) => {
  fs.mkdirSync(path.dirname(outputPath), { recursive: true });
  fs.writeFileSync(outputPath, buffer);
  console.log("Wrote", outputPath);
});

