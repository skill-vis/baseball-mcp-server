# Baseball Pitch Trajectory Simulator - MCP Server

Connect [Claude Desktop](https://claude.ai/download) to the [Baseball Pitch Trajectory Simulator](https://baseball.skill-vis.com) API to query MLB Statcast data and run pitch trajectory simulations using natural language.

## What you can do

Ask Claude Desktop questions like:

- "Search for Shohei Ohtani and show his 2025 game dates"
- "Show me all pitches Ohtani threw on July 1, 2025"
- "Simulate his 5th pitch and compare with Statcast data"
- "What is Ohtani's spin efficiency on his sweeper for the 2025 season?"
- "Show me Darvish's monthly speed trends for 2025"

Claude will automatically call the baseball.skill-vis.com API to find answers.

## Setup

### 1. Install dependencies

```bash
pip install mcp httpx
```

### 2. Download the MCP server script

Download [`baseball_mcp_server.py`](baseball_mcp_server.py) to a local folder, e.g. `~/baseball-mcp/`.

### 3. Configure Claude Desktop

Open the Claude Desktop config file:

- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

Add the `mcpServers` section (adjust the path to where you saved the script):

```json
{
  "mcpServers": {
    "baseball-simulator": {
      "command": "python3",
      "args": ["/path/to/baseball_mcp_server.py"]
    }
  }
}
```

If the file already has other settings, just add the `mcpServers` key alongside them.

### 4. Restart Claude Desktop

Quit and reopen Claude Desktop. You should see a tool icon in the chat indicating the baseball-simulator tools are available.

## Available Tools

| Tool | Description |
|------|-------------|
| `search_pitcher` | Search for a pitcher by name |
| `search_pitcher_by_id` | Search by MLBAM ID (for players not yet in registry) |
| `get_games` | Get game dates and pitch counts for a pitcher/year |
| `get_pitches` | Get all pitches from a specific game date |
| `simulate_pitch` | Run trajectory simulation for a specific pitch |
| `season_summary` | Season-wide per pitch-type summary (speed, spin, movement, BSG, spin efficiency, monthly trends) |

## Example Conversations

### Simulate a pitch with 3D animation

**You:** "Look up Yoshinobu Yamamoto and simulate one of his fastballs from 2025"

**Claude:** *(automatically calls search_pitcher, get_games, get_pitches, simulate_pitch)*

> Yamamoto threw 95.2 mph with 2,450 rpm spin. The simulation shows the ball arriving at x=-0.12m, z=0.85m at home plate, compared to Statcast measured x=-0.10m, z=0.84m (error: 22mm).
>
> 3D Animation: https://baseball.skill-vis.com/?mlbam_id=808967&year=2025&date=2025-07-01&pitch=3

Click the link to open a 3D animation of the pitch trajectory in your browser.

### Season analysis

**You:** "What is Ohtani's spin efficiency on each pitch type for the 2025 season?"

**Claude:** *(calls search_pitcher, season_summary with include_bsg=true)*

> Season 2025: 1089 pitches
>
> | Type |   n |  mph |  rpm |   eff |      B |      S |     G |
> |------|-----|------|------|-------|--------|--------|-------|
> |   FF | 433 | 98.4 | 2493 | 71.6% | +1654  |  -619  |  1520 |
> |   ST | 229 | 85.2 | 2614 | 48.2% |  +323  | +1191  |  2209 |
> |   SL | 120 | 88.3 | 2566 |  9.7% |   -26  |  +200  |  2548 |
> |   CU | 114 | 78.4 | 2676 | 70.0% | -1443  | +1182  |  1852 |

![3D Trajectory Simulator](https://baseball.skill-vis.com/static/ogp.png)

## Usage Notes

- **For aggregate stats** (averages, trends, comparisons), use `season_summary`. It returns all pitch-type data in a single request.
- **For trajectory simulation** (`simulate_pitch`), limit to 1-3 pitches per conversation. Each simulation runs a full physics integration on the server and is computationally expensive.
- **For 3D animation**, click the link included in `simulate_pitch` results to view the trajectory in your browser.

## API

This MCP server connects to the public API at https://baseball.skill-vis.com. The simulator is based on [Alan Nathan's physics model](https://baseball.physics.illinois.edu/) with extensions for Statcast data integration.

No API key is required.

## Troubleshooting

- **Tools not appearing**: Make sure the path in the config is absolute (not relative)
- **Python not found**: Try using the full path to python3 (e.g. `/usr/bin/python3` or `/usr/local/bin/python3`)
- **Connection errors**: Check that https://baseball.skill-vis.com is accessible from your network
