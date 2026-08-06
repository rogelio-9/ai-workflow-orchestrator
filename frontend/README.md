# Frontend

Next.js App Router client for the orchestrator, talking to the GraphQL gateway.

## Running it

The backend must be up (`docker compose up -d` from the repo root).

```bash
cp .env.local.example .env.local
# mint a token into DEV_TOKEN -- the command is in the example file
npm install
npm run dev
```

## Why requests go through `/api/graphql`

The gateway authenticates every request with a bearer token, and there is no
login flow yet. Browser code can only read `NEXT_PUBLIC_*` variables, which are
inlined into the JavaScript bundle and served to everyone -- so putting a token
there would publish it.

Instead the browser posts to this app's own `/api/graphql` route, which runs on
the server and attaches the token from `DEV_TOKEN`. The token never enters the
bundle, and because the browser only ever talks to its own origin, the gateway
needs no CORS configuration.

The variable holds a *token*, not `JWT_SECRET`. This app needs to call the
gateway, not to sign arbitrary identities: a leaked token expires in hours, a
leaked signing key would let anyone mint any user.
