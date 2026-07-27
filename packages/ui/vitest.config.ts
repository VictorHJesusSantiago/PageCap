import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@pagecap/core": path.resolve(__dirname, "../core/src/index.ts"),
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: true, // CSS Modules must resolve so className lookups in tests work
    coverage: {
      provider: "v8",
      reporter: ["text", "lcov"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: [
        "src/main.tsx",
        "src/vite-env.d.ts",
        "src/test/**",
        "**/*.test.{ts,tsx}",
      ],
      // A floor, not a target: set just under what the suite currently
      // achieves, so a regression fails the build but normal churn does not.
      // Raise it when coverage rises; never lower it to make a build pass.
      thresholds: {
        lines: 85,
        functions: 78,
        branches: 74,
        statements: 83,
      },
    },
  },
});
