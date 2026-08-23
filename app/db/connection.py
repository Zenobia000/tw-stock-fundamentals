import sqlite3
import threading
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[2] / "data" / "app.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"

# schema.sql 是 CREATE TABLE/INDEX IF NOT EXISTS，重跑本身是安全的，但它是一次
# executescript DDL，SQLite 對 DDL 要求獨佔鎖；如果每個請求的 get_connection()
# 都重跑一次，多個請求同時進來（例如頁面一次發出好幾個 fetch）就會互搶這把鎖，
# 逾時後噴 "database is locked" 500。同一個行程對同一個 db_path 只需要跑一次，
# 用鎖＋集合把「這個路徑本行程是否已初始化」記住，後續呼叫只開連線、不重跑 DDL。
#
# 這把鎖同時也要包住 sqlite3.connect() 本身跟 PRAGMA journal_mode = WAL：
# 切換成 WAL 模式需要當下沒有其他連線在存取同一個檔案，第一次對全新資料庫
# 檔案多執行緒同時 connect() 時，多個連線同時搶著切 WAL 模式一樣會噴
# "database is locked"（這不是 DDL，busy_timeout 對這個場景不保證有效）。
_initialized_paths: set[Path] = set()
_init_lock = threading.Lock()


def _ensure_column(
    conn: sqlite3.Connection, table: str, column: str, definition: str
) -> None:
    """CREATE TABLE 不會替既有 SQLite 表補欄位；用可重複 migration 保留舊 DB。"""
    columns = {
        row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def get_connection(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_path = db_path.resolve()

    with _init_lock:
        # FastAPI 對 sync 的 dependency（這支函式）跟 sync 的 route handler 各自透過
        # anyio threadpool 執行，兩者不保證分到同一條 thread；預設 check_same_thread=True
        # 會在「建立連線的 thread」跟「實際用連線的 thread」不同時直接噴
        # sqlite3.ProgrammingError。這個連線本來就是每個 request 各自新開、不跨
        # request 共用，關掉這個檢查是安全的。
        conn = sqlite3.connect(db_path, timeout=5, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        # 個人單機部署以 WAL 允許讀取與單一寫入並行；NORMAL 是 SQLite WAL
        # 建議的效能／耐久折衷。若未來改為多主機多寫入，再升級 PostgreSQL。
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")

        if resolved_path not in _initialized_paths:
            conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
            _ensure_column(conn, "market_cap_daily", "rank", "INTEGER")
            _ensure_column(conn, "market_cap_daily", "name", "TEXT")
            _ensure_column(conn, "cashflow_quarterly", "capital_expenditure", "REAL")
            _ensure_column(conn, "cashflow_quarterly", "free_cash_flow", "REAL")
            _ensure_column(conn, "cashflow_quarterly", "operating_plus_investing", "REAL")
            _ensure_column(conn, "cashflow_quarterly", "source", "TEXT")
            _ensure_column(conn, "capital_reductions", "stop_date", "TEXT")
            _ensure_column(conn, "capital_reductions", "exchange_ratio", "REAL")
            _ensure_column(conn, "capital_reductions", "reason", "TEXT")
            _ensure_column(conn, "capital_reductions", "source", "TEXT")
            _ensure_column(conn, "capital_reductions", "fetched_at", "TEXT")
            _ensure_column(conn, "rankings_daily", "source", "TEXT NOT NULL DEFAULT 'unknown'")
            _ensure_column(
                conn, "stock_universe_top100", "source", "TEXT NOT NULL DEFAULT 'unknown'"
            )
            _ensure_column(conn, "ingestion_runs", "duration_ms", "REAL")
            _ensure_column(conn, "ingestion_runs", "http_status", "INTEGER")
            _ensure_column(conn, "ingestion_runs", "error_type", "TEXT")
            # 這張表在 source 欄位加入前只有 FinMind 腳本會寫入，故可確定舊列血緣。
            conn.execute(
                """
                UPDATE stock_universe_top100
                SET source = 'finmind-market-value'
                WHERE source = 'unknown'
                """
            )
            conn.commit()
            _initialized_paths.add(resolved_path)
    return conn
