#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str, executable: bool = False) -> None:
    target = ROOT / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    if executable:
        target.chmod(target.stat().st_mode | 0o111)


def replace_once(path: str, old: str, new: str) -> None:
    content = read(path)
    count = content.count(old)
    if count != 1:
        raise RuntimeError(f"Expected exactly one match in {path}, found {count}")
    write(path, content.replace(old, new, 1))


# ---------------------------------------------------------------------------
# Correct Markdown and wiki/internal link resolution.
# ---------------------------------------------------------------------------
internal_links = r'''import { slugifyPageName } from "@/lib/markdown/wiki-links";
import type { TreeNode } from "@/types";

export interface ResolvedInternalLink {
  path: string;
  fragment: string | null;
}

type FlatPage = { path: string; name: string };

function flattenTree(nodes: TreeNode[]): FlatPage[] {
  const result: FlatPage[] = [];
  for (const node of nodes) {
    result.push({ path: node.path, name: node.name });
    if (node.children) result.push(...flattenTree(node.children));
  }
  return result;
}

function parentOf(pagePath: string): string {
  return pagePath.includes("/")
    ? pagePath.substring(0, pagePath.lastIndexOf("/"))
    : "";
}

export function normalizeVirtualPath(input: string): string | null {
  const parts: string[] = [];
  for (const segment of input.replace(/\\/g, "/").split("/")) {
    if (!segment || segment === ".") continue;
    if (segment === "..") {
      if (parts.length === 0) return null;
      parts.pop();
      continue;
    }
    parts.push(segment);
  }
  return parts.join("/");
}

function splitHref(href: string): {
  path: string;
  fragment: string | null;
  absolute: boolean;
} {
  const hashIndex = href.indexOf("#");
  const rawPath = hashIndex >= 0 ? href.slice(0, hashIndex) : href;
  const rawFragment = hashIndex >= 0 ? href.slice(hashIndex + 1) : "";
  const queryIndex = rawPath.indexOf("?");
  const pathWithoutQuery = queryIndex >= 0 ? rawPath.slice(0, queryIndex) : rawPath;
  const absolute = pathWithoutQuery.startsWith("/");

  let cleaned = pathWithoutQuery
    .replace(/\\/g, "/")
    .replace(/^\/+/, "")
    .replace(/\/+$/, "")
    .replace(/\.md$/i, "")
    .replace(/(?:^|\/)index$/i, "");

  try {
    cleaned = decodeURIComponent(cleaned);
  } catch {
    // Keep the original encoded value when it is not valid URI encoding.
  }

  let fragment: string | null = rawFragment || null;
  if (fragment) {
    try {
      fragment = decodeURIComponent(fragment);
    } catch {
      // Keep the original fragment.
    }
  }

  return { path: cleaned, fragment, absolute };
}

export function findPageBySlug(
  slug: string,
  currentPath: string | null,
  nodes: TreeNode[],
): string | null {
  const allPages = flattenTree(nodes);
  const lastSeg = (pagePath: string) => pagePath.split("/").pop() ?? pagePath;
  const matches = allPages.filter(
    (page) =>
      page.name === slug ||
      page.path.endsWith("/" + slug) ||
      slugifyPageName(lastSeg(page.path)) === slug,
  );

  if (matches.length === 0) return null;
  if (matches.length === 1) return matches[0].path;

  if (currentPath) {
    const sibling = matches.find(
      (match) => parentOf(match.path) === parentOf(currentPath),
    );
    if (sibling) return sibling.path;
  }

  return matches[0].path;
}

export function resolveInternalLink(
  href: string,
  currentPath: string | null,
  assetBase: string | null,
  nodes: TreeNode[],
): ResolvedInternalLink | null {
  const allPages = flattenTree(nodes);
  const parsed = splitHref(href);

  const findExact = (candidate: string | null): string | null => {
    if (!candidate) return null;
    return allPages.find((page) => page.path === candidate)?.path ?? null;
  };

  if (!parsed.path) {
    return currentPath
      ? { path: currentPath, fragment: parsed.fragment }
      : null;
  }

  if (parsed.absolute) {
    const match = findExact(normalizeVirtualPath(parsed.path));
    return match ? { path: match, fragment: parsed.fragment } : null;
  }

  // PageData.assetBase is the folder itself for index.md pages and the parent
  // folder for standalone .md pages. It is therefore the correct Markdown base.
  const base = assetBase ?? currentPath ?? "";
  const relativeCandidate = normalizeVirtualPath(
    base ? `${base}/${parsed.path}` : parsed.path,
  );
  const relativeMatch = findExact(relativeCandidate);
  if (relativeMatch) {
    return { path: relativeMatch, fragment: parsed.fragment };
  }

  // Preserve root-relative links written without a leading slash.
  const directMatch = findExact(normalizeVirtualPath(parsed.path));
  if (directMatch) {
    return { path: directMatch, fragment: parsed.fragment };
  }

  // Fuzzy fallback is safe only for a bare page name. Qualified broken paths
  // must not silently open an unrelated page with the same basename.
  if (!parsed.path.includes("/")) {
    const match = findPageBySlug(parsed.path, currentPath, nodes);
    return match ? { path: match, fragment: parsed.fragment } : null;
  }

  return null;
}
'''
write("src/lib/markdown/internal-links.ts", internal_links)

editor_path = "src/components/editor/editor.tsx"
replace_once(
    editor_path,
    'import { slugifyPageName } from "@/lib/markdown/wiki-links";\n',
    'import { findPageBySlug, resolveInternalLink } from "@/lib/markdown/internal-links";\n',
)
replace_once(editor_path, 'import type { TreeNode } from "@/types";\n', '')
old_helpers = r'''function flattenTree(nodes: TreeNode[]): { path: string; name: string }[] {
  const result: { path: string; name: string }[] = [];
  for (const node of nodes) {
    result.push({ path: node.path, name: node.name });
    if (node.children) result.push(...flattenTree(node.children));
  }
  return result;
}

function findPageBySlug(slug: string, currentPath: string | null, nodes: TreeNode[]): string | null {
  const allPages = flattenTree(nodes);
  // The slug matches the last segment of the path. Native pages are stored with
  // slug filenames, so an exact match works; imported pages (e.g. Notion) keep
  // human names ("Day 1-100 Build 👩🏻‍💻"), so also match when the last segment
  // *slugifies to* the target slug.
  const lastSeg = (p: string) => p.split("/").pop() ?? p;
  const parentOf = (p: string) => (p.includes("/") ? p.substring(0, p.lastIndexOf("/")) : "");
  const matches = allPages.filter(
    (p) =>
      p.name === slug ||
      p.path.endsWith("/" + slug) ||
      slugifyPageName(lastSeg(p.path)) === slug
  );
  if (matches.length === 0) return null;
  if (matches.length === 1) return matches[0].path;

  // Prefer sibling pages (same parent directory as current page)
  if (currentPath) {
    const parentDir = parentOf(currentPath);
    const sibling = matches.find((m) => parentOf(m.path) === parentDir);
    if (sibling) return sibling.path;
  }
  return matches[0].path;
}

'''
replace_once(editor_path, old_helpers, '')
old_resolver = r'''function resolveInternalLink(
  href: string,
  currentPath: string | null,
  nodes: TreeNode[]
): string | null {
  const allPages = flattenTree(nodes);

  // Clean up the href: strip .md extension, leading ./ or /
  const linkPath = href
    .replace(/\.md$/, "")
    .replace(/^\.\//, "")
    .replace(/^\//, "");

  // 1. Try as absolute path (exact match in tree)
  const exactMatch = allPages.find((p) => p.path === linkPath);
  if (exactMatch) return exactMatch.path;

  // 2. Try relative to current page's directory
  if (currentPath) {
    const parentDir = currentPath.includes("/")
      ? currentPath.substring(0, currentPath.lastIndexOf("/"))
      : "";
    const relativePath = parentDir ? parentDir + "/" + linkPath : linkPath;
    const relMatch = allPages.find((p) => p.path === relativePath);
    if (relMatch) return relMatch.path;
  }

  // 3. Try matching by last segment (slug-style lookup)
  const slug = linkPath.includes("/") ? linkPath.split("/").pop()! : linkPath;
  return findPageBySlug(slug, currentPath, nodes);
}

'''
replace_once(editor_path, old_resolver, '')
old_navigate = r'''function navigateToPage(
  targetPath: string,
  selectPage: (path: string) => void,
  expandPath: (path: string) => void
) {
  const parts = targetPath.split("/");
  for (let i = 1; i < parts.length; i++) {
    expandPath(parts.slice(0, i).join("/"));
  }
  selectPage(targetPath);
  useEditorStore.getState().loadPage(targetPath);
  // Scroll editor container to top
  setTimeout(() => {
    document.querySelector("[data-editor-scroll]")?.scrollTo(0, 0);
  }, 0);
}
'''
new_navigate = r'''function scrollToPageFragment(fragment: string, attempts = 20) {
  const element = document.getElementById(fragment);
  if (element) {
    element.scrollIntoView({ behavior: "smooth", block: "start" });
    window.history.replaceState(
      null,
      "",
      `${window.location.pathname}#${encodeURIComponent(fragment)}`,
    );
    return;
  }
  if (attempts > 0) {
    setTimeout(() => scrollToPageFragment(fragment, attempts - 1), 50);
  }
}

function navigateToPage(
  targetPath: string,
  selectPage: (path: string) => void,
  expandPath: (path: string) => void,
  fragment: string | null = null,
) {
  const parts = targetPath.split("/");
  for (let i = 1; i < parts.length; i++) {
    expandPath(parts.slice(0, i).join("/"));
  }
  selectPage(targetPath);
  void useEditorStore.getState().loadPage(targetPath).then(() => {
    if (fragment) {
      scrollToPageFragment(fragment);
      return;
    }
    document.querySelector("[data-editor-scroll]")?.scrollTo(0, 0);
  });
}
'''
replace_once(editor_path, old_navigate, new_navigate)
old_click = r'''          const { nodes, selectPage, expandPath } = useTreeStore.getState();
          const activePath = useEditorStore.getState().currentPath;

          // Resolve the link target to a KB page path
          const targetPath = resolveInternalLink(href, activePath, nodes);
          if (targetPath) {
            navigateToPage(targetPath, selectPage, expandPath);
          }
'''
new_click = r'''          const { nodes, selectPage, expandPath } = useTreeStore.getState();
          const {
            currentPath: activePath,
            assetBase: activeBase,
          } = useEditorStore.getState();

          // Resolve using real Markdown semantics. assetBase is the folder for
          // index.md pages and the parent folder for standalone .md pages.
          const target = resolveInternalLink(
            href,
            activePath,
            activeBase,
            nodes,
          );
          if (target) {
            navigateToPage(
              target.path,
              selectPage,
              expandPath,
              target.fragment,
            );
          }
'''
replace_once(editor_path, old_click, new_click)

# Do not rewrite page links beginning with ./ as assets during Markdown render.
to_html_path = "src/lib/markdown/to-html.ts"
old_relative = r'''/**
 * Rewrite relative URLs (./file.pdf, ./image.png) to /api/assets/{pagePath}/file
 * and convert PDF links to inline embedded viewers.
 * Applies to href, src, and data-src attributes (the last is used by embed blocks).
 */
function resolveRelativeUrls(html: string, pagePath: string): string {
  const dirPath = pagePath;

  html = html.replace(
    /href="\.\/([^"]+)"/g,
    (_match, file: string) => `href="/api/assets/${dirPath}/${file}"`
  );

  html = html.replace(
    /src="\.\/([^"]+)"/g,
    (_match, file: string) => `src="/api/assets/${dirPath}/${file}"`
  );

  html = html.replace(
    /data-src="\.\/([^"]+)"/g,
    (_match, file: string) => `data-src="/api/assets/${dirPath}/${file}"`
  );

  // Agents routinely write bare relative refs (`![x](image.jpg)`, no `./`).
  // Rewrite those for src/data-src too — a relative media src can only mean a
  // page asset. Skip schemes (https:, data:), absolute paths (incl. already
  // rewritten /api/assets/…), protocol-relative URLs, anchors, and queries.
  // href is deliberately NOT given this treatment: a bare relative href is
  // usually a page-to-page link, not an asset.
  html = html.replace(
    /(?<![\w-])(src|data-src)="(?![a-z][a-z0-9+.-]*:)(?![/#?])([^"]+)"/gi,
    (_match, attr: string, file: string) => `${attr}="/api/assets/${dirPath}/${file}"`
  );

  // Mark PDF links with a data attribute so the editor can handle them
  html = html.replace(
    /<a([^>]*?)href="(\/api\/assets\/[^"]+\.pdf)"([^>]*?)>/gi,
    (_match, before: string, url: string, after: string) => {
      return `<a${before}href="${url}"${after} data-pdf-link="true">`;
    }
  );

  return html;
}
'''
new_relative = r'''const ASSET_LINK_EXTENSIONS = new Set([
  ".pdf", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".avif",
  ".mp4", ".webm", ".mov", ".m4v", ".mp3", ".wav", ".ogg", ".m4a",
  ".docx", ".xlsx", ".xlsm", ".pptx", ".csv", ".zip", ".tex", ".latex",
]);

function normalizeRelativeAssetPath(pagePath: string, file: string): string {
  const parts: string[] = [];
  for (const segment of `${pagePath}/${file}`.replace(/\\/g, "/").split("/")) {
    if (!segment || segment === ".") continue;
    if (segment === "..") {
      parts.pop();
      continue;
    }
    parts.push(segment);
  }
  return parts.join("/");
}

function isRelativeAssetHref(href: string): boolean {
  const clean = href.split(/[?#]/, 1)[0].replace(/\/+$/, "");
  const dot = clean.lastIndexOf(".");
  return dot >= 0 && ASSET_LINK_EXTENSIONS.has(clean.slice(dot).toLowerCase());
}

/**
 * Rewrite relative asset URLs to /api/assets while preserving Markdown page
 * links for the editor's internal-link resolver. Previously every `./...` href
 * was treated as an asset, which made `./folder/` navigation impossible.
 */
function resolveRelativeUrls(html: string, pagePath: string): string {
  html = html.replace(/href="([^"]+)"/g, (match, href: string) => {
    if (
      !href ||
      href.startsWith("#") ||
      href.startsWith("/") ||
      href.startsWith("//") ||
      /^[a-z][a-z0-9+.-]*:/i.test(href) ||
      !isRelativeAssetHref(href)
    ) {
      return match;
    }
    const assetPath = normalizeRelativeAssetPath(pagePath, href);
    return `href="/api/assets/${assetPath}"`;
  });

  html = html.replace(
    /(?<![\w-])(src|data-src)="(?![a-z][a-z0-9+.-]*:)(?![/#?])([^"]+)"/gi,
    (_match, attr: string, file: string) => {
      const assetPath = normalizeRelativeAssetPath(pagePath, file);
      return `${attr}="/api/assets/${assetPath}"`;
    },
  );

  html = html.replace(
    /<a([^>]*?)href="(\/api\/assets\/[^"]+\.pdf)"([^>]*?)>/gi,
    (_match, before: string, url: string, after: string) =>
      `<a${before}href="${url}"${after} data-pdf-link="true">`,
  );

  return html;
}
'''
replace_once(to_html_path, old_relative, new_relative)

# ---------------------------------------------------------------------------
# Correct SemVer ordering for Good Place prerelease versions.
# ---------------------------------------------------------------------------
version_utils = r'''interface ParsedSemver {
  core: [number, number, number];
  prerelease: string[];
}

function parseSemver(input: string): ParsedSemver | null {
  const match = input
    .trim()
    .replace(/^v/, "")
    .match(/^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$/);
  if (!match) return null;
  return {
    core: [
      Number.parseInt(match[1], 10),
      Number.parseInt(match[2], 10),
      Number.parseInt(match[3], 10),
    ],
    prerelease: match[4] ? match[4].split(".") : [],
  };
}

function comparePrerelease(left: string[], right: string[]): number {
  if (left.length === 0 && right.length === 0) return 0;
  if (left.length === 0) return 1;
  if (right.length === 0) return -1;

  const length = Math.max(left.length, right.length);
  for (let index = 0; index < length; index += 1) {
    const leftPart = left[index];
    const rightPart = right[index];
    if (leftPart === undefined) return -1;
    if (rightPart === undefined) return 1;
    if (leftPart === rightPart) continue;

    const leftNumeric = /^\d+$/.test(leftPart);
    const rightNumeric = /^\d+$/.test(rightPart);
    if (leftNumeric && rightNumeric) {
      return Number(leftPart) > Number(rightPart) ? 1 : -1;
    }
    if (leftNumeric !== rightNumeric) return leftNumeric ? -1 : 1;
    return leftPart > rightPart ? 1 : -1;
  }
  return 0;
}

export function compareVersions(left: string, right: string): number {
  const leftVersion = parseSemver(left);
  const rightVersion = parseSemver(right);
  if (!leftVersion || !rightVersion) {
    return left.localeCompare(right, undefined, { numeric: true });
  }

  for (let index = 0; index < 3; index += 1) {
    if (leftVersion.core[index] !== rightVersion.core[index]) {
      return leftVersion.core[index] > rightVersion.core[index] ? 1 : -1;
    }
  }
  return comparePrerelease(leftVersion.prerelease, rightVersion.prerelease);
}

export function isStableVersion(version: string): boolean {
  const parsed = parseSemver(version);
  return parsed !== null && parsed.prerelease.length === 0;
}
'''
write("src/lib/system/version-utils.ts", version_utils)

# ---------------------------------------------------------------------------
# Make release metadata deterministic and fork-safe.
# ---------------------------------------------------------------------------
generator_path = "scripts/generate-release-manifest.mjs"
replace_once(
    generator_path,
    '''// Prefer an explicit --repository-url, then the CI repo (GITHUB_REPOSITORY),
// then the canonical repo. Keeps generated URLs correct after the org move
// (hilash/cabinet → cabinetai/cabinet) without hardcoding.
const repositoryUrl = (
  readArg("repository-url") ||
  (process.env.GITHUB_REPOSITORY && `https://github.com/${process.env.GITHUB_REPOSITORY}`) ||
  "https://github.com/cabinetai/cabinet"
).replace(/\.git$/, "");
''',
    '''function normalizeRepositoryUrl(value) {
  return value?.replace(/^git\+/, "").replace(/\.git$/, "");
}

const packageRepository =
  typeof packageJson.repository === "string"
    ? packageJson.repository
    : packageJson.repository?.url;

// Explicit CLI input wins, then the Actions repository, then package.json.
// This keeps local fork releases from silently pointing back at upstream.
const repositoryUrl = normalizeRepositoryUrl(
  readArg("repository-url") ||
    (process.env.GITHUB_REPOSITORY &&
      `https://github.com/${process.env.GITHUB_REPOSITORY}`) ||
    packageRepository ||
    "https://github.com/cabinetai/cabinet",
);
const publishesUpstreamNpm = repositoryUrl === "https://github.com/cabinetai/cabinet";
''',
)
replace_once(
    generator_path,
    '''  npmPackage: "create-cabinet",
  createCabinetVersion: version,
  cabinetaiPackage: "cabinetai",
  cabinetaiVersion: version,
''',
    '''  ...(publishesUpstreamNpm
    ? {
        npmPackage: "create-cabinet",
        createCabinetVersion: version,
        cabinetaiPackage: "cabinetai",
        cabinetaiVersion: version,
      }
    : {}),
''',
)

manifest_path = ROOT / "cabinet-release.json"
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
repo_url = "https://github.com/souljorje/cabinet"
manifest["repositoryUrl"] = repo_url
manifest["releaseNotesUrl"] = f'{repo_url}/releases/tag/{manifest["gitTag"]}'
manifest["sourceTarballUrl"] = f'{repo_url}/archive/refs/tags/{manifest["gitTag"]}.tar.gz'
for bundle in manifest.get("appBundles", {}).values():
    bundle["url"] = f'{repo_url}/releases/download/{manifest["gitTag"]}/{bundle["assetName"]}'
for key in ["npmPackage", "createCabinetVersion", "cabinetaiPackage", "cabinetaiVersion"]:
    manifest.pop(key, None)
write("cabinet-release.json", json.dumps(manifest, indent=2) + "\n")

# Keep fallback manifests from advertising unpublished fork npm packages.
release_manifest_path = "src/lib/system/release-manifest.ts"
replace_once(
    release_manifest_path,
    '''    npmPackage: "create-cabinet",
    createCabinetVersion: version,
    cabinetaiPackage: "cabinetai",
    cabinetaiVersion: version,
''',
    '''    ...(repositoryUrl === "https://github.com/cabinetai/cabinet"
      ? {
          npmPackage: "create-cabinet",
          createCabinetVersion: version,
          cabinetaiPackage: "cabinetai",
          cabinetaiVersion: version,
        }
      : {}),
''',
)

# ---------------------------------------------------------------------------
# Partner-safe workspace sync and machine-local credentials.
# ---------------------------------------------------------------------------
workspace_sync = r'''/* eslint-disable @typescript-eslint/no-require-imports */
"use strict";

const { execFileSync, spawn } = require("child_process");
const fs = require("fs");
const path = require("path");

function statusPath(dataDir) {
  return path.join(dataDir, ".cabinet-state", "workspace-sync.json");
}

function writeStatus(dataDir, status) {
  try {
    const file = statusPath(dataDir);
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(
      file,
      `${JSON.stringify({ ...status, updatedAt: new Date().toISOString() }, null, 2)}\n`,
      "utf8",
    );
  } catch (error) {
    console.warn("workspace-sync: failed to persist status", error);
  }
}

function git(dataDir, ...args) {
  return execFileSync("git", ["-C", dataDir, ...args], {
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  }).trim();
}

function safeChildEnv(extra = {}) {
  const names = [
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "SSH_AUTH_SOCK",
    "GIT_ASKPASS", "GIT_SSH", "GIT_SSH_COMMAND", "HTTPS_PROXY",
    "HTTP_PROXY", "NO_PROXY", "LANG", "LC_ALL",
  ];
  const env = {};
  for (const name of names) {
    if (process.env[name]) env[name] = process.env[name];
  }
  return { ...env, ...extra };
}

function resolveWorkspaceSync(dataDir, env = process.env) {
  const scriptPath = path.join(dataDir, "scripts", "cabinet-sync.mjs");
  if (!fs.existsSync(scriptPath)) return null;

  try {
    const stat = fs.lstatSync(scriptPath);
    if (!stat.isFile() || stat.isSymbolicLink()) {
      throw new Error("sync script must be a regular, non-symlink file");
    }
    const dataReal = fs.realpathSync(dataDir);
    const scriptReal = fs.realpathSync(scriptPath);
    const relative = path.relative(dataReal, scriptReal);
    if (relative.startsWith("..") || path.isAbsolute(relative)) {
      throw new Error("sync script resolves outside the selected workspace");
    }

    const gitDir = git(dataDir, "rev-parse", "--absolute-git-dir");
    const branch =
      env.CABINET_SYNC_BRANCH || git(dataDir, "branch", "--show-current") || "main";
    return {
      branch,
      headRef: path.join(gitDir, "refs", "heads", ...branch.split("/")),
      scriptPath,
    };
  } catch (error) {
    console.warn("workspace-sync: workspace is not sync-ready", error);
    writeStatus(dataDir, {
      state: "error",
      reason: "configuration-failed",
      error: error instanceof Error ? error.message : String(error),
    });
    return null;
  }
}

function createWorkspaceSyncSupervisor({
  dataDir,
  nodeCommand,
  nodeEnv = {},
  intervalMs = Number(process.env.CABINET_SYNC_INTERVAL_MS || 30_000),
}) {
  let activeChild = null;
  let activeSync = null;
  let configuration = null;
  let started = false;
  let timer = null;

  function sync() {
    if (!started) return Promise.resolve();
    if (activeSync) return activeSync;

    writeStatus(dataDir, {
      state: "syncing",
      branch: configuration.branch,
      lastAttemptAt: new Date().toISOString(),
    });

    activeSync = new Promise((resolve) => {
      let settled = false;
      const finish = (status) => {
        if (settled) return;
        settled = true;
        writeStatus(dataDir, status);
        resolve();
      };

      const child = spawn(nodeCommand, [configuration.scriptPath, "once"], {
        cwd: dataDir,
        env: safeChildEnv({
          ...nodeEnv,
          CABINET_SYNC_REPO_ROOT: dataDir,
          CABINET_SYNC_BRANCH: configuration.branch,
          CABINET_SYNC_ASSUME_RUNNING: "1",
        }),
        stdio: "inherit",
      });
      activeChild = child;

      child.once("error", (error) => {
        console.warn(`workspace-sync: ${error.message}; will retry`);
        finish({
          state: "error",
          branch: configuration.branch,
          reason: "spawn-failed",
          error: error.message,
        });
      });
      child.once("exit", (code) => {
        if (code && code !== 0) {
          console.warn(`workspace-sync: exited with code ${code}; will retry`);
          finish({
            state: "error",
            branch: configuration.branch,
            reason: "sync-failed",
            error: `Sync exited with code ${code}`,
          });
          return;
        }
        finish({
          state: "synced",
          branch: configuration.branch,
          lastSuccessAt: new Date().toISOString(),
        });
      });
    }).finally(() => {
      activeChild = null;
      activeSync = null;
    });

    return activeSync;
  }

  function start() {
    if (started) return true;
    configuration = resolveWorkspaceSync(dataDir);
    if (!configuration) {
      if (!fs.existsSync(path.join(dataDir, "scripts", "cabinet-sync.mjs"))) {
        writeStatus(dataDir, { state: "disabled", reason: "script-missing" });
      }
      return false;
    }

    started = true;
    void sync();
    timer = setInterval(() => void sync(), intervalMs);
    fs.watchFile(configuration.headRef, { interval: 500 }, (current, previous) => {
      if (current.mtimeMs !== previous.mtimeMs) void sync();
    });
    console.log(`workspace-sync: supervising ${dataDir} on ${configuration.branch}`);
    return true;
  }

  async function stop({ waitMs = 5_000 } = {}) {
    if (!started) return activeSync || Promise.resolve();
    started = false;
    if (timer) clearInterval(timer);
    timer = null;
    if (configuration) fs.unwatchFile(configuration.headRef);
    configuration = null;

    if (!activeSync) return;
    let timedOut = false;
    await Promise.race([
      activeSync,
      new Promise((resolve) =>
        setTimeout(() => {
          timedOut = true;
          resolve();
        }, waitMs),
      ),
    ]);
    if (timedOut && activeChild && !activeChild.killed) {
      activeChild.kill("SIGTERM");
    }
  }

  return { start, stop, sync };
}

module.exports = {
  createWorkspaceSyncSupervisor,
  resolveWorkspaceSync,
  safeChildEnv,
  statusPath,
};
'''
write("electron/workspace-sync.cjs", workspace_sync)

managed_data = r'''/* eslint-disable @typescript-eslint/no-require-imports */
const fs = require("node:fs");
const path = require("node:path");

function shouldSeedDefaultContent(managedDataDir) {
  if (fs.existsSync(path.join(managedDataDir, ".cabinet"))) return false;
  try {
    const meaningfulEntries = fs
      .readdirSync(managedDataDir)
      .filter((entry) => entry !== ".DS_Store");
    return meaningfulEntries.length === 0;
  } catch {
    return true;
  }
}

module.exports = {
  shouldSeedDefaultContent,
};
'''
write("electron/managed-data.cjs", managed_data)

# Environment keys are machine-local in Electron, while source mode retains the
# existing managed-data default.
cabinet_env_path = "src/lib/runtime/cabinet-env.ts"
replace_once(
    cabinet_env_path,
    '''export function cabinetEnvPath(): string {
  return path.join(getManagedDataDir(), CABINET_ENV_FILENAME);
}
''',
    '''export function cabinetEnvPath(): string {
  const configured = process.env.CABINET_ENV_PATH?.trim();
  return configured
    ? path.resolve(configured)
    : path.join(getManagedDataDir(), CABINET_ENV_FILENAME);
}
''',
)
replace_once(
    cabinet_env_path,
    '''function ensureGitignoreCovers(): void {
''',
    '''function ensureGitignoreCovers(): void {
  const file = cabinetEnvPath();
  const managedDataDir = getManagedDataDir();
  const relative = path.relative(managedDataDir, file);
  if (relative.startsWith("..") || path.isAbsolute(relative)) return;
''',
)
replace_once(
    cabinet_env_path,
    '''function atomicWrite(file: string, contents: string): void {
  const dir = path.dirname(file);
''',
    '''function atomicWrite(file: string, contents: string): void {
  const dir = path.dirname(file);
  fs.mkdirSync(dir, { recursive: true });
''',
)

main_path = "electron/main.cjs"
replace_once(main_path, 'const fs = require("fs");\n', 'const fs = require("fs");\nconst crypto = require("crypto");\n')
replace_once(
    main_path,
    '''function workspaceSyncNode() {
''',
    '''function workspaceEnvPath() {
  const workspaceKey = crypto
    .createHash("sha256")
    .update(path.resolve(managedDataDir))
    .digest("hex")
    .slice(0, 16);
  return path.join(
    userDataDir,
    "workspace-secrets",
    workspaceKey,
    ".cabinet.env",
  );
}

function workspaceSyncNode() {
''',
)
replace_once(
    main_path,
    '''    CABINET_USER_DATA: userDataDir,
    CABINET_APP_PORT: String(appPort),
''',
    '''    CABINET_USER_DATA: userDataDir,
    CABINET_ENV_PATH: workspaceEnvPath(),
    CABINET_APP_PORT: String(appPort),
''',
)

# ---------------------------------------------------------------------------
# Tests and maintenance tooling.
# ---------------------------------------------------------------------------
internal_link_tests = r'''import assert from "node:assert/strict";
import test from "node:test";
import { resolveInternalLink } from "@/lib/markdown/internal-links";
import type { TreeNode } from "@/types";

const nodes: TreeNode[] = [
  {
    name: "good-place-os",
    path: "good-place-os",
    type: "cabinet",
    children: [
      {
        name: "acquisitions",
        path: "good-place-os/acquisitions",
        type: "directory",
        children: [
          { name: "thesis.md", path: "good-place-os/acquisitions/thesis", type: "file" },
          { name: "target-profile.md", path: "good-place-os/acquisitions/target-profile", type: "file" },
          { name: "locations", path: "good-place-os/acquisitions/locations", type: "directory" },
          { name: "pipeline", path: "good-place-os/acquisitions/pipeline", type: "directory" },
          { name: "diligence", path: "good-place-os/acquisitions/diligence", type: "directory" },
        ],
      },
      {
        name: "research",
        path: "good-place-os/research",
        type: "directory",
        children: [
          { name: "acquisitions", path: "good-place-os/research/acquisitions", type: "directory" },
          { name: "status.md", path: "good-place-os/research/status", type: "file" },
        ],
      },
    ],
  },
];

function resolve(href: string, current = "good-place-os/acquisitions", base = current) {
  return resolveInternalLink(href, current, base, nodes);
}

test("resolves folder links from an index page", () => {
  assert.deepEqual(resolve("./locations/"), {
    path: "good-place-os/acquisitions/locations",
    fragment: null,
  });
});

test("resolves parent traversal and folder index links", () => {
  assert.equal(
    resolve("../research/acquisitions/")?.path,
    "good-place-os/research/acquisitions",
  );
  assert.equal(
    resolve("./locations/index.md")?.path,
    "good-place-os/acquisitions/locations",
  );
});

test("uses assetBase for standalone markdown pages", () => {
  assert.equal(
    resolveInternalLink(
      "./target-profile.md",
      "good-place-os/acquisitions/thesis",
      "good-place-os/acquisitions",
      nodes,
    )?.path,
    "good-place-os/acquisitions/target-profile",
  );
});

test("preserves cross-page heading fragments", () => {
  assert.deepEqual(resolve("./thesis.md#seller-financing"), {
    path: "good-place-os/acquisitions/thesis",
    fragment: "seller-financing",
  });
});

test("does not fuzzy-match a broken qualified path", () => {
  assert.equal(resolve("../missing/status.md"), null);
});
'''
write("test/internal-links.test.ts", internal_link_tests)

version_tests = r'''import assert from "node:assert/strict";
import test from "node:test";
import { compareVersions, isStableVersion } from "@/lib/system/version-utils";

test("orders numeric Good Place prerelease identifiers", () => {
  assert.equal(compareVersions("0.5.3-gp.10", "0.5.3-gp.9"), 1);
  assert.equal(compareVersions("0.5.3-gp.2", "0.5.3-gp.10"), -1);
});

test("orders base and prerelease versions using SemVer rules", () => {
  assert.equal(compareVersions("0.5.3", "0.5.3-gp.10"), 1);
  assert.equal(compareVersions("0.5.4-gp.1", "0.5.3-gp.99"), 1);
  assert.equal(isStableVersion("0.5.3-gp.2"), false);
});
'''
write("test/version-utils-fork.test.ts", version_tests)

# Extend managed data coverage.
managed_test_path = "test/managed-data.test.ts"
managed_tests = read(managed_test_path)
managed_tests += r'''

test("starter content is not seeded into an unrelated non-empty directory", () => {
  const managedDataDir = fs.mkdtempSync(
    path.join(os.tmpdir(), "cabinet-nonempty-")
  );

  try {
    fs.writeFileSync(path.join(managedDataDir, "existing.md"), "keep me");
    assert.equal(shouldSeedDefaultContent(managedDataDir), false);
  } finally {
    fs.rmSync(managedDataDir, { recursive: true, force: true });
  }
});
'''
write(managed_test_path, managed_tests)

# Add status and environment assertions to workspace sync coverage.
workspace_test_path = "test/workspace-sync.test.ts"
workspace_tests = read(workspace_test_path)
workspace_tests = workspace_tests.replace(
    '''  resolveWorkspaceSync,
} = require("../electron/workspace-sync.cjs");
''',
    '''  resolveWorkspaceSync,
  safeChildEnv,
  statusPath,
} = require("../electron/workspace-sync.cjs");
''',
)
workspace_tests += r'''

test("workspace sync child environment does not inherit provider secrets", () => {
  const previous = process.env.OPENAI_API_KEY;
  process.env.OPENAI_API_KEY = "must-not-leak";
  try {
    const env = safeChildEnv({ CABINET_SYNC_BRANCH: "main" });
    assert.equal(env.OPENAI_API_KEY, undefined);
    assert.equal(env.CABINET_SYNC_BRANCH, "main");
  } finally {
    if (previous === undefined) delete process.env.OPENAI_API_KEY;
    else process.env.OPENAI_API_KEY = previous;
  }
});

test("workspace sync writes a disabled status when no script is configured", () => {
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "cabinet-sync-status-"));
  const supervisor = createWorkspaceSyncSupervisor({
    dataDir,
    nodeCommand: process.execPath,
  });
  try {
    assert.equal(supervisor.start(), false);
    const status = JSON.parse(fs.readFileSync(statusPath(dataDir), "utf8"));
    assert.equal(status.state, "disabled");
    assert.equal(status.reason, "script-missing");
  } finally {
    fs.rmSync(dataDir, { recursive: true, force: true });
  }
});
'''
write(workspace_test_path, workspace_tests)

fork_invariants = r'''#!/usr/bin/env node
import fs from "node:fs";

function readJson(path) {
  return JSON.parse(fs.readFileSync(path, "utf8"));
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

const pkg = readJson("package.json");
const manifest = readJson("cabinet-release.json");
const repo = "https://github.com/souljorje/cabinet";

assert(pkg.productName === "Good Place Cabinet", "productName must identify the fork");
assert(pkg.repository?.url === `git+${repo}.git`, "package repository must point to the fork");
assert(manifest.version === pkg.version, "manifest and package versions must match");
assert(manifest.repositoryUrl === repo, "manifest repository must point to the fork");
assert(manifest.releaseNotesUrl.startsWith(`${repo}/releases/`), "release notes URL must point to the fork");
assert(manifest.sourceTarballUrl.startsWith(`${repo}/archive/`), "source tarball URL must point to the fork");
for (const bundle of Object.values(manifest.appBundles || {})) {
  assert(bundle.url.startsWith(`${repo}/releases/`), `bundle URL points elsewhere: ${bundle.url}`);
}
for (const key of ["npmPackage", "createCabinetVersion", "cabinetaiPackage", "cabinetaiVersion"]) {
  assert(!(key in manifest), `${key} must be absent because the fork does not publish upstream npm packages`);
}
const readme = fs.readFileSync("README.md", "utf8");
assert(readme.includes("Good Place distribution"), "README must explain that this is the Good Place fork");
const releaseWorkflow = fs.readFileSync(".github/workflows/release.yml", "utf8");
assert(
  (releaseWorkflow.match(/github\.repository == 'cabinetai\/cabinet'/g) || []).length >= 2,
  "fork releases must keep upstream npm publishing disabled",
);
console.log("Fork invariants passed");
'''
write("scripts/check-fork-invariants.mjs", fork_invariants, executable=True)

prepare_release = r'''#!/usr/bin/env node
import { execFileSync } from "node:child_process";
import fs from "node:fs";

const version = process.argv[2];
if (!/^\d+\.\d+\.\d+-gp\.\d+$/.test(version || "")) {
  console.error("Usage: npm run fork:release:prepare -- 0.5.4-gp.1");
  process.exit(1);
}

const dirty = execFileSync("git", ["status", "--porcelain"], { encoding: "utf8" }).trim();
if (dirty) {
  console.error("Release preparation requires a clean working tree.");
  process.exit(1);
}

for (const file of ["package.json", "package-lock.json"]) {
  const json = JSON.parse(fs.readFileSync(file, "utf8"));
  json.version = version;
  if (json.packages?.[""]) json.packages[""].version = version;
  fs.writeFileSync(file, `${JSON.stringify(json, null, 2)}\n`);
}

execFileSync(
  process.execPath,
  [
    "scripts/generate-release-manifest.mjs",
    "--version",
    version,
    "--tag",
    `v${version}`,
    "--repository-url",
    "https://github.com/souljorje/cabinet",
  ],
  { stdio: "inherit" },
);
execFileSync(process.execPath, ["scripts/check-fork-invariants.mjs"], { stdio: "inherit" });
console.log(`Prepared Good Place Cabinet ${version}. Review, commit, and tag v${version}.`);
'''
write("scripts/prepare-good-place-release.mjs", prepare_release, executable=True)

sync_upstream = r'''#!/usr/bin/env bash
set -euo pipefail

UPSTREAM_REMOTE="${UPSTREAM_REMOTE:-upstream}"
UPSTREAM_BRANCH="${UPSTREAM_BRANCH:-main}"
MIRROR_BRANCH="${MIRROR_BRANCH:-upstream-main}"

if ! git remote get-url "$UPSTREAM_REMOTE" >/dev/null 2>&1; then
  git remote add "$UPSTREAM_REMOTE" https://github.com/cabinetai/cabinet.git
fi

git fetch "$UPSTREAM_REMOTE" "$UPSTREAM_BRANCH"
if git show-ref --verify --quiet "refs/heads/$MIRROR_BRANCH"; then
  git branch -f "$MIRROR_BRANCH" "$UPSTREAM_REMOTE/$UPSTREAM_BRANCH"
else
  git branch "$MIRROR_BRANCH" "$UPSTREAM_REMOTE/$UPSTREAM_BRANCH"
fi

echo "$MIRROR_BRANCH now mirrors $UPSTREAM_REMOTE/$UPSTREAM_BRANCH."
echo "Push it with: git push --force-with-lease origin $MIRROR_BRANCH"
'''
write("scripts/sync-upstream.sh", sync_upstream, executable=True)

# Package scripts, without introducing new dependencies.
pkg_path = ROOT / "package.json"
pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
scripts = pkg.setdefault("scripts", {})
scripts["fork:check"] = "node scripts/check-fork-invariants.mjs"
scripts["fork:release:prepare"] = "node scripts/prepare-good-place-release.mjs"
write("package.json", json.dumps(pkg, indent=2) + "\n")

# Fork-facing README and maintenance rules.
readme = read("README.md")
notice = r'''> [!IMPORTANT]
> **Good Place distribution.** This repository is Georgii's maintained Cabinet
> fork. The original project is `cabinetai/cabinet`. The upstream
> `npx cabinetai` and `create-cabinet` packages install upstream Cabinet, not
> this distribution. Good Place users should install the desktop application
> from this repository's Releases page; developers may run this checkout from
> source.

'''
if not readme.startswith("> [!IMPORTANT]\n> **Good Place distribution."):
    write("README.md", notice + readme)

claude = read("CLAUDE.md")
claude_addition = r'''

## Fork and upstream changes

- Generic fixes intended for `cabinetai/cabinet` must start from the clean
  `upstream-main` mirror and append to upstream `PROGRESS.md`.
- Good Place branding, distribution, release, and workspace-sync changes start
  from fork `main` and append to `FORK_PROGRESS.md`, not `PROGRESS.md`.
- Feature branches use `upstream/*` for upstreamable work and `gp/*` for
  fork-only work. Release-only changes use `release/*`.
- Do not change package versions or `cabinet-release.json` in ordinary feature
  branches. Use `npm run fork:release:prepare -- <version>`.
'''
if "## Fork and upstream changes" not in claude:
    write("CLAUDE.md", claude.rstrip() + claude_addition + "\n")

fork_progress = r'''# Good Place fork progress

Fork-only distribution, branding, release, and workspace integration changes
are recorded here. Generic changes intended for upstream continue to use
`PROGRESS.md` on branches created from `upstream-main`.

[2026-07-24] Hardened fork maintenance and distribution: corrected internal Markdown path resolution, fixed prerelease version ordering, made release manifests fork-safe, added release and upstream-sync tooling, kept Electron credentials machine-local, hardened workspace sync execution/status, and added focused tests and fork invariants.
'''
write("FORK_PROGRESS.md", fork_progress)

maintenance = r'''# Maintaining the Good Place Cabinet fork

## Branches

| Branch | Purpose |
|---|---|
| `main` | Shipping Good Place distribution |
| `upstream-main` | Exact mirror of `cabinetai/cabinet:main`; never customize |
| `upstream/*` | Generic fixes proposed to upstream |
| `gp/*` | Good Place-only features |
| `release/*` | Version and manifest preparation only |

## Update the upstream mirror

```bash
./scripts/sync-upstream.sh
git push --force-with-lease origin upstream-main
```

Merge upstream into the shipping fork without rewriting published history:

```bash
git switch main
git merge --no-ff upstream-main
npm ci
npm run fork:check
npm test
npm run lint
npm run build
```

## Build an upstream pull request

```bash
git switch upstream-main
git switch -c upstream/fix-description
# implement only generic Cabinet changes
git push -u origin upstream/fix-description
```

Open the PR against `cabinetai/cabinet:main`. To use the fix immediately in the
fork, merge that same branch into fork `main`.

## Build a Good Place feature

```bash
git switch main
git switch -c gp/feature-description
```

Append fork-only work to `FORK_PROGRESS.md`. Prefer squash-merging these PRs so
the custom patch set stays easy to review when upstream changes arrive.

## Prepare a release

Feature PRs must not bump versions. Prepare releases on a dedicated branch:

```bash
git switch main
git switch -c release/0.5.4-gp.1
npm run fork:release:prepare -- 0.5.4-gp.1
npm test
npm run lint
npm run build
```

After merging, tag the exact `main` commit. The generated manifest and all
bundle URLs are checked to point to `souljorje/cabinet`; fork releases do not
advertise unpublished upstream npm packages.
'''
write("docs/FORK_MAINTENANCE.md", maintenance)

# Append the new fork release instructions to the existing distribution doc.
distribution = read("docs/GOOD_PLACE_DISTRIBUTION.md")
if "## Maintenance" not in distribution:
    distribution += r'''

## Maintenance

See `docs/FORK_MAINTENANCE.md` for the clean upstream mirror, branch model,
release preparation command, and validation rules. Run `npm run fork:check`
before every Good Place release.
'''
    write("docs/GOOD_PLACE_DISTRIBUTION.md", distribution)

print("Applied Good Place fork review fixes.")
