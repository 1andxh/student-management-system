import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  // Generated files: the route tree (TanStack Router plugin) and the API
  // types (openapi-typescript). Linting them would only flag the generator.
  { ignores: ["dist", "src/routeTree.gen.ts", "src/lib/api-schema.d.ts"] },
  {
    files: ["**/*.{ts,tsx,js}"],
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    languageOptions: { globals: globals.browser },
    plugins: { "react-hooks": reactHooks },
    rules: reactHooks.configs.recommended.rules,
  },
);
