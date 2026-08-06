"use client";

import { ApolloProvider } from "@apollo/client/react";
import { useState } from "react";
import { makeClient } from "@/lib/apollo";

export function Providers({ children }: { children: React.ReactNode }) {
  // Created once per browser session rather than per render: a new client
  // would mean a new empty cache, so every navigation would refetch.
  const [client] = useState(makeClient);
  return <ApolloProvider client={client}>{children}</ApolloProvider>;
}
