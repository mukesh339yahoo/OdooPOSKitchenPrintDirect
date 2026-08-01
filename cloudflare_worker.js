// Cloudflare Worker: License Server
// Upload this to Cloudflare Workers

// The KV Namespace should be bound as `ridhira_odoo_direct_kitchen_print_licenses`
// You need to set an environment variable `JWT_SECRET` in your Cloudflare Worker settings.

async function generateJWT(payload, secret) {
  const enc = new TextEncoder();
  const header = { alg: "HS256", typ: "JWT" };
  const encodedHeader = btoa(JSON.stringify(header)).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");
  const encodedPayload = btoa(JSON.stringify(payload)).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");
  const data = `${encodedHeader}.${encodedPayload}`;

  const key = await crypto.subtle.importKey(
    "raw",
    enc.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"]
  );

  const signature = await crypto.subtle.sign("HMAC", key, enc.encode(data));
  const encodedSignature = btoa(String.fromCharCode(...new Uint8Array(signature)))
    .replace(/=/g, "")
    .replace(/\+/g, "-")
    .replace(/\//g, "_");

  return `${data}.${encodedSignature}`;
}

export default {
  async fetch(request, env, ctx) {
    // Handle CORS preflight
    if (request.method === "OPTIONS") {
      return new Response(null, {
        headers: {
          "Access-Control-Allow-Origin": "*",
          "Access-Control-Allow-Methods": "POST, OPTIONS",
          "Access-Control-Allow-Headers": "Content-Type",
        },
      });
    }

    if (request.method !== "POST") {
      return new Response(JSON.stringify({ error: "Method not allowed" }), { 
        status: 405,
        headers: { "Content-Type": "application/json" }
      });
    }

    try {
      const body = await request.json();
      const apiKey = body.api_key;

      if (!apiKey) {
        return new Response(JSON.stringify({ error: "Missing api_key" }), { 
          status: 400,
          headers: { "Content-Type": "application/json" }
        });
      }

      // Check KV Store
      const licenseDataStr = await env.ridhira_odoo_direct_kitchen_print_licenses.get(apiKey);
      
      if (!licenseDataStr) {
        return new Response(JSON.stringify({ status: "expired", message: "Invalid or missing API key." }), { 
          status: 403,
          headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
        });
      }

      const licenseData = JSON.parse(licenseDataStr);
      // Example KV Data: { "status": "active", "expires_at": "2026-08-30T00:00:00Z" }

      const expiresAt = new Date(licenseData.expires_at);
      const now = new Date();

      if (now > expiresAt || licenseData.status !== "active") {
        return new Response(JSON.stringify({ status: "expired", message: "Subscription expired or inactive." }), { 
          status: 403,
          headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
        });
      }

      // Generate Signed JWT
      const jwtPayload = {
        api_key: apiKey,
        status: "active",
        expires_at: licenseData.expires_at,
        iat: Math.floor(Date.now() / 1000)
      };

      const token = await generateJWT(jwtPayload, env.JWT_SECRET);

      return new Response(JSON.stringify({
        status: "active",
        token: token,
        expires_at: licenseData.expires_at
      }), {
        status: 200,
        headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
      });

    } catch (e) {
      return new Response(JSON.stringify({ error: "Internal Server Error", details: e.message }), { 
        status: 500,
        headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" }
      });
    }
  },
};
