export default {
  async fetch(request, env) {
    const backendHost = (env && env.BACKEND_HOST ? String(env.BACKEND_HOST) : "").trim();
    if (!backendHost) {
      return new Response("Missing BACKEND_HOST environment variable", { status: 500 });
    }

    const url = new URL(request.url);
    url.hostname = backendHost;
    url.protocol = "https:";

    const headers = new Headers(request.headers);
    headers.set("Host", backendHost);
    headers.set("X-Forwarded-Proto", "https");

    return fetch(url.toString(), {
      method: request.method,
      headers,
      body: request.method !== "GET" && request.method !== "HEAD" ? request.body : undefined,
      redirect: "manual",
    });
  },
};
