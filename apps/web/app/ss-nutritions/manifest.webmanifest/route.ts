export async function GET() {
  return Response.json({
    name: "SS Nutritions",
    short_name: "SS Nutritions",
    description: "Natural and practical wellness for everyday living.",
    start_url: "/ss-nutritions",
    scope: "/ss-nutritions",
    display: "standalone",
    orientation: "portrait-primary",
    background_color: "#f8f6ee",
    theme_color: "#315f45",
    categories: ["health", "lifestyle"],
    icons: [
      { src: "/ss-nutritions/icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any maskable" }
    ]
  });
}
