"""
MCP Server for Baseball Pitch Trajectory Simulator.

Wraps https://baseball.skill-vis.com API endpoints as tools
for Claude Desktop / Claude Code.

Usage:
    Claude Desktop: register in claude_desktop_config.json
    Claude Code:    register in .claude/settings.json
"""

import asyncio
import json
import math
import httpx
from mcp.server import Server
from mcp.types import Tool, TextContent
from mcp.server.stdio import stdio_server

BASE_URL = "https://baseball.skill-vis.com"

server = Server("baseball-simulator")


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="search_pitcher",
            description="Search for an MLB pitcher by name. Returns MLBAM ID and career years.",
            inputSchema={
                "type": "object",
                "properties": {
                    "last_name": {"type": "string", "description": "Pitcher's last name (e.g. 'Ohtani')"},
                    "first_name": {"type": "string", "description": "First name (optional)"},
                    "year": {"type": "integer", "description": "Season year (default 2025)", "default": 2025},
                },
                "required": ["last_name"],
            },
        ),
        Tool(
            name="search_pitcher_by_id",
            description="Search for a pitcher by MLBAM ID (useful for newly arrived players not in Chadwick registry).",
            inputSchema={
                "type": "object",
                "properties": {
                    "mlbam_id": {"type": "integer", "description": "MLB Advanced Media ID"},
                    "year": {"type": "integer", "description": "Season year", "default": 2025},
                },
                "required": ["mlbam_id"],
            },
        ),
        Tool(
            name="get_games",
            description="Get game dates and pitch counts for a pitcher in a given year.",
            inputSchema={
                "type": "object",
                "properties": {
                    "mlbam_id": {"type": "integer", "description": "Pitcher's MLBAM ID"},
                    "year": {"type": "integer", "description": "Season year"},
                },
                "required": ["mlbam_id", "year"],
            },
        ),
        Tool(
            name="get_pitches",
            description="Get all pitches thrown by a pitcher on a specific game date. Returns pitch type, speed, spin rate, spin axis, and movement data.",
            inputSchema={
                "type": "object",
                "properties": {
                    "mlbam_id": {"type": "integer", "description": "Pitcher's MLBAM ID"},
                    "year": {"type": "integer", "description": "Season year"},
                    "date": {"type": "string", "description": "Game date (YYYY-MM-DD)"},
                },
                "required": ["mlbam_id", "year", "date"],
            },
        ),
        Tool(
            name="simulate_pitch",
            description="Run trajectory simulation for a specific Statcast pitch. Returns trajectory, home plate crossing, and comparison with Statcast measured data. IMPORTANT: This is computationally expensive. Do NOT call this in a loop or for many pitches at once. Limit to 1-3 simulations per conversation. For aggregate stats (averages, trends), use season_summary instead.",
            inputSchema={
                "type": "object",
                "properties": {
                    "mlbam_id": {"type": "integer", "description": "Pitcher's MLBAM ID"},
                    "year": {"type": "integer", "description": "Season year"},
                    "date": {"type": "string", "description": "Game date (YYYY-MM-DD)"},
                    "pitch_index": {"type": "integer", "description": "Pitch index within the game (0-based)"},
                    "spin_method": {"type": "string", "description": "'bsg' (default) or 'direct'", "default": "bsg"},
                    "cl_mode": {"type": "string", "description": "'adjusted' (default, cl2=1.045) or 'nathan' (cl2=1.12)", "default": "adjusted"},
                },
                "required": ["mlbam_id", "year", "date", "pitch_index"],
            },
        ),
        Tool(
            name="season_summary",
            description="Get season-wide summary for a pitcher: per pitch-type averages (speed, spin, movement, BSG decomposition, spin efficiency) and optional monthly trends. Use this for questions about a pitcher's overall season stats. Prefer this over calling get_pitches multiple times for aggregate analysis.",
            inputSchema={
                "type": "object",
                "properties": {
                    "mlbam_id": {"type": "integer", "description": "Pitcher's MLBAM ID"},
                    "year": {"type": "integer", "description": "Season year", "default": 2025},
                    "include_bsg": {"type": "boolean", "description": "Include BSG decomposition (backspin/sidespin/gyro/spin efficiency)", "default": True},
                    "include_monthly": {"type": "boolean", "description": "Include monthly trend data", "default": False},
                },
                "required": ["mlbam_id", "year"],
            },
        ),
    ]


MCP_HEADERS = {"User-Agent": "baseball-mcp-server/1.0"}


async def _api_post(client: httpx.AsyncClient, endpoint: str, data: dict) -> dict:
    resp = await client.post(f"{BASE_URL}{endpoint}", json=data, timeout=30.0, headers=MCP_HEADERS)
    resp.raise_for_status()
    return resp.json()


def _summarize_simulation(data: dict, mlbam_id: int = 0, year: int = 2025,
                          date: str = "", pitch_index: int = 0) -> str:
    """Extract key results from simulation response for concise display."""
    lines = []

    pi = data.get("pitch_info", {})
    sp = data.get("sim_params", {})
    hp = data.get("home_plate")
    hp_sc = data.get("home_plate_statcast")
    pfx = data.get("statcast_pfx")

    lines.append(f"Pitch: {pi.get('pitch_type', '?')} | {pi.get('release_speed_mph', '?')} mph | "
                 f"Spin: {pi.get('release_spin_rate', '?')} rpm | Axis: {pi.get('spin_axis', '?')}°")
    lines.append(f"Backspin: {sp.get('backspin_rpm', 0):.0f} rpm | Sidespin: {sp.get('sidespin_rpm', 0):.0f} rpm | "
                 f"Gyro: {sp.get('wg_rpm', 0):.0f} rpm")
    lines.append(f"Spin efficiency: {(sp.get('spin_efficiency', 0) * 100):.1f}%")
    lines.append(f"Method: {sp.get('spin_method', 'bsg')} | C_L: {sp.get('cl_mode', 'adjusted')} (cl2={sp.get('cl2', '?')})")

    if hp:
        lines.append(f"Sim home plate: x={hp.get('x', 0):.4f} m, z={hp.get('z', 0):.4f} m")
    if hp_sc:
        lines.append(f"Statcast actual: x={hp_sc.get('x', 0):.4f} m, z={hp_sc.get('z', 0):.4f} m")
    if hp and hp_sc:
        dx = (hp['x'] - hp_sc['x']) * 1000
        dz = (hp['z'] - hp_sc['z']) * 1000
        dr = math.sqrt(dx**2 + dz**2)
        lines.append(f"Error: Δx={dx:+.1f} mm, Δz={dz:+.1f} mm, Δr={dr:.1f} mm")
    if pfx:
        lines.append(f"Statcast pfx: x={pfx.get('pfx_x_in', 0):.1f} in, z={pfx.get('pfx_z_in', 0):.1f} in")

    # 3D animation link
    if mlbam_id and date:
        url = f"{BASE_URL}/?mlbam_id={mlbam_id}&year={year}&date={date}&pitch={pitch_index}"
        lines.append(f"\n3D Animation: {url}")

    return "\n".join(lines)


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        async with httpx.AsyncClient() as client:
            if name == "search_pitcher":
                data = await _api_post(client, "/statcast/search", {
                    "last_name": arguments["last_name"],
                    "first_name": arguments.get("first_name"),
                    "year": arguments.get("year", 2025),
                })
                if not data.get("players"):
                    return [TextContent(type="text", text="No players found.")]
                lines = []
                for p in data["players"]:
                    lines.append(f"{p['first_name']} {p['last_name']} (ID: {p['mlbam_id']}, {p['years']})")
                return [TextContent(type="text", text="\n".join(lines))]

            elif name == "search_pitcher_by_id":
                data = await _api_post(client, "/statcast/search_by_id", {
                    "mlbam_id": arguments["mlbam_id"],
                    "year": arguments.get("year", 2025),
                })
                if not data.get("players"):
                    return [TextContent(type="text", text="No player found for this ID.")]
                p = data["players"][0]
                return [TextContent(type="text", text=f"{p['first_name']} {p['last_name']} (ID: {p['mlbam_id']}, {p['years']})")]

            elif name == "get_games":
                data = await _api_post(client, "/statcast/games", {
                    "mlbam_id": arguments["mlbam_id"],
                    "year": arguments["year"],
                })
                if not data.get("games"):
                    return [TextContent(type="text", text=f"No games found for {arguments['year']}.")]
                lines = [f"Total pitches: {data.get('total_pitches', '?')}"]
                for g in data["games"]:
                    lines.append(f"  {g['date']}: {g['pitch_count']} pitches ({g['pitch_types']})")
                return [TextContent(type="text", text="\n".join(lines))]

            elif name == "get_pitches":
                data = await _api_post(client, "/statcast/pitches", {
                    "mlbam_id": arguments["mlbam_id"],
                    "year": arguments["year"],
                    "date": arguments["date"],
                })
                if not data.get("pitches"):
                    return [TextContent(type="text", text="No pitches found.")]
                lines = [f"Total: {len(data['pitches'])} pitches"]
                for i, p in enumerate(data["pitches"]):
                    lines.append(
                        f"  [{i}] {p.get('pitch_type', '?'):>3} "
                        f"{p.get('release_speed', 0):5.1f}mph "
                        f"spin={p.get('release_spin_rate', 0):.0f}rpm "
                        f"axis={p.get('spin_axis', 0):.0f}° "
                        f"pfx=({p.get('pfx_x', 0):.2f},{p.get('pfx_z', 0):.2f})ft "
                        f"| {p.get('description', '')}"
                    )
                return [TextContent(type="text", text="\n".join(lines))]

            elif name == "simulate_pitch":
                data = await _api_post(client, "/statcast/simulate", {
                    "mlbam_id": arguments["mlbam_id"],
                    "year": arguments["year"],
                    "date": arguments["date"],
                    "pitch_index": arguments["pitch_index"],
                    "spin_method": arguments.get("spin_method", "bsg"),
                    "cl_mode": arguments.get("cl_mode", "adjusted"),
                })
                summary = _summarize_simulation(
                    data,
                    mlbam_id=arguments["mlbam_id"],
                    year=arguments["year"],
                    date=arguments["date"],
                    pitch_index=arguments["pitch_index"],
                )
                return [TextContent(type="text", text=summary)]

            elif name == "season_summary":
                data = await _api_post(client, "/statcast/season_summary", {
                    "mlbam_id": arguments["mlbam_id"],
                    "year": arguments.get("year", 2025),
                    "include_bsg": arguments.get("include_bsg", True),
                    "include_monthly": arguments.get("include_monthly", False),
                })
                lines = [f"Season {data['year']}: {data['total_pitches']} pitches"]
                lines.append("")
                for s in data["pitch_type_summaries"]:
                    lines.append(f"--- {s['pitch_type']} ({s['count']} pitches) ---")
                    lines.append(f"  Speed: {s['avg_speed_mph'] or '?'} mph  EffSpeed: {s.get('avg_effective_speed') or '?'} mph  Arm: {s.get('avg_arm_angle') or '?'}°")
                    lines.append(f"  Spin: {s['avg_spin_rate'] or '?'} rpm  Axis: {s['avg_spin_axis'] or '?'}°")
                    lines.append(f"  pfx: ({s['avg_pfx_x_in'] or 0:+.1f}, {s['avg_pfx_z_in'] or 0:+.1f}) in  IVB: {s.get('avg_ivb_in') or '?'} in  HB: {s.get('avg_hb_in') or '?'} in")
                    lines.append(f"  Whiff: {s.get('whiff_pct') or '?'}%  Chase: {s.get('chase_pct') or '?'}%  Zone: {s.get('zone_pct') or '?'}%  CSW: {s.get('csw_pct') or '?'}%")
                    if s.get('avg_launch_speed') is not None:
                        lines.append(f"  ExitVelo: {s['avg_launch_speed']} mph  LA: {s.get('avg_launch_angle') or '?'}°  xwOBA: {s.get('avg_xwoba') or '?'}  wOBA: {s.get('avg_woba') or '?'}")
                    if data['bsg_computed'] and s.get('avg_spin_efficiency') is not None:
                        lines.append(f"  SpinEff: {s['avg_spin_efficiency']*100:.1f}%  B: {s['avg_backspin_rpm'] or 0:+.0f}  S: {s['avg_sidespin_rpm'] or 0:+.0f}  G: {s['avg_gyrospin_rpm'] or 0:.0f}")
                    lines.append("")

                if data.get("monthly_trends"):
                    lines.append("")
                    lines.append("--- Monthly Trends ---")
                    for t in data["monthly_trends"]:
                        lines.append(f"  {t['month']} {t['pitch_type']:>3}: n={t['count']:3d} "
                                     f"{t['avg_speed_mph'] or 0:.1f}mph {t['avg_spin_rate'] or 0:.0f}rpm "
                                     f"pfx=({t['avg_pfx_x_in'] or 0:+.1f},{t['avg_pfx_z_in'] or 0:+.1f})in")

                return [TextContent(type="text", text="\n".join(lines))]

            else:
                return [TextContent(type="text", text=f"Unknown tool: {name}")]

    except httpx.HTTPStatusError as e:
        return [TextContent(type="text", text=f"API error {e.response.status_code}: {e.response.text}")]
    except Exception as e:
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
