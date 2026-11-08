"use client";

import { EvidenceLabel } from "@/components/basho/researcher/evidence-panel";
import type { EvidenceEvent } from "@/lib/types";

export function EvidencePicker({ evidence, value, onChange, filter }: {
  evidence: EvidenceEvent[];
  value: string[];
  onChange: (ids: string[]) => void;
  filter?: (e: EvidenceEvent) => boolean;
}) {
  const options = filter ? evidence.filter(filter) : evidence;
  if (options.length === 0) return <p className="text-xs text-zinc-500">Nenhuma evidência disponível.</p>;
  return (
    <div className="max-h-40 space-y-1 overflow-y-auto rounded border border-zinc-200 bg-white p-2 text-xs">
      {options.map((e) => (
        <label key={e.id} className="flex items-start gap-2">
          <input
            type="checkbox"
            className="mt-0.5"
            checked={value.includes(e.id)}
            onChange={(ev) => onChange(ev.target.checked ? [...value, e.id] : value.filter((v) => v !== e.id))}
          />
          <EvidenceLabel e={e} />
        </label>
      ))}
    </div>
  );
}
