/**
 * Test helper: a fast-check arbitrary for any value that validates against one of our JSON Schemas
 * (the subset the engine uses: type, enum, anyOf, min/max, items, properties, required, additionalProperties).
 * Used by the contract property W1 (REQ-WEB-DATA.1, testing.md #16).
 */
import fc from "fast-check";

export type Schema = {
  type?: string;
  enum?: unknown[];
  anyOf?: Schema[];
  properties?: Record<string, Schema>;
  required?: string[];
  additionalProperties?: boolean | Schema;
  items?: Schema;
  minItems?: number;
  maxItems?: number;
  minimum?: number;
  maximum?: number;
};

export function arbFromSchema(s: Schema): fc.Arbitrary<unknown> {
  if (s.enum) return fc.constantFrom(...s.enum);
  if (s.anyOf) return fc.oneof(...s.anyOf.map(arbFromSchema));
  switch (s.type) {
    case "null":
      return fc.constant(null);
    case "boolean":
      return fc.boolean();
    case "string":
      return fc.string({ maxLength: 12 });
    case "integer":
      return fc.integer({ min: s.minimum ?? -1000, max: s.maximum ?? 100000 });
    case "number":
      return fc.double({ min: s.minimum ?? -1000, max: s.maximum ?? 100000, noNaN: true, noDefaultInfinity: true });
    case "array":
      return fc.array(s.items ? arbFromSchema(s.items) : fc.anything(), { minLength: s.minItems ?? 0, maxLength: s.maxItems ?? 4 });
    case "object": {
      const props = s.properties ?? {};
      const required = new Set(s.required ?? []);
      const entries = Object.entries(props);
      const shape: Record<string, fc.Arbitrary<unknown>> = {};
      for (const [k, v] of entries) shape[k] = arbFromSchema(v);
      const record = fc.record(shape, { requiredKeys: entries.filter(([k]) => required.has(k)).map(([k]) => k) });
      const extra =
        typeof s.additionalProperties === "object"
          ? fc.dictionary(
              fc.string({ minLength: 1, maxLength: 6 }).filter((k) => !(k in props) && k !== "__proto__"),
              arbFromSchema(s.additionalProperties),
              { maxKeys: 3 },
            )
          : fc.constant({});
      return fc.tuple(record, extra).map(([r, e]) => ({ ...e, ...r }));
    }
    default:
      return fc.anything();
  }
}
