import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { test } from "node:test";
import ts from "typescript";

const source = await readFile(new URL("../src/calendar.ts", import.meta.url), "utf8");
const compiled = ts.transpile(source, { module: ts.ModuleKind.ESNext, target: ts.ScriptTarget.ES2022 });
const moduleUrl = `data:text/javascript;base64,${Buffer.from(compiled).toString("base64")}`;
const { buildCalendarIcs } = await import(moduleUrl);

test("calendar export uses valid UTC stamps, escaped text, and all-day dates", () => {
  const calendar = buildCalendarIcs(
    [{ due_date: "2026-11-12", action: "Submit, resume; before interview\r\nwith transcript" }],
    new Date("2026-11-02T01:02:03.456Z"),
  );

  assert.match(calendar, /DTSTAMP:20261102T010203Z/);
  assert.doesNotMatch(calendar, /DTSTAMP:[^\r\n]*ZZ/);
  assert.match(calendar, /DTSTART;VALUE=DATE:20261112/);
  assert.match(calendar, /DTEND;VALUE=DATE:20261113/);
  assert.match(calendar, /SUMMARY:Submit\\, resume\\; before interview\\nwith transcript/);
  assert.ok(calendar.endsWith("END:VCALENDAR"));
});

test("calendar export folds long UTF-8 lines within the RFC 5545 limit", () => {
  const calendar = buildCalendarIcs(
    [{ due_date: "2026-11-12", action: "📚".repeat(80) }],
    new Date("2026-11-02T01:02:03.000Z"),
  );
  const byteLengths = calendar.split("\r\n").map((line) => new TextEncoder().encode(line).length);
  assert.ok(byteLengths.every((length) => length <= 75));
  assert.ok(calendar.includes("\r\n "));
});
