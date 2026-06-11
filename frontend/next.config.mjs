import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/**
 * Force `.env.local` to take precedence over any inherited Windows User /
 * shell env vars. This protects against a real-world trap: if the operator
 * has `NEXT_PUBLIC_API_URL` set globally for an unrelated project (we found
 * one pointing at port 4000), Next.js's default order silently lets that
 * value win over `.env.local` — and the bundle ships baking the wrong
 * backend URL. Every "Network Error on login" you ever see in dev is this.
 *
 * This block re-reads `.env.local` and overwrites any NEXT_PUBLIC_* values
 * that came in from the shell so the bundle always reflects what's on disk.
 */
function loadLocalEnvOverrides() {
  const envPath = path.join(__dirname, ".env.local");
  if (!fs.existsSync(envPath)) return;
  const lines = fs.readFileSync(envPath, "utf8").split(/\r?\n/);
  for (const raw of lines) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq < 1) continue;
    const key = line.slice(0, eq).trim();
    const value = line.slice(eq + 1).trim().replace(/^['"]|['"]$/g, "");
    // Only override NEXT_PUBLIC_* (the build-time inlined variety). Don't
    // touch system env we genuinely want to inherit (PATH, NODE_ENV, etc).
    if (key.startsWith("NEXT_PUBLIC_") && process.env[key] !== value) {
      const previous = process.env[key];
      process.env[key] = value;
      if (previous !== undefined) {
        // eslint-disable-next-line no-console
        console.log(
          `[next.config] Overrode polluted env var ${key}: ` +
            `was ${JSON.stringify(previous)} -> using ${JSON.stringify(value)} from .env.local`,
        );
      }
    }
  }
}

loadLocalEnvOverrides();

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  experimental: {
    optimizePackageImports: ["lucide-react", "date-fns", "recharts"],
  },
};

export default nextConfig;
