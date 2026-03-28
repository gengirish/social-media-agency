const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const {
  FaRobot, FaChartLine, FaDollarSign, FaUsers, FaRocket,
  FaBrain, FaSearchDollar, FaPenFancy, FaAd, FaShieldAlt,
  FaBullseye, FaLayerGroup, FaEye, FaClock, FaCheckCircle,
  FaStar, FaLightbulb, FaArrowRight, FaGlobe, FaEnvelope
} = require("react-icons/fa");

// --- Color palette: "Coral Energy" adapted for startup pitch ---
const C = {
  primary: "F96167",    // coral
  secondary: "2F3C7E",  // deep navy
  accent: "F9E795",     // gold
  dark: "1A1F36",       // dark navy
  light: "FAFBFF",      // off-white
  white: "FFFFFF",
  muted: "8892B0",      // muted blue-gray
  success: "10B981",    // green
  navy80: "4A5296",     // lighter navy
};

function renderIconSvg(IconComponent, color, size = 256) {
  return ReactDOMServer.renderToStaticMarkup(
    React.createElement(IconComponent, { color: "#" + color, size: String(size) })
  );
}

async function iconToBase64Png(IconComponent, color, size = 256) {
  const svg = renderIconSvg(IconComponent, color, size);
  const pngBuffer = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + pngBuffer.toString("base64");
}

const mkShadow = () => ({
  type: "outer", color: "000000", blur: 8, offset: 3, angle: 135, opacity: 0.12,
});

async function createDeck() {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_16x9";
  pres.author = "CampaignForge AI";
  pres.title = "CampaignForge AI — Investor Pitch Deck";

  // Pre-render icons
  const icons = {
    robot: await iconToBase64Png(FaRobot, C.primary),
    chart: await iconToBase64Png(FaChartLine, C.primary),
    dollar: await iconToBase64Png(FaDollarSign, C.success),
    users: await iconToBase64Png(FaUsers, C.secondary),
    rocket: await iconToBase64Png(FaRocket, C.primary),
    brain: await iconToBase64Png(FaBrain, C.accent),
    search: await iconToBase64Png(FaSearchDollar, C.white),
    pen: await iconToBase64Png(FaPenFancy, C.white),
    ad: await iconToBase64Png(FaAd, C.white),
    shield: await iconToBase64Png(FaShieldAlt, C.white),
    bullseye: await iconToBase64Png(FaBullseye, C.white),
    layers: await iconToBase64Png(FaLayerGroup, C.white),
    eye: await iconToBase64Png(FaEye, C.primary),
    clock: await iconToBase64Png(FaClock, C.primary),
    check: await iconToBase64Png(FaCheckCircle, C.success),
    star: await iconToBase64Png(FaStar, C.accent),
    lightbulb: await iconToBase64Png(FaLightbulb, C.accent),
    arrow: await iconToBase64Png(FaArrowRight, C.primary),
    globe: await iconToBase64Png(FaGlobe, C.secondary),
    envelope: await iconToBase64Png(FaEnvelope, C.secondary),
    brainWhite: await iconToBase64Png(FaBrain, C.white),
    robotNav: await iconToBase64Png(FaRobot, C.secondary),
    dollarW: await iconToBase64Png(FaDollarSign, C.white),
    usersW: await iconToBase64Png(FaUsers, C.white),
    rocketW: await iconToBase64Png(FaRocket, C.white),
    chartW: await iconToBase64Png(FaChartLine, C.white),
    eyeW: await iconToBase64Png(FaEye, C.white),
    clockW: await iconToBase64Png(FaClock, C.white),
    checkW: await iconToBase64Png(FaCheckCircle, C.white),
    starW: await iconToBase64Png(FaStar, C.white),
    globeW: await iconToBase64Png(FaGlobe, C.white),
  };

  // ===== SLIDE 1: Title =====
  let s = pres.addSlide();
  s.background = { color: C.dark };
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 4.4, w: 10, h: 1.225, fill: { color: C.primary },
  });
  s.addImage({ data: icons.robot, x: 4.25, y: 0.8, w: 1.5, h: 1.5 });
  s.addText("CampaignForge AI", {
    x: 0.5, y: 2.4, w: 9, h: 0.8,
    fontSize: 44, fontFace: "Trebuchet MS", color: C.white,
    bold: true, align: "center", margin: 0,
  });
  s.addText("Replace Your Marketing Agency with 7 AI Agents", {
    x: 1, y: 3.2, w: 8, h: 0.6,
    fontSize: 20, fontFace: "Calibri", color: C.muted,
    align: "center", margin: 0,
  });
  s.addText("Investor Pitch  |  March 2026", {
    x: 1, y: 4.65, w: 8, h: 0.5,
    fontSize: 16, fontFace: "Calibri", color: C.dark,
    bold: true, align: "center", margin: 0,
  });

  // ===== SLIDE 2: Problem =====
  s = pres.addSlide();
  s.background = { color: C.light };
  s.addText("The Problem", {
    x: 0.6, y: 0.3, w: 8, h: 0.7,
    fontSize: 36, fontFace: "Trebuchet MS", color: C.secondary, bold: true, margin: 0,
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.6, y: 1.0, w: 1.2, h: 0.06, fill: { color: C.primary },
  });

  const problems = [
    { num: "$5K–15K/mo", desc: "Average cost of a marketing agency for SMBs" },
    { num: "3–5 weeks", desc: "Time from brief to first content delivery" },
    { num: "70%", desc: "Of SMBs can't afford professional marketing help" },
    { num: "1 function", desc: "Most AI tools only do ads OR SEO OR content — never all three" },
  ];
  problems.forEach((p, i) => {
    const yPos = 1.4 + i * 1.0;
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.6, y: yPos, w: 8.8, h: 0.85,
      fill: { color: C.white }, shadow: mkShadow(),
    });
    s.addText(p.num, {
      x: 0.8, y: yPos + 0.1, w: 2.5, h: 0.65,
      fontSize: 26, fontFace: "Trebuchet MS", color: C.primary,
      bold: true, valign: "middle", margin: 0,
    });
    s.addText(p.desc, {
      x: 3.4, y: yPos + 0.1, w: 5.8, h: 0.65,
      fontSize: 16, fontFace: "Calibri", color: C.dark,
      valign: "middle", margin: 0,
    });
  });

  // ===== SLIDE 3: Solution =====
  s = pres.addSlide();
  s.background = { color: C.secondary };
  s.addText("The Solution", {
    x: 0.6, y: 0.3, w: 8, h: 0.7,
    fontSize: 36, fontFace: "Trebuchet MS", color: C.white, bold: true, margin: 0,
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.6, y: 1.0, w: 1.2, h: 0.06, fill: { color: C.primary },
  });
  s.addText([
    { text: "CampaignForge replaces the entire marketing agency", options: { bold: true, fontSize: 22 } },
    { text: " — not just one function — with ", options: { fontSize: 22 } },
    { text: "7 specialized AI agents", options: { bold: true, color: C.accent, fontSize: 22 } },
    { text: " that work together in a visible, auditable pipeline.", options: { fontSize: 22 } },
  ], {
    x: 0.6, y: 1.3, w: 8.8, h: 1.2,
    fontFace: "Calibri", color: C.white, margin: 0,
  });
  s.addText("One brief → Complete campaign → 5 minutes → $49/month", {
    x: 0.6, y: 2.6, w: 8.8, h: 0.6,
    fontSize: 20, fontFace: "Calibri", color: C.accent,
    bold: true, italic: true, margin: 0,
  });

  const agents = [
    { icon: icons.brainWhite, name: "Orchestrator" },
    { icon: icons.bullseye, name: "Strategist" },
    { icon: icons.search, name: "SEO" },
    { icon: icons.pen, name: "Copywriter" },
    { icon: icons.ad, name: "Ad Creator" },
    { icon: icons.shield, name: "QA/Brand" },
    { icon: icons.layers, name: "Publisher" },
  ];
  agents.forEach((a, i) => {
    const xPos = 0.35 + i * 1.35;
    s.addShape(pres.shapes.RECTANGLE, {
      x: xPos, y: 3.5, w: 1.15, h: 1.6,
      fill: { color: C.navy80 }, shadow: mkShadow(),
    });
    s.addImage({ data: a.icon, x: xPos + 0.33, y: 3.65, w: 0.5, h: 0.5 });
    s.addText(a.name, {
      x: xPos, y: 4.25, w: 1.15, h: 0.7,
      fontSize: 11, fontFace: "Calibri", color: C.white,
      align: "center", valign: "top", margin: 0,
    });
  });

  // ===== SLIDE 4: How It Works =====
  s = pres.addSlide();
  s.background = { color: C.light };
  s.addText("How It Works", {
    x: 0.6, y: 0.3, w: 8, h: 0.7,
    fontSize: 36, fontFace: "Trebuchet MS", color: C.secondary, bold: true, margin: 0,
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.6, y: 1.0, w: 1.2, h: 0.06, fill: { color: C.primary },
  });

  const steps = [
    { num: "1", title: "Submit Brief", desc: "Describe your campaign in natural language. AI auto-extracts brand voice from your website.", color: C.primary },
    { num: "2", title: "Agents Collaborate", desc: "7 specialized agents work in parallel — strategy, SEO, content, ads, QA — all visible in real time.", color: C.secondary },
    { num: "3", title: "Review & Approve", desc: "Human-in-the-loop. Review each piece, approve, edit, or send back. Nothing ships without your OK.", color: C.success },
    { num: "4", title: "Publish Everywhere", desc: "One-click publishing to X, LinkedIn, Instagram, Facebook. Schedule, track, and optimize.", color: C.navy80 },
  ];
  steps.forEach((st, i) => {
    const yPos = 1.3 + i * 1.05;
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.6, y: yPos, w: 0.55, h: 0.55,
      fill: { color: st.color },
    });
    s.addText(st.num, {
      x: 0.6, y: yPos, w: 0.55, h: 0.55,
      fontSize: 22, fontFace: "Trebuchet MS", color: C.white,
      bold: true, align: "center", valign: "middle", margin: 0,
    });
    s.addText(st.title, {
      x: 1.35, y: yPos, w: 3, h: 0.55,
      fontSize: 18, fontFace: "Trebuchet MS", color: C.dark,
      bold: true, valign: "middle", margin: 0,
    });
    s.addText(st.desc, {
      x: 4.2, y: yPos, w: 5.4, h: 0.55,
      fontSize: 13, fontFace: "Calibri", color: C.muted,
      valign: "middle", margin: 0,
    });
  });

  // ===== SLIDE 5: Market Opportunity =====
  s = pres.addSlide();
  s.background = { color: C.dark };
  s.addText("Market Opportunity", {
    x: 0.6, y: 0.3, w: 8, h: 0.7,
    fontSize: 36, fontFace: "Trebuchet MS", color: C.white, bold: true, margin: 0,
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.6, y: 1.0, w: 1.2, h: 0.06, fill: { color: C.primary },
  });

  // TAM / SAM / SOM cards
  const markets = [
    { label: "TAM", value: "$26.9B", sub: "AI Marketing by 2034", color: C.primary },
    { label: "SAM", value: "$3.49B", sub: "AI Marketing today (2026)", color: C.secondary },
    { label: "SOM", value: "$50M", sub: "SMB agency replacement", color: C.success },
  ];
  markets.forEach((m, i) => {
    const xPos = 0.6 + i * 3.1;
    s.addShape(pres.shapes.RECTANGLE, {
      x: xPos, y: 1.3, w: 2.8, h: 2.2,
      fill: { color: m.color }, shadow: mkShadow(),
    });
    s.addText(m.label, {
      x: xPos, y: 1.45, w: 2.8, h: 0.4,
      fontSize: 14, fontFace: "Calibri", color: C.white,
      bold: true, align: "center", margin: 0,
    });
    s.addText(m.value, {
      x: xPos, y: 1.9, w: 2.8, h: 0.7,
      fontSize: 42, fontFace: "Trebuchet MS", color: C.white,
      bold: true, align: "center", margin: 0,
    });
    s.addText(m.sub, {
      x: xPos, y: 2.7, w: 2.8, h: 0.5,
      fontSize: 13, fontFace: "Calibri", color: C.white,
      align: "center", margin: 0, transparency: 30,
    });
  });

  s.addText("33.2% CAGR  |  Fastest-growing segment in MarTech", {
    x: 0.6, y: 3.8, w: 8.8, h: 0.5,
    fontSize: 18, fontFace: "Calibri", color: C.accent,
    bold: true, align: "center", margin: 0,
  });
  s.addText("Sources: Grand View Research, MarketsandMarkets (2024–2034)", {
    x: 0.6, y: 4.5, w: 8.8, h: 0.4,
    fontSize: 11, fontFace: "Calibri", color: C.muted,
    italic: true, align: "center", margin: 0,
  });

  // ===== SLIDE 6: Business Model =====
  s = pres.addSlide();
  s.background = { color: C.light };
  s.addText("Business Model", {
    x: 0.6, y: 0.3, w: 8, h: 0.7,
    fontSize: 36, fontFace: "Trebuchet MS", color: C.secondary, bold: true, margin: 0,
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.6, y: 1.0, w: 1.2, h: 0.06, fill: { color: C.primary },
  });

  const plans = [
    { name: "Free", price: "$0", features: "1 client, 5 campaigns/mo\nNo publishing", border: C.muted },
    { name: "Starter", price: "$49/mo", features: "3 clients, 20 campaigns/mo\n2 platforms", border: C.primary },
    { name: "Growth", price: "$149/mo", features: "10 clients, unlimited campaigns\nAll platforms", border: C.success },
    { name: "Agency", price: "$399/mo", features: "Unlimited, white-label\nPriority support", border: C.secondary },
  ];
  plans.forEach((p, i) => {
    const xPos = 0.4 + i * 2.35;
    s.addShape(pres.shapes.RECTANGLE, {
      x: xPos, y: 1.3, w: 2.15, h: 2.8,
      fill: { color: C.white }, shadow: mkShadow(),
    });
    s.addShape(pres.shapes.RECTANGLE, {
      x: xPos, y: 1.3, w: 2.15, h: 0.06,
      fill: { color: p.border },
    });
    s.addText(p.name, {
      x: xPos, y: 1.5, w: 2.15, h: 0.45,
      fontSize: 16, fontFace: "Trebuchet MS", color: C.dark,
      bold: true, align: "center", margin: 0,
    });
    s.addText(p.price, {
      x: xPos, y: 2.0, w: 2.15, h: 0.6,
      fontSize: 32, fontFace: "Trebuchet MS", color: p.border,
      bold: true, align: "center", margin: 0,
    });
    s.addText(p.features, {
      x: xPos + 0.15, y: 2.7, w: 1.85, h: 1.2,
      fontSize: 12, fontFace: "Calibri", color: C.muted,
      align: "center", valign: "top", margin: 0,
    });
  });

  s.addText("Unit economics: LLM cost ~$0.15–0.30/campaign (Gemini Flash) → 95%+ gross margin", {
    x: 0.6, y: 4.4, w: 8.8, h: 0.5,
    fontSize: 14, fontFace: "Calibri", color: C.dark,
    italic: true, align: "center", margin: 0,
  });

  // ===== SLIDE 7: Competition =====
  s = pres.addSlide();
  s.background = { color: C.light };
  s.addText("Competitive Landscape", {
    x: 0.6, y: 0.3, w: 8, h: 0.7,
    fontSize: 36, fontFace: "Trebuchet MS", color: C.secondary, bold: true, margin: 0,
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.6, y: 1.0, w: 1.2, h: 0.06, fill: { color: C.primary },
  });

  const compHeaders = [
    { text: "Capability", options: { fill: { color: C.secondary }, color: C.white, bold: true, fontSize: 12, fontFace: "Calibri", align: "left" } },
    { text: "Uplane\n(YC F25)", options: { fill: { color: C.secondary }, color: C.white, bold: true, fontSize: 11, fontFace: "Calibri", align: "center" } },
    { text: "Rankai\n(YC S23)", options: { fill: { color: C.secondary }, color: C.white, bold: true, fontSize: 11, fontFace: "Calibri", align: "center" } },
    { text: "Sprites\n(YC W22)", options: { fill: { color: C.secondary }, color: C.white, bold: true, fontSize: 11, fontFace: "Calibri", align: "center" } },
    { text: "CampaignForge", options: { fill: { color: C.primary }, color: C.white, bold: true, fontSize: 11, fontFace: "Calibri", align: "center" } },
  ];

  const compRows = [
    ["Full-stack campaigns", "Ads only", "SEO only", "Acquisition", "Full pipeline"],
    ["Multi-agent visible to user", "Hidden", "Hidden", "Hidden", "Live dashboard"],
    ["Brand voice enforcement", "Basic", "No", "No", "Deep profiles"],
    ["Human-in-the-loop review", "No", "No", "No", "Built-in"],
    ["Multi-platform publishing", "Ad platforms", "Blog/web", "Varied", "Social-native"],
    ["Transparent AI pipeline", "Black box", "Black box", "Black box", "Open pipeline"],
  ];

  const cellOpts = (val, isLast) => {
    const isPositive = ["Full pipeline", "Live dashboard", "Deep profiles", "Built-in", "Social-native", "Open pipeline"].includes(val);
    const isNeg = ["No", "Hidden", "Black box"].includes(val);
    return {
      text: val,
      options: {
        fontSize: 11, fontFace: "Calibri",
        color: isLast ? (isPositive ? C.success : C.dark) : (isNeg ? C.primary : C.dark),
        bold: isLast && isPositive,
        align: "center",
        fill: { color: isLast ? "FFF5F5" : C.white },
      },
    };
  };

  const tableData = [compHeaders];
  compRows.forEach((row) => {
    tableData.push(row.map((val, i) => {
      if (i === 0) return { text: val, options: { fontSize: 11, fontFace: "Calibri", color: C.dark, bold: true, align: "left", fill: { color: C.white } } };
      return cellOpts(val, i === 4);
    }));
  });

  s.addTable(tableData, {
    x: 0.4, y: 1.2, w: 9.2,
    colW: [2.2, 1.6, 1.6, 1.6, 2.2],
    border: { pt: 0.5, color: "E5E7EB" },
    rowH: [0.55, 0.45, 0.45, 0.45, 0.45, 0.45, 0.45],
  });

  // ===== SLIDE 8: Unique Insight =====
  s = pres.addSlide();
  s.background = { color: C.secondary };
  s.addText("Our Unique Insight", {
    x: 0.6, y: 0.3, w: 8, h: 0.7,
    fontSize: 36, fontFace: "Trebuchet MS", color: C.white, bold: true, margin: 0,
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.6, y: 1.0, w: 1.2, h: 0.06, fill: { color: C.primary },
  });

  s.addImage({ data: icons.lightbulb, x: 4.25, y: 1.3, w: 1.5, h: 1.5 });

  s.addText([
    { text: '"Marketing agencies are teams, not individuals.', options: { italic: true, fontSize: 20 } },
  ], {
    x: 0.8, y: 3.0, w: 8.4, h: 0.6,
    fontFace: "Georgia", color: C.white, align: "center", margin: 0,
  });
  s.addText([
    { text: "Single-model AI tools fail because they try to do strategy, writing, SEO, ads, and QA with one prompt. CampaignForge mirrors how real agencies work — ", options: { fontSize: 16 } },
    { text: "specialized roles, parallel execution, quality gates", options: { fontSize: 16, bold: true, color: C.accent } },
    { text: ' — at 1/50th the cost and 100x the speed."', options: { fontSize: 16 } },
  ], {
    x: 0.8, y: 3.6, w: 8.4, h: 1.4,
    fontFace: "Calibri", color: C.white, align: "center", margin: 0,
  });

  // ===== SLIDE 9: Tech Stack =====
  s = pres.addSlide();
  s.background = { color: C.light };
  s.addText("Tech Stack & Cost Efficiency", {
    x: 0.6, y: 0.3, w: 8, h: 0.7,
    fontSize: 36, fontFace: "Trebuchet MS", color: C.secondary, bold: true, margin: 0,
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.6, y: 1.0, w: 1.2, h: 0.06, fill: { color: C.primary },
  });

  const techStack = [
    { layer: "Frontend", tech: "Next.js 14 → Vercel (edge)" },
    { layer: "Backend", tech: "FastAPI + LangGraph → Fly.io" },
    { layer: "Database", tech: "Neon PostgreSQL (serverless)" },
    { layer: "AI Brain", tech: "Claude Sonnet 4 (orchestrator)" },
    { layer: "AI Workers", tech: "Gemini 2.0 Flash (cost-optimized)" },
    { layer: "Payments", tech: "Stripe (subscriptions + metering)" },
    { layer: "Email", tech: "AgentMail (client reports)" },
  ];
  techStack.forEach((t, i) => {
    const yPos = 1.3 + i * 0.52;
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.6, y: yPos, w: 1.8, h: 0.42,
      fill: { color: C.secondary },
    });
    s.addText(t.layer, {
      x: 0.6, y: yPos, w: 1.8, h: 0.42,
      fontSize: 12, fontFace: "Calibri", color: C.white,
      bold: true, align: "center", valign: "middle", margin: 0,
    });
    s.addText(t.tech, {
      x: 2.6, y: yPos, w: 4.5, h: 0.42,
      fontSize: 13, fontFace: "Calibri", color: C.dark,
      valign: "middle", margin: 0,
    });
  });

  // Cost card
  s.addShape(pres.shapes.RECTANGLE, {
    x: 7.5, y: 1.3, w: 2.2, h: 3.6,
    fill: { color: C.dark }, shadow: mkShadow(),
  });
  s.addText("Infra Cost\nat 100 Users", {
    x: 7.5, y: 1.4, w: 2.2, h: 0.7,
    fontSize: 13, fontFace: "Calibri", color: C.muted,
    align: "center", margin: 0,
  });
  s.addText("< $50/mo", {
    x: 7.5, y: 2.2, w: 2.2, h: 0.7,
    fontSize: 28, fontFace: "Trebuchet MS", color: C.success,
    bold: true, align: "center", margin: 0,
  });
  s.addText("Fly.io: ~$15\nNeon: ~$0\nVercel: ~$0\nLLM: ~$0.20/run", {
    x: 7.6, y: 3.0, w: 2.0, h: 1.5,
    fontSize: 11, fontFace: "Calibri", color: C.white,
    margin: 0,
  });

  // ===== SLIDE 10: Traction & Roadmap =====
  s = pres.addSlide();
  s.background = { color: C.dark };
  s.addText("Roadmap to YC", {
    x: 0.6, y: 0.3, w: 8, h: 0.7,
    fontSize: 36, fontFace: "Trebuchet MS", color: C.white, bold: true, margin: 0,
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.6, y: 1.0, w: 1.2, h: 0.06, fill: { color: C.primary },
  });

  const phases = [
    { wk: "Week 1", phase: "Foundation", goal: "End-to-end working product, demo video", status: "done" },
    { wk: "Weeks 2–4", phase: "The Wedge", goal: "Publishing, scheduling, Stripe. 5 paying users.", status: "now" },
    { wk: "Weeks 5–8", phase: "Traction", goal: "$2K MRR, 20 paying users, analytics loop", status: "next" },
    { wk: "Weeks 9–14", phase: "Moats", goal: "Brand learning, agency-mode, API, $10K MRR", status: "next" },
    { wk: "Weeks 15–16", phase: "YC Apply", goal: "Polish metrics, record video, submit", status: "next" },
  ];
  phases.forEach((p, i) => {
    const yPos = 1.3 + i * 0.82;
    const statusColor = p.status === "done" ? C.success : (p.status === "now" ? C.primary : C.navy80);
    s.addShape(pres.shapes.RECTANGLE, {
      x: 0.6, y: yPos, w: 8.8, h: 0.7,
      fill: { color: statusColor, transparency: p.status === "next" ? 60 : 0 },
    });
    s.addText(p.wk, {
      x: 0.8, y: yPos, w: 1.8, h: 0.7,
      fontSize: 13, fontFace: "Calibri", color: C.white,
      bold: true, valign: "middle", margin: 0,
    });
    s.addText(p.phase, {
      x: 2.7, y: yPos, w: 2, h: 0.7,
      fontSize: 15, fontFace: "Trebuchet MS", color: C.white,
      bold: true, valign: "middle", margin: 0,
    });
    s.addText(p.goal, {
      x: 4.8, y: yPos, w: 4.4, h: 0.7,
      fontSize: 13, fontFace: "Calibri", color: C.white,
      valign: "middle", margin: 0,
    });
  });

  s.addText("Target: YC W2027 or S2027", {
    x: 0.6, y: 5.0, w: 8.8, h: 0.4,
    fontSize: 16, fontFace: "Calibri", color: C.accent,
    bold: true, align: "center", margin: 0,
  });

  // ===== SLIDE 11: The Ask =====
  s = pres.addSlide();
  s.background = { color: C.secondary };
  s.addText("The Ask", {
    x: 0.6, y: 0.3, w: 8, h: 0.7,
    fontSize: 36, fontFace: "Trebuchet MS", color: C.white, bold: true, margin: 0,
  });
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0.6, y: 1.0, w: 1.2, h: 0.06, fill: { color: C.primary },
  });

  s.addText("Raising $500K Pre-Seed", {
    x: 0.6, y: 1.3, w: 8.8, h: 0.7,
    fontSize: 28, fontFace: "Trebuchet MS", color: C.accent,
    bold: true, align: "center", margin: 0,
  });

  const funds = [
    { pct: "40%", area: "Engineering", desc: "Scale agent pipeline, platform integrations" },
    { pct: "30%", area: "Go-to-Market", desc: "Product Hunt launch, content marketing, cold outreach" },
    { pct: "20%", area: "Operations", desc: "Infrastructure, LLM costs, monitoring" },
    { pct: "10%", area: "Reserve", desc: "Buffer for iteration and unexpected opportunities" },
  ];
  funds.forEach((f, i) => {
    const yPos = 2.2 + i * 0.75;
    s.addShape(pres.shapes.RECTANGLE, {
      x: 1.5, y: yPos, w: 7, h: 0.6,
      fill: { color: C.navy80 },
    });
    s.addText(f.pct, {
      x: 1.5, y: yPos, w: 1.2, h: 0.6,
      fontSize: 22, fontFace: "Trebuchet MS", color: C.accent,
      bold: true, align: "center", valign: "middle", margin: 0,
    });
    s.addText(f.area, {
      x: 2.8, y: yPos, w: 2, h: 0.6,
      fontSize: 16, fontFace: "Calibri", color: C.white,
      bold: true, valign: "middle", margin: 0,
    });
    s.addText(f.desc, {
      x: 4.9, y: yPos, w: 3.5, h: 0.6,
      fontSize: 13, fontFace: "Calibri", color: C.white,
      valign: "middle", margin: 0, transparency: 20,
    });
  });

  s.addText("18 months runway → Path to $10K MRR before needing next round", {
    x: 0.6, y: 5.0, w: 8.8, h: 0.4,
    fontSize: 14, fontFace: "Calibri", color: C.muted,
    italic: true, align: "center", margin: 0,
  });

  // ===== SLIDE 12: Closing =====
  s = pres.addSlide();
  s.background = { color: C.dark };
  s.addShape(pres.shapes.RECTANGLE, {
    x: 0, y: 4.4, w: 10, h: 1.225, fill: { color: C.primary },
  });
  s.addImage({ data: icons.robot, x: 4.25, y: 0.6, w: 1.5, h: 1.5 });
  s.addText("Your entire marketing team.", {
    x: 0.5, y: 2.2, w: 9, h: 0.6,
    fontSize: 28, fontFace: "Trebuchet MS", color: C.white,
    bold: true, align: "center", margin: 0,
  });
  s.addText("One prompt. Five minutes. $49/month.", {
    x: 0.5, y: 2.8, w: 9, h: 0.6,
    fontSize: 24, fontFace: "Calibri", color: C.accent,
    bold: true, align: "center", margin: 0,
  });
  s.addText("Let's talk.", {
    x: 0.5, y: 3.5, w: 9, h: 0.5,
    fontSize: 20, fontFace: "Calibri", color: C.muted,
    align: "center", margin: 0,
  });
  s.addText("campaignforge.ai  |  hello@campaignforge.dev", {
    x: 1, y: 4.65, w: 8, h: 0.5,
    fontSize: 16, fontFace: "Calibri", color: C.dark,
    bold: true, align: "center", margin: 0,
  });

  // Write file
  const outputPath = "CampaignForge-Pitch-Deck.pptx";
  await pres.writeFile({ fileName: outputPath });
  console.log(`Pitch deck created: ${outputPath}`);
}

createDeck().catch(console.error);
