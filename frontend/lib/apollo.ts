"use client";

import { ApolloClient, HttpLink, InMemoryCache } from "@apollo/client";

/**
 * Points at this app's own /api/graphql route, not at the gateway directly.
 * The route attaches the bearer token server-side; see app/api/graphql/route.ts.
 */
export function makeClient() {
  return new ApolloClient({
    link: new HttpLink({ uri: "/api/graphql" }),
    cache: new InMemoryCache(),
  });
}
