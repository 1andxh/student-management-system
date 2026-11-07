/// <reference types="vitest/config" />
import tailwindcss from "@tailwindcss/vite";
import { tanstackRouter } from "@tanstack/router-plugin/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [
    // Must come before react(): it generates src/routeTree.gen.ts from the
    // files in src/routes/, and code-splits each route into its own chunk.
    tanstackRouter({ target: "react", autoCodeSplitting: true }),
    react(),
    tailwindcss(),
  ],
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    // No tests until F3's auth client; an empty suite is not a failure yet.
    passWithNoTests: true,
  },
});
