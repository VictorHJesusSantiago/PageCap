import { PageCapClient } from "@pagecap/core";

const API_BASE = (window as any).__PAGECAP_API__ ?? "http://127.0.0.1:8765";

export const client = new PageCapClient(API_BASE);
