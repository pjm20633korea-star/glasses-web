"""
데이터베이스 연결 및 테이블 생성 모듈
SQLite 파일 하나로 동작 (optical.db)
"""
import secrets
import sqlite3
from contextlib import contextmanager

import bcrypt

DB_PATH = "optical.db"

_SPEC_EYE_COLS = """
    {p}_sph REAL, {p}_cyl REAL, {p}_axis REAL,
    {p}_far_pd REAL, {p}_add REAL, {p}_near_pd REAL,
    {p}_oh REAL,
    {p}_prism_h REAL, {p}_base_io TEXT,
    {p}_prism_v REAL, {p}_base_ud TEXT,
    {p}_va_uncorrected TEXT, {p}_va_corrected TEXT
"""

_CL_EYE_COLS = """
    {p}_cl_sph REAL, {p}_cl_cyl REAL, {p}_cl_axis REAL, {p}_cl_add REAL,
    {p}_cl_bc REAL, {p}_cl_dia REAL, {p}_cl_kerato TEXT
"""

# 매출/결제 정보 (한 방문 = 검안 1건 + 매출/결제 1건)
_SALE_PAYMENT_COLS = """
    sale_total REAL,
    cash_checked INTEGER, cash_amount REAL,
    card_checked INTEGER, card_amount REAL,
    giftcard_checked INTEGER, giftcard_amount REAL,
    unpaid_amount REAL,
    cash_receipt_type TEXT,
    card_type TEXT,
    giftcard_type TEXT,
    discount REAL,
    visit_cycle_months REAL,
    completion_date TEXT,
    staff_manager TEXT,
    staff_seller TEXT,
    sale_memo TEXT
"""


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # ---- 매장(테넌시) / 그룹 ----
    # 매장은 정확히 하나의 그룹에 속함. 같은 그룹 매장끼리는 서로 데이터를 읽기 전용으로 조회할 수 있음
    cur.execute("""
    CREATE TABLE IF NOT EXISTS store_groups (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now', 'localtime'))
    )
    """)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS stores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        login_id TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        group_id INTEGER NOT NULL,
        is_admin INTEGER DEFAULT 0,
        created_at TEXT DEFAULT (datetime('now', 'localtime')),
        FOREIGN KEY (group_id) REFERENCES store_groups (id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        gender TEXT,
        phone TEXT,
        phone2 TEXT,
        birth_date TEXT,
        dominant_eye TEXT,
        occupation TEXT,
        email TEXT,
        address TEXT,
        note TEXT,
        created_at TEXT DEFAULT (datetime('now', 'localtime'))
    )
    """)

    exam_cols = (
        _SPEC_EYE_COLS.format(p="od") + "," +
        _SPEC_EYE_COLS.format(p="os") + "," +
        _CL_EYE_COLS.format(p="od") + "," +
        _CL_EYE_COLS.format(p="os") + "," +
        _SALE_PAYMENT_COLS
    )

    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS exams (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL,
        exam_date TEXT NOT NULL,
        {exam_cols},
        prescription_memo TEXT,
        FOREIGN KEY (customer_id) REFERENCES customers (id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS sale_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        exam_id INTEGER NOT NULL,
        category TEXT,
        brand TEXT,
        product_name TEXT,
        color TEXT,
        quantity REAL,
        unit_price REAL,
        FOREIGN KEY (exam_id) REFERENCES exams (id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS visits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL,
        visit_date TEXT NOT NULL,
        note TEXT,
        FOREIGN KEY (customer_id) REFERENCES customers (id)
    )
    """)

    # 반품 내역 (미수 잔액 자체는 별도 테이블 없이 exams.unpaid_amount를 그대로 조회해서 사용)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS returns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL,
        exam_id INTEGER,
        return_date TEXT NOT NULL,
        product_name TEXT,
        amount REAL,
        reason TEXT,
        created_at TEXT DEFAULT (datetime('now', 'localtime')),
        FOREIGN KEY (customer_id) REFERENCES customers (id)
    )
    """)
    _migrate_add_column(cur, "returns", "refund_method", "TEXT")
    _migrate_add_column(cur, "returns", "items_detail", "TEXT")
    _migrate_add_column(cur, "returns", "cash_refund", "REAL")
    _migrate_add_column(cur, "returns", "card_refund", "REAL")
    _migrate_add_column(cur, "returns", "giftcard_refund", "REAL")
    _migrate_add_column(cur, "returns", "discount_cancel", "REAL")
    _migrate_add_column(cur, "returns", "unpaid_offset", "REAL")
    _migrate_add_column(cur, "returns", "staff", "TEXT")

    # 미수금을 정산 처리한 기록 (언제, 결제정보별로 얼마씩 받았는지)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS settlements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_id INTEGER NOT NULL,
        exam_id INTEGER,
        settle_date TEXT NOT NULL,
        amount REAL,
        payment_method TEXT,
        created_at TEXT DEFAULT (datetime('now', 'localtime')),
        FOREIGN KEY (customer_id) REFERENCES customers (id)
    )
    """)
    _migrate_add_column(cur, "settlements", "cash_amount", "REAL")
    _migrate_add_column(cur, "settlements", "card_amount", "REAL")
    _migrate_add_column(cur, "settlements", "giftcard_amount", "REAL")
    _migrate_add_column(cur, "settlements", "discount", "REAL")
    _migrate_add_column(cur, "settlements", "card_type", "TEXT")
    _migrate_add_column(cur, "settlements", "giftcard_type", "TEXT")
    _migrate_add_column(cur, "settlements", "point_option", "TEXT")
    _migrate_add_column(cur, "settlements", "staff", "TEXT")
    _migrate_add_column(cur, "settlements", "seller", "TEXT")
    _migrate_add_column(cur, "settlements", "cash_receipt", "TEXT")
    _migrate_add_column(cur, "settlements", "memo", "TEXT")

    _migrate_add_column(cur, "customers", "phone2", "TEXT")

    # exams에 남아있던 sale_type 구분(예전 방식) - 더는 쓰지 않지만 컬럼 자체는 SQLite 제약상 그대로 둠
    _migrate_add_column(cur, "exams", "sale_type", "TEXT", default="'exam'")
    # created_at은 SQLite가 ALTER TABLE에서 datetime('now') 같은 비상수 기본값을 허용하지 않으므로,
    # 컬럼만 추가하고 새 저장 시 main.py에서 직접 값을 채움. 기존 기록은 방문일자로 채워줌
    is_new_created_at_col = "created_at" not in [row[1] for row in cur.execute("PRAGMA table_info(exams)").fetchall()]
    _migrate_add_column(cur, "exams", "created_at", "TEXT")
    if is_new_created_at_col:
        cur.execute("UPDATE exams SET created_at = exam_date || ' 00:00:00' WHERE created_at IS NULL")

    # ---- 일반판매 (고객 정보 없이 - 어떤 고객/비회원에도 연결하지 않는 독립된 판매 기록) ----
    # 매출현황에서만 조회/수정할 수 있고, 고객 목록·방문내역·미수금현황 등 고객 관련 화면에는 전혀 나타나지 않음
    general_sale_cols = (
        _SPEC_EYE_COLS.format(p="od") + "," +
        _SPEC_EYE_COLS.format(p="os") + "," +
        _CL_EYE_COLS.format(p="od") + "," +
        _CL_EYE_COLS.format(p="os") + "," +
        _SALE_PAYMENT_COLS
    )
    cur.execute(f"""
    CREATE TABLE IF NOT EXISTS general_sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sale_date TEXT NOT NULL,
        created_at TEXT,
        {general_sale_cols},
        prescription_memo TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS general_sale_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        general_sale_id INTEGER NOT NULL,
        category TEXT,
        brand TEXT,
        product_name TEXT,
        color TEXT,
        quantity REAL,
        unit_price REAL,
        FOREIGN KEY (general_sale_id) REFERENCES general_sales (id)
    )
    """)

    # ---- A/S전표 (수리 접수) ----
    cur.execute("""
    CREATE TABLE IF NOT EXISTS as_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_name TEXT,
        phone1 TEXT,
        phone2 TEXT,
        receive_date TEXT NOT NULL,
        contact_method TEXT,
        mobile1 TEXT,
        mobile2 TEXT,
        finish_date TEXT,
        delivery_method TEXT,
        address TEXT,
        brand TEXT,
        product_name TEXT,
        part_rim INTEGER,
        part_bridge INTEGER,
        part_temple INTEGER,
        part_nosepad INTEGER,
        part_etc INTEGER,
        part_etc_detail TEXT,
        content TEXT,
        repair_type TEXT,
        cash_receipt INTEGER,
        deposit REAL,
        balance REAL,
        total REAL,
        print_vendor INTEGER,
        created_at TEXT,
        store_id INTEGER
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS general_sale_returns (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        general_sale_id INTEGER NOT NULL,
        return_date TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now', 'localtime')),
        product_name TEXT,
        amount REAL,
        items_detail TEXT,
        cash_refund REAL,
        card_refund REAL,
        giftcard_refund REAL,
        discount_cancel REAL,
        staff TEXT,
        reason TEXT,
        FOREIGN KEY (general_sale_id) REFERENCES general_sales (id)
    )
    """)

    # ---- 그룹 채팅: 같은 그룹(store_groups)에 속한 매장끼리만 서로 보이는 메시지 ----
    cur.execute("""
    CREATE TABLE IF NOT EXISTS group_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        group_id INTEGER NOT NULL,
        store_id INTEGER NOT NULL,
        content TEXT NOT NULL,
        created_at TEXT DEFAULT (datetime('now', 'localtime')),
        FOREIGN KEY (group_id) REFERENCES store_groups (id),
        FOREIGN KEY (store_id) REFERENCES stores (id)
    )
    """)

    # ---- 매장 격리: 데이터가 저장되는 9개 테이블 전부에 직접 store_id를 둠
    # (부모 테이블을 거치지 않고 바로 필터링할 수 있어야 JOIN 누락으로 다른 매장 데이터가
    #  새어나가는 사고를 막을 수 있음 - 자식 테이블에도 예외 없이 전부 추가)
    for table in (
        "customers", "exams", "sale_items", "visits", "returns", "settlements",
        "general_sales", "general_sale_items", "general_sale_returns", "as_records",
    ):
        _migrate_add_column(cur, table, "store_id", "INTEGER")

    conn.commit()

    # ---- 첫 실행 시(매장이 하나도 없으면): 그룹1 + Store 1을 자동으로 만들고,
    #      이미 쌓여있던 기존 데이터를 전부 Store 1 소유로 배정함 ----
    if cur.execute("SELECT COUNT(*) FROM stores").fetchone()[0] == 0:
        cur.execute("INSERT INTO store_groups (name) VALUES (?)", ("Store 1 그룹",))
        group_id = cur.lastrowid
        temp_password = secrets.token_urlsafe(9)
        password_hash = bcrypt.hashpw(temp_password.encode(), bcrypt.gensalt()).decode()
        cur.execute(
            "INSERT INTO stores (name, login_id, password_hash, group_id, is_admin) VALUES (?, ?, ?, ?, 1)",
            ("Store 1", "store1", password_hash, group_id),
        )
        store_id = cur.lastrowid
        for table in (
            "customers", "exams", "sale_items", "visits", "returns", "settlements",
            "general_sales", "general_sale_items", "general_sale_returns", "as_records",
        ):
            cur.execute(f"UPDATE {table} SET store_id = ? WHERE store_id IS NULL", (store_id,))
        conn.commit()
        print("=" * 60)
        print("[최초 실행] 매장 계정이 자동으로 만들어졌습니다. 로그인 후 꼭 비밀번호를 바꿔주세요.")
        print(f"  로그인 ID: store1")
        print(f"  임시 비밀번호: {temp_password}")
        print("=" * 60)

    conn.close()


def _migrate_add_column(cur, table, column, coltype, default=None):
    """이미 만들어진 DB 파일에도 새 컬럼을 안전하게 추가합니다.
    (컬럼이 이미 있으면 조용히 넘어감 - optical.db를 지우지 않아도 됩니다)"""
    existing = [row[1] for row in cur.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in existing:
        clause = f"ALTER TABLE {table} ADD COLUMN {column} {coltype}"
        if default is not None:
            clause += f" DEFAULT {default}"
        cur.execute(clause)


@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()
