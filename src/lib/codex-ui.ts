export function looksLikeCodexTranscript(snapshot: string): boolean {
  const text = snapshot.toLowerCase();
  const compact = text.replace(/[^a-z]/g, "");

  return (
    compact.includes("transcript") &&
    text.includes("q to quit") &&
    text.includes("esc to edit prev")
  );
}
