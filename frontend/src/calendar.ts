export type CalendarAction = { action: string; due_date: string };

function escapeIcsText(value: string): string {
  return value.replaceAll("\\", "\\\\").replace(/\r\n|\r|\n/g, "\\n").replaceAll(";", "\\;").replaceAll(",", "\\,");
}

function foldIcsLine(line: string): string {
  const encoder = new TextEncoder();
  const parts: string[] = [];
  let part = "";
  let bytes = 0;
  for (const character of line) {
    const size = encoder.encode(character).length;
    if (bytes + size > 75 && part) {
      parts.push(part);
      part = " ";
      bytes = 1;
    }
    part += character;
    bytes += size;
  }
  parts.push(part);
  return parts.join("\r\n");
}

export function buildCalendarIcs(actions: readonly CalendarAction[], now = new Date()): string {
  const stamp = now.toISOString().replaceAll("-", "").replaceAll(":", "").replace(/\.\d{3}/, "");
  const events = actions.map((action, index) => {
    const start = action.due_date.replaceAll("-", "");
    const next = new Date(`${action.due_date}T00:00:00Z`);
    next.setUTCDate(next.getUTCDate() + 1);
    const end = next.toISOString().slice(0, 10).replaceAll("-", "");
    return ["BEGIN:VEVENT", `UID:buildproof-${stamp}-${index}@buildproof.app`, `DTSTAMP:${stamp}`,
      `DTSTART;VALUE=DATE:${start}`, `DTEND;VALUE=DATE:${end}`, `SUMMARY:${escapeIcsText(action.action)}`, "END:VEVENT"];
  });
  return [["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//BuildProof//Campus Notices//EN"], ...events, ["END:VCALENDAR"]]
    .flat().map(foldIcsLine).join("\r\n");
}
