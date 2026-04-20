"""
app.py — NBA Analytics Dashboard
Built with DuckDB + Streamlit for DSCI 551

Run:
    streamlit run app.py
"""

import duckdb
import pandas as pd
import streamlit as st

# ── Page config ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="NBA Analytics Dashboard",
    page_icon="🏀",
    layout="wide",
)

# ── DB connection (cached so it's reused across reruns) ────────────────────────
@st.cache_resource
def get_con():
    return duckdb.connect("nba.duckdb", read_only=True)

con = get_con()

# ── Helper: run query → DataFrame ──────────────────────────────────────────────
def q(sql, params=None):
    if params:
        return con.execute(sql, params).df()
    return con.execute(sql).df()

# ── Sidebar nav ────────────────────────────────────────────────────────────────
st.sidebar.title("NBA Dashboard")
st.sidebar.caption("2024–25 Season · Powered by DuckDB")
page = st.sidebar.radio(
    "Navigate",
    ["Player Game Log", "Player Comparison", "Team Trends", "Leaderboard", "Custom Query"],
)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE 1: Player Game Log + Rolling Average
# ══════════════════════════════════════════════════════════════════════════════
if page == "Player Game Log":
    st.title("Player Game Log")
    st.caption(
        "**DuckDB internals:** columnar scan on PTS, REB, AST, GAME_DATE only — "
        "unneeded columns are never read from storage. Window function computed "
        "with vectorized batch processing."
    )

    # Controls
    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        all_players = q("SELECT PLAYER_NAME FROM Players ORDER BY PLAYER_NAME")["PLAYER_NAME"].tolist()
        player = st.selectbox("Player", all_players, index=all_players.index("Stephen Curry") if "Stephen Curry" in all_players else 0)
    with col2:
        season_type = st.selectbox("Season Type", ["All", "Regular Season", "Playoffs"])
    with col3:
        window = st.slider("Rolling window (games)", 3, 20, 10)

    # Build filter
    season_filter = "" if season_type == "All" else f"AND SEASON_TYPE = '{season_type}'"

    # Game log with rolling avg — window function over sorted date
    df = q(f"""
        SELECT
            GAME_DATE,
            SEASON_TYPE,
            TEAM_ABBREVIATION AS TEAM,
            PTS, REB, AST, STL, BLK, TOV,
            ROUND(FG_PCT * 100, 1)  AS FG_PCT,
            ROUND(FG3_PCT * 100, 1) AS FG3_PCT,
            PLUS_MINUS,
            ROUND(AVG(PTS) OVER (
                PARTITION BY PLAYER_NAME
                ORDER BY GAME_DATE
                ROWS BETWEEN {window - 1} PRECEDING AND CURRENT ROW
            ), 1) AS rolling_pts,
            ROUND(AVG(AST) OVER (
                PARTITION BY PLAYER_NAME
                ORDER BY GAME_DATE
                ROWS BETWEEN {window - 1} PRECEDING AND CURRENT ROW
            ), 1) AS rolling_ast
        FROM PlayerBoxScores
        WHERE PLAYER_NAME = '{player}'
        {season_filter}
        ORDER BY GAME_DATE DESC
    """)

    if df.empty:
        st.warning("No data found for this player / filter combination.")
    else:
        # Summary cards
        c1, c2, c3, c4, c5 = st.columns(5)
        c1.metric("PPG", f"{df['PTS'].mean():.1f}")
        c2.metric("RPG", f"{df['REB'].mean():.1f}")
        c3.metric("APG", f"{df['AST'].mean():.1f}")
        c4.metric("FG%", f"{df['FG_PCT'].mean():.1f}%")
        c5.metric("3P%", f"{df['FG3_PCT'].mean():.1f}%")

        # Rolling pts chart
        chart_df = df[["GAME_DATE", "PTS", "rolling_pts"]].sort_values("GAME_DATE")
        st.subheader(f"Points + {window}-Game Rolling Average")
        st.line_chart(chart_df.set_index("GAME_DATE")[["PTS", "rolling_pts"]])

        # Full game log table
        st.subheader("Game Log")
        st.dataframe(df, use_container_width=True, hide_index=True)

    # EXPLAIN output (useful for final report)
    with st.expander("🔍 DuckDB Query Plan (EXPLAIN)"):
        plan = con.execute(f"""
            EXPLAIN SELECT PTS,
                AVG(PTS) OVER (ORDER BY GAME_DATE ROWS BETWEEN {window-1} PRECEDING AND CURRENT ROW)
            FROM PlayerBoxScores
            WHERE PLAYER_NAME = '{player}' {season_filter}
        """).fetchall()
        st.code("\n".join(row[1] for row in plan), language="text")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 2: Player Comparison
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Player Comparison":
    st.title("Player Comparison")
    st.caption(
        "**DuckDB internals:** GROUP BY aggregation runs as vectorized batch operations "
        "over columnar PTS, REB, AST data. Only selected stat columns are scanned."
    )

    all_players = q("SELECT PLAYER_NAME FROM Players ORDER BY PLAYER_NAME")["PLAYER_NAME"].tolist()

    col1, col2, col3 = st.columns([2, 2, 1])
    with col1:
        p1 = st.selectbox("Player 1", all_players, index=all_players.index("LeBron James") if "LeBron James" in all_players else 0)
    with col2:
        p2 = st.selectbox("Player 2", all_players, index=all_players.index("Stephen Curry") if "Stephen Curry" in all_players else 1)
    with col3:
        season_type = st.selectbox("Season", ["All", "Regular Season", "Playoffs"])

    season_filter = "" if season_type == "All" else f"AND SEASON_TYPE = '{season_type}'"

    df = q(f"""
        SELECT
            PLAYER_NAME,
            COUNT(*)                        AS GP,
            ROUND(AVG(PTS),  1)             AS PPG,
            ROUND(AVG(REB),  1)             AS RPG,
            ROUND(AVG(AST),  1)             AS APG,
            ROUND(AVG(STL),  1)             AS SPG,
            ROUND(AVG(BLK),  1)             AS BPG,
            ROUND(AVG(TOV),  1)             AS TPG,
            ROUND(AVG(FG_PCT)  * 100, 1)    AS FG_PCT,
            ROUND(AVG(FG3_PCT) * 100, 1)    AS FG3_PCT,
            ROUND(AVG(FT_PCT)  * 100, 1)    AS FT_PCT,
            ROUND(AVG(PLUS_MINUS), 1)       AS PLUS_MINUS
        FROM PlayerBoxScores
        WHERE PLAYER_NAME IN ('{p1}', '{p2}')
        {season_filter}
        GROUP BY PLAYER_NAME
    """)

    if df.empty:
        st.warning("No data found. Check season type filter — playoff data may be limited.")
    else:
        st.subheader(f"{p1} vs. {p2}" + (f" — {season_type}" if season_type != "All" else ""))
        st.dataframe(df.set_index("PLAYER_NAME").T, use_container_width=True)

        # Bar charts for key stats
        stats = ["PPG", "RPG", "APG", "FG_PCT", "FG3_PCT"]
        for stat in stats:
            if stat in df.columns:
                st.bar_chart(df.set_index("PLAYER_NAME")[stat])

    with st.expander("🔍 DuckDB Query Plan (EXPLAIN)"):
        plan = con.execute(f"""
            EXPLAIN SELECT PLAYER_NAME, AVG(PTS), AVG(REB), AVG(AST)
            FROM PlayerBoxScores
            WHERE PLAYER_NAME IN ('{p1}', '{p2}') {season_filter}
            GROUP BY PLAYER_NAME
        """).fetchall()
        st.code("\n".join(row[1] for row in plan), language="text")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 3: Team Monthly Trends
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Team Trends":
    st.title("Team Monthly Trends")
    st.caption(
        "**DuckDB internals:** STRFTIME date extraction and GROUP BY run as vectorized "
        "operations. Columnar storage means only the date, team, and selected stat "
        "columns are read from disk."
    )

    teams = q("SELECT DISTINCT TEAM_ABBREVIATION FROM PlayerBoxScores ORDER BY 1")["TEAM_ABBREVIATION"].tolist()

    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        team = st.selectbox("Team", teams)
    with col2:
        stat = st.selectbox("Stat", ["PTS", "REB", "AST", "STL", "BLK", "TOV"])
    with col3:
        season_type = st.selectbox("Season Type", ["All", "Regular Season", "Playoffs"])

    season_filter = "" if season_type == "All" else f"AND SEASON_TYPE = '{season_type}'"

    df = q(f"""
        SELECT
            STRFTIME(GAME_DATE, '%Y-%m')    AS month,
            ROUND(AVG({stat}), 2)           AS avg_{stat},
            COUNT(DISTINCT GAME_ID)         AS games
        FROM PlayerBoxScores
        WHERE TEAM_ABBREVIATION = '{team}'
        {season_filter}
        GROUP BY month
        ORDER BY month
    """)

    if df.empty:
        st.warning("No data found for this combination.")
    else:
        st.subheader(f"{team} — Average {stat} by Month")
        st.line_chart(df.set_index("month")[f"avg_{stat}"])
        st.dataframe(df, use_container_width=True, hide_index=True)

    with st.expander("🔍 DuckDB Query Plan (EXPLAIN)"):
        plan = con.execute(f"""
            EXPLAIN SELECT STRFTIME(GAME_DATE, '%Y-%m') AS month, AVG({stat})
            FROM PlayerBoxScores
            WHERE TEAM_ABBREVIATION = '{team}' {season_filter}
            GROUP BY month
        """).fetchall()
        st.code("\n".join(row[1] for row in plan), language="text")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 4: Leaderboard
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Leaderboard":
    st.title("Leaderboard")
    st.caption(
        "**DuckDB internals:** ORDER BY + LIMIT on aggregated columnar data. "
        "DuckDB's vectorized execution computes all AVG() aggregations in a single "
        "parallel pass over the relevant columns."
    )

    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        stat = st.selectbox("Rank by", ["PTS", "REB", "AST", "STL", "BLK", "FG_PCT", "FG3_PCT"])
    with col2:
        season_type = st.selectbox("Season Type", ["Regular Season", "Playoffs", "All"])
    with col3:
        min_games = st.slider("Min games played", 1, 50, 20)

    season_filter = "" if season_type == "All" else f"AND SEASON_TYPE = '{season_type}'"
    label = "AVG" if stat in ("FG_PCT", "FG3_PCT") else "PPG" if stat == "PTS" else stat

    df = q(f"""
        SELECT
            PLAYER_NAME,
            TEAM_ABBREVIATION                   AS TEAM,
            COUNT(*)                            AS GP,
            ROUND(AVG({stat}), 3)               AS avg_{stat}
        FROM PlayerBoxScores
        WHERE 1=1 {season_filter}
        GROUP BY PLAYER_NAME, TEAM_ABBREVIATION
        HAVING COUNT(*) >= {min_games}
        ORDER BY avg_{stat} DESC
        LIMIT 25
    """)

    if df.empty:
        st.warning("No results. Try lowering the minimum games filter.")
    else:
        st.subheader(f"Top 25 by {stat} — {season_type}")
        # Add rank column
        df.insert(0, "Rank", range(1, len(df) + 1))
        st.dataframe(df, use_container_width=True, hide_index=True)

        st.bar_chart(df.set_index("PLAYER_NAME")[f"avg_{stat}"].head(15))

    with st.expander("🔍 DuckDB Query Plan (EXPLAIN)"):
        plan = con.execute(f"""
            EXPLAIN SELECT PLAYER_NAME, AVG({stat})
            FROM PlayerBoxScores {season_filter.replace('AND', 'WHERE')}
            GROUP BY PLAYER_NAME
            HAVING COUNT(*) >= {min_games}
            ORDER BY AVG({stat}) DESC
            LIMIT 25
        """).fetchall()
        st.code("\n".join(row[1] for row in plan), language="text")


# ══════════════════════════════════════════════════════════════════════════════
# PAGE 5: Custom Query
# ══════════════════════════════════════════════════════════════════════════════
elif page == "Custom Query":
    st.title("Custom SQL Query")
    st.caption(
        "**DuckDB internals:** queries run directly against the columnar DuckDB engine. "
        "Use EXPLAIN to inspect the query plan and observe which columns are scanned."
    )

    # Schema reference
    with st.expander("Schema Reference", expanded=True):
        st.markdown("""
| Table | Key Columns |
|---|---|
| `Games` | `GAME_ID`, `GAME_DATE`, `HOME_TEAM`, `AWAY_TEAM`, `SEASON_TYPE` |
| `Players` | `PLAYER_ID`, `PLAYER_NAME`, `TEAM` |
| `PlayerBoxScores` | `GAME_ID`, `PLAYER_ID`, `PLAYER_NAME`, `TEAM_ABBREVIATION`, `PTS`, `REB`, `AST`, `STL`, `BLK`, `TOV`, `FGM`, `FGA`, `FG_PCT`, `FG3M`, `FG3A`, `FG3_PCT`, `FTM`, `FTA`, `FT_PCT`, `PLUS_MINUS`, `GAME_DATE`, `SEASON_TYPE` |

**Season types:** `'Regular Season'`, `'Playoffs'`
        """)

    # Example queries
    examples = {
        "-- select an example --": "",
        "Top 10 scorers (Regular Season)": """SELECT PLAYER_NAME, TEAM_ABBREVIATION, ROUND(AVG(PTS), 1) AS PPG, COUNT(*) AS GP
FROM PlayerBoxScores
WHERE SEASON_TYPE = 'Regular Season'
GROUP BY PLAYER_NAME, TEAM_ABBREVIATION
HAVING COUNT(*) >= 20
ORDER BY PPG DESC
LIMIT 10""",
        "Stephen Curry rolling 10-game avg": """SELECT GAME_DATE, PTS,
    ROUND(AVG(PTS) OVER (
        ORDER BY GAME_DATE
        ROWS BETWEEN 9 PRECEDING AND CURRENT ROW
    ), 1) AS rolling_10_pts
FROM PlayerBoxScores
WHERE PLAYER_NAME = 'Stephen Curry'
  AND SEASON_TYPE = 'Regular Season'
ORDER BY GAME_DATE""",
        "Playoff leaders by team": """SELECT TEAM_ABBREVIATION,
    ROUND(AVG(PTS), 1) AS team_avg_pts,
    ROUND(AVG(REB), 1) AS team_avg_reb,
    ROUND(AVG(AST), 1) AS team_avg_ast,
    COUNT(DISTINCT GAME_ID) AS gp
FROM PlayerBoxScores
WHERE SEASON_TYPE = 'Playoffs'
GROUP BY TEAM_ABBREVIATION
ORDER BY team_avg_pts DESC""",
        "40-point games this season": """SELECT PLAYER_NAME, TEAM_ABBREVIATION, GAME_DATE, PTS, REB, AST, SEASON_TYPE
FROM PlayerBoxScores
WHERE PTS >= 40
ORDER BY PTS DESC""",
        "Home vs. away scoring splits": """SELECT
    p.PLAYER_NAME,
    ROUND(AVG(CASE WHEN g.HOME_TEAM = p.TEAM_ABBREVIATION THEN p.PTS END), 1) AS home_ppg,
    ROUND(AVG(CASE WHEN g.AWAY_TEAM = p.TEAM_ABBREVIATION THEN p.PTS END), 1) AS away_ppg,
    COUNT(*) AS gp
FROM PlayerBoxScores p
JOIN Games g ON p.GAME_ID = g.GAME_ID
WHERE p.SEASON_TYPE = 'Regular Season'
GROUP BY p.PLAYER_NAME
HAVING COUNT(*) >= 30
ORDER BY home_ppg DESC
LIMIT 20""",
    }

    selected = st.selectbox("Load an example query", list(examples.keys()))

    default_sql = examples[selected] if selected != "-- select an example --" else \
        "SELECT PLAYER_NAME, ROUND(AVG(PTS), 1) AS PPG\nFROM PlayerBoxScores\nGROUP BY PLAYER_NAME\nORDER BY PPG DESC\nLIMIT 10"

    sql = st.text_area("SQL Query", value=default_sql, height=200)

    show_explain = st.checkbox("Show query plan (EXPLAIN)", value=False)
    run = st.button("▶ Run Query", type="primary")

    if run:
        if not sql.strip():
            st.warning("Please enter a query.")
        else:
            # Safety: block writes
            first_word = sql.strip().split()[0].upper()
            if first_word not in ("SELECT", "EXPLAIN", "WITH"):
                st.error("Only SELECT / WITH / EXPLAIN queries are allowed.")
            else:
                try:
                    # Run the actual query
                    df = con.execute(sql).df()
                    st.success(f"Returned {len(df):,} rows")
                    st.dataframe(df, use_container_width=True, hide_index=True)

                    # Optional EXPLAIN
                    if show_explain:
                        st.subheader("Query Plan")
                        plan = con.execute(f"EXPLAIN {sql}").fetchall()
                        st.code("\n".join(row[1] for row in plan), language="text")

                except Exception as e:
                    st.error(f"Query error: {e}")
