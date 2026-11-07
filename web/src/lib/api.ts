import createClient from "openapi-fetch";

import type { paths } from "./api-schema";

/**
 * The one typed client every API call goes through. `paths` is generated
 * from the backend's OpenAPI schema (`npm run gen:api`), so a request to a
 * route that doesn't exist, a wrong query param, or a misread response
 * field is a type error here rather than a runtime surprise.
 *
 * 127.0.0.1, not localhost: on this machine the two resolve differently
 * (IPv4 vs IPv6), and the backend's CORS allowlist names 127.0.0.1.
 *
 * Auth (attaching the in-memory access token, single-flight refresh on 401)
 * is added as middleware in Stage F3; nothing here knows about tokens yet.
 */
export const API_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8001";

export const api = createClient<paths>({ baseUrl: API_URL });
