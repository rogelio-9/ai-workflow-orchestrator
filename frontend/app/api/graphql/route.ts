/**
 * Server-side proxy to the GraphQL gateway.
 *
 * The browser never sees a token. Anything reachable from client code has to
 * be NEXT_PUBLIC_*, which means it is inlined into the bundle and shipped to
 * everyone -- a bearer token for a gateway that trusts `sub` as the user id is
 * exactly the wrong thing to put there. Instead the browser posts to this
 * same-origin route and the token is attached here, in Node, from a variable
 * that is never exposed to the client.
 *
 * It also makes CORS moot: from the browser's side every request is
 * same-origin, so the gateway does not need to allow a second origin.
 */

const GATEWAY_URL = process.env.GATEWAY_URL ?? "http://localhost:4000/graphql";
const DEV_TOKEN = process.env.DEV_TOKEN;

export async function POST(request: Request) {
  if (!DEV_TOKEN) {
    // Fail loudly rather than forwarding an unauthenticated request and
    // surfacing the gateway's 401 as if the query itself were wrong.
    return Response.json(
      { errors: [{ message: "DEV_TOKEN is not set -- see frontend/.env.local.example" }] },
      { status: 500 },
    );
  }

  const upstream = await fetch(GATEWAY_URL, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${DEV_TOKEN}`,
    },
    body: await request.text(),
    cache: "no-store",
  });

  // Passed through unchanged: GraphQL reports its own errors in the body with
  // a 200, and rewriting the status here would hide them.
  return new Response(await upstream.text(), {
    status: upstream.status,
    headers: { "content-type": "application/json" },
  });
}
