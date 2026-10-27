import { apiFetch } from './client';
import type { Branch, BranchWorker } from '../types';

interface RawBranch {
  key?: unknown;
  name?: unknown;
  description?: unknown;
  tagline?: unknown;
  workers?: unknown;
}

function asString(value: unknown, fallback = ''): string {
  return typeof value === 'string' && value.trim() ? value : fallback;
}

function mapWorkers(raw: unknown): BranchWorker[] {
  if (!Array.isArray(raw)) return [];
  return raw
    .filter((w): w is Record<string, unknown> => !!w && typeof w === 'object')
    .filter((w) => typeof w.key === 'string' && !!w.key)
    .map((w) => ({
      key: w.key as string,
      jobRole: asString(w.jobRole, w.key as string),
      exampleQuestions: Array.isArray(w.exampleQuestions)
        ? w.exampleQuestions.filter((q): q is string => typeof q === 'string' && !!q.trim())
        : [],
    }));
}

/** Hanya field aman yang diambil; `manager_persona` dan `icon` (emoji) sengaja tidak dipetakan. */
export async function fetchBranches(): Promise<Branch[]> {
  const raw = (await apiFetch('/api/branches')) as { branches?: unknown };
  if (!raw || !Array.isArray(raw.branches)) return [];
  return raw.branches
    .filter((b): b is RawBranch => !!b && typeof b === 'object')
    .filter((b) => typeof b.key === 'string' && !!b.key)
    .map((b) => ({
      key: b.key as string,
      name: asString(b.name, b.key as string),
      description: asString(b.description),
      tagline: asString(b.tagline),
      workers: mapWorkers(b.workers),
    }));
}
