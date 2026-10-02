import { NextResponse } from "next/server";

export async function GET(
    _request: Request,
    { params }: { params: Promise<{ slug: string }> },
) {
    const { slug } = await params;
    const safe = encodeURIComponent(slug);
    return NextResponse.json(
        {
            name: `${slug} — AI Growth OS`,
            short_name: slug.slice(0, 12),
            start_url: `/customer?business=${safe}`,
            scope: "/customer",
            display: "standalone",
            background_color: "#f5f7fb",
            theme_color: "#111827",
            icons: [],
        },
        {
            headers: {
                "Cache-Control": "public, max-age=300",
                "Content-Type": "application/manifest+json",
            },
        },
    );
}