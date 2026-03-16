# UMI Schema Design Principles

This document defines the rules that all UMI schemas must follow. If you're proposing a new schema or implementing the existing ones in a new language, start here.

## Core Rule

**An AI agent with no documentation should be able to guess every property name correctly.**

If a property needs explanation to be understood, rename it.

## Naming

- **PascalCase** for all property names: `UsedPercent`, not `used_percent` or `usedPercent`
- **Full words** — never abbreviate: `MemoryBytes`, not `MemBytes` or `mem`
- **Unit in the name** when the value isn't obvious: `TotalBytes`, `SpeedMbps`, `UptimeSeconds`
- **Boolean prefix** — `Is` for booleans: `IsAdmin`, `IsRemovable`, `IsEnabled`
- **Null over absent** — every property in the schema must appear in every output, using `null` for unavailable data

## Types

- **Bytes** are always `integer` — never pre-formatted strings like "4.2 GB"
- **Percentages** are `number` from 0 to 100, rounded to 1 decimal
- **Timestamps** are ISO 8601 strings (`"2026-03-16T14:22:00-05:00"`)
- **Enums** are short, uppercase-first English words: `Running`, `Up`, `WiFi`
- **Lists** are arrays, even if empty: `"DnsServers": []`, not `"DnsServers": null`

## Structure

- **Flat** — one level deep. No nested objects. If you need sub-objects, you need a separate schema.
- **One schema = one concept** — Disk, Network, Process. Not "SystemInfo" with everything jammed in.
- **Required vs Optional** — mark the minimum viable set as `required`. Optional fields still appear in output (as null).

## Enums

Every enum must:
- Be defined in the schema with `"enum": [...]`
- Include an `"Unknown"` value as a fallback
- Use consistent casing (first letter uppercase, rest lowercase)
- Be stable across versions — never remove a value, only add

## Versioning

- Schemas are versioned in their `$id`: `https://universalmachine.dev/schema/disk/v1`
- Adding optional properties = minor change (stays v1)
- Adding required properties or changing types = new version (v2)
- Implementations should declare which schema version they target

## Adding a New Schema

1. Identify the concept (one noun: "Service", "Package", "Port")
2. Research what each OS reports for that concept
3. Find the **intersection** of useful properties across all platforms
4. Name properties using the rules above
5. Write the JSON Schema file
6. Implement in PowerShell as proof that it works
7. Write Pester tests that validate schema compliance
8. Submit PR with schema + implementation + tests
