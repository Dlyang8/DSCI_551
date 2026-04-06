"""
setup_db.py
Loads CSV files from data/ into a persistent DuckDB database file (nba.duckdb).

Run once from inside your project folder:
    python setup_db.py
"""

import os
import duckdb

# Create nba.duckdb in the same folder as this script
db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "nba.duckdb")
con = duckdb.connect(db_path)

print(f"Creating database at: {db_path}")

# Drop and recreate tables so this script is safe to re-run
con.execute("DROP TABLE IF EXISTS PlayerBoxScores")
con.execute("DROP TABLE IF EXISTS Players")
con.execute("DROP TABLE IF EXISTS Games")

con.execute("""
    CREATE TABLE Games (
        GAME_ID      VARCHAR PRIMARY KEY,
        GAME_DATE    DATE,
        HOME_TEAM    VARCHAR,
        AWAY_TEAM    VARCHAR,
        SEASON_TYPE  VARCHAR
    )
""")

con.execute("""
    CREATE TABLE Players (
        PLAYER_ID    INTEGER PRIMARY KEY,
        PLAYER_NAME  VARCHAR,
        TEAM         VARCHAR
    )
""")

con.execute("""
    CREATE TABLE PlayerBoxScores (
        GAME_ID           VARCHAR,
        PLAYER_ID         INTEGER,
        PLAYER_NAME       VARCHAR,
        TEAM_ABBREVIATION VARCHAR,
        MIN               VARCHAR,
        PTS               DOUBLE,
        REB               DOUBLE,
        AST               DOUBLE,
        STL               DOUBLE,
        BLK               DOUBLE,
        TOV               DOUBLE,
        FGM               DOUBLE,
        FGA               DOUBLE,
        FG_PCT            DOUBLE,
        FG3M              DOUBLE,
        FG3A              DOUBLE,
        FG3_PCT           DOUBLE,
        FTM               DOUBLE,
        FTA               DOUBLE,
        FT_PCT            DOUBLE,
        PLUS_MINUS        DOUBLE,
        GAME_DATE         DATE,
        SEASON_TYPE       VARCHAR
    )
""")

# DuckDB reads CSVs natively — no pandas needed
print("Loading Games...")
con.execute("INSERT INTO Games SELECT * FROM read_csv_auto('data/games.csv')")

print("Loading Players...")
con.execute("INSERT INTO Players SELECT * FROM read_csv_auto('data/players.csv')")

print("Loading PlayerBoxScores...")
con.execute("INSERT INTO PlayerBoxScores SELECT * FROM read_csv_auto('data/player_boxscores.csv')")

# Verify row counts
games_count    = con.execute("SELECT COUNT(*) FROM Games").fetchone()[0]
players_count  = con.execute("SELECT COUNT(*) FROM Players").fetchone()[0]
boxscore_count = con.execute("SELECT COUNT(*) FROM PlayerBoxScores").fetchone()[0]

print(f"\nDone!")
print(f"   Games:           {games_count:,}")
print(f"   Players:         {players_count:,}")
print(f"   PlayerBoxScores: {boxscore_count:,}")

con.close()
