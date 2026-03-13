import { NextRequest, NextResponse } from "next/server";

export async function POST(request: NextRequest) {
  const { passcode } = await request.json();
  const expected = process.env.PASSCODE;

  if (!expected) {
    return NextResponse.json({ error: "Passcode not configured" }, { status: 500 });
  }

  if (passcode !== expected) {
    return NextResponse.json({ error: "Invalid passcode" }, { status: 401 });
  }

  const response = NextResponse.json({ success: true });
  response.cookies.set("authenticated", "true", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    maxAge: 60 * 60 * 24 * 7, // 7 days
    path: "/",
  });

  return response;
}
