import { mkdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { runInNewContext } from "node:vm";

const ROOT = dirname(fileURLToPath(import.meta.url));
const SOURCE_BASE = "https://colors.xiaoxiaodong.ai";
const SOURCES = {
  images: `${SOURCE_BASE}/assets/data/images.js`,
  harmonies: `${SOURCE_BASE}/assets/data/harmonies.js`,
  harmonyUsage: `${SOURCE_BASE}/assets/data/harmony-usage.js`,
};

const UI_TOKEN_IDS = {
  surface: "733",
  surfaceWarm: "684",
  surfaceSoft: "682",
  text: "693",
  textStrong: "736",
  border: "691",
  mutedText: "690",
  primary: "741",
  secondary: "704",
  info: "666",
  successSoft: "683",
  success: "740",
  warning: "735",
  dangerSoft: "703",
  danger: "720",
  tableStripe: "717",
  correctionBase: "731",
};

async function fetchText(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to fetch ${url}: ${response.status} ${response.statusText}`);
  }
  return response.text();
}

function evaluateWindowAssignment(source, assignmentName) {
  const sandbox = { window: {} };
  runInNewContext(source, sandbox, { timeout: 5000 });
  const value = sandbox.window[assignmentName];
  if (!value) {
    throw new Error(`Could not evaluate window.${assignmentName}`);
  }
  return value;
}

function colorName(file) {
  return file.replace(/^\d+-/, "").replace(/\.png$/u, "");
}

function hexToRgb(hex) {
  const value = hex.replace("#", "");
  const number = Number.parseInt(value, 16);
  return {
    r: (number >> 16) & 255,
    g: (number >> 8) & 255,
    b: number & 255,
  };
}

function normalizeColor(image) {
  return {
    id: image.id,
    name: colorName(image.file),
    hex: image.hex,
    rgb: hexToRgb(image.hex),
    cmyk: image.cmyk,
    pinyin: image.pinyin,
    imagePath: `${SOURCE_BASE}/${image.path}`,
    file: image.file,
  };
}

function buildUiTokens(colorsById) {
  const tokens = {};
  for (const [tokenName, colorId] of Object.entries(UI_TOKEN_IDS)) {
    const color = colorsById.get(colorId);
    if (!color) {
      throw new Error(`Missing token color id ${colorId} for ${tokenName}`);
    }
    tokens[tokenName] = {
      colorId,
      name: color.name,
      hex: color.hex,
    };
  }
  return {
    name: "booking-screening-traditional",
    description: "A restrained traditional-color token set for booking form screening UI.",
    tokens,
    usage: {
      surface: "App background and large panels.",
      primary: "Main actions, active navigation, selected state.",
      danger: "Invalid source cells and blocking validation issues.",
      warning: "Parseable but uncertain source cells.",
      success: "Correction suggestions and applied fixes.",
      info: "Tooltips, secondary emphasis, neutral status.",
    },
  };
}

async function main() {
  await mkdir(ROOT, { recursive: true });

  const [imagesJs, harmoniesJs, harmonyUsageJs] = await Promise.all([
    fetchText(SOURCES.images),
    fetchText(SOURCES.harmonies),
    fetchText(SOURCES.harmonyUsage),
  ]);

  const project = evaluateWindowAssignment(imagesJs, "TRADITIONAL_COLOR_PROJECT");
  const images = evaluateWindowAssignment(imagesJs, "TRADITIONAL_COLOR_IMAGES");
  const harmonies = evaluateWindowAssignment(harmoniesJs, "TRADITIONAL_COLOR_HARMONIES");
  const harmonyUsage = evaluateWindowAssignment(harmonyUsageJs, "TRADITIONAL_COLOR_HARMONY_USAGE");

  const colors = images.map(normalizeColor);
  const colorsById = new Map(colors.map((color) => [color.id, color]));

  const metadata = {
    generatedAt: new Date().toISOString(),
    sourceBase: SOURCE_BASE,
    sourceUrls: SOURCES,
    sourceProject: project,
    colorCount: colors.length,
    licenseNote: "Source project is published by nevertoday/zhongguo-traditional-colors and described as MIT licensed on the website.",
  };

  await writeFile(join(ROOT, "metadata.json"), `${JSON.stringify(metadata, null, 2)}\n`, "utf8");
  await writeFile(join(ROOT, "colors.json"), `${JSON.stringify(colors, null, 2)}\n`, "utf8");
  await writeFile(join(ROOT, "harmonies.json"), `${JSON.stringify(harmonies, null, 2)}\n`, "utf8");
  await writeFile(join(ROOT, "harmony_usage.json"), `${JSON.stringify(harmonyUsage, null, 2)}\n`, "utf8");
  await writeFile(join(ROOT, "booking_screening_tokens.json"), `${JSON.stringify(buildUiTokens(colorsById), null, 2)}\n`, "utf8");

  console.log(JSON.stringify({ colorCount: colors.length, outputDir: ROOT }, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
