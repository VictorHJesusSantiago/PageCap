import { PageCapClient } from "@pagecap/core";

// Both globals are injected by the Electron main process (see
// packages/electron/src/main.ts). In a plain browser they are undefined and the
// engine, having no PAGECAP_API_TOKEN set, accepts unauthenticated localhost
// requests — which is the documented dev-server setup.
const API_BASE = (window as any).__PAGECAP_API__ ?? "http://127.0.0.1:8765";
const API_TOKEN = (window as any).__PAGECAP_TOKEN__ as string | undefined;

export const client = new PageCapClient(API_BASE, API_TOKEN);
