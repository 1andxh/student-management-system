import { useQuery } from "@tanstack/react-query";
import { createFileRoute } from "@tanstack/react-router";

import { api, API_URL } from "../lib/api";

export const Route = createFileRoute("/")({
  component: Home,
});

// Temporary (replaced in F3 by the role redirect): proves the whole chain
// works end to end — router, query cache, generated types, CORS, backend.
function Home() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: async () => {
      const { data, error } = await api.GET("/health");
      if (error) throw new Error("Health check failed");
      return data;
    },
  });

  return (
    <main className="p-8">
      <h1 className="text-xl font-semibold">School</h1>
      <p className="mt-2">
        API at <code>{API_URL}</code>:{" "}
        {health.isPending ? "checking…" : health.isError ? "unreachable" : health.data.status}
      </p>
    </main>
  );
}
