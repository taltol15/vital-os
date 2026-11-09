import { ImageResponse } from "next/og";

export const alt = "Vital OS. A quiet desktop.";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpenGraphImage() {
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", background: "#050608", color: "#F3EEE4", padding: "72px", alignItems: "center", justifyContent: "space-between" }}>
        <div style={{ display: "flex", flexDirection: "column", maxWidth: 680 }}>
          <div style={{ fontSize: 22, letterSpacing: 6, color: "#E6D3A4", textTransform: "uppercase" }}>Nocturne</div>
          <div style={{ fontSize: 92, lineHeight: 1, marginTop: 18 }}>Vital OS</div>
          <div style={{ fontSize: 32, color: "#C4BBAE", marginTop: 24 }}>A quiet desktop. Graphite, ivory, champagne.</div>
        </div>
        <div style={{ width: 220, height: 220, borderRadius: 999, border: "3px solid #C6A56A", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 88 }}>
          V
        </div>
      </div>
    ),
    size,
  );
}
