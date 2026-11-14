/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { securityHeaders } from "./src/lib/csp.ts";

export default defineConfig({
  plugins: [react()],
  // the preview server (used by make e2e) sends the same headers as the host, so the end-to-end tests run under the CSP
  preview: { headers: securityHeaders() },
  test: { environment: "jsdom", include: ["src/**/*.test.{ts,tsx}"], setupFiles: ["src/test/setup.ts"] },
});
