"""
안경원 고객관리/검안정보 웹앱 - 1단계 MVP (확장판: 매출/결제 포함, 저장 통합)
실행: uvicorn main:app --reload
접속: http://localhost:8000
"""
import json
import os
import time
import uuid
from datetime import date, datetime
from pathlib import Path
from typing import List, Optional

import bcrypt
from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from database import init_db, get_db, DB_PATH

app = FastAPI(title="안경원 고객관리 시스템")

# 세션 쿠키 서명용 비밀키. 운영 배포 시에는 반드시 SESSION_SECRET 환경변수로 별도 지정해야 함
# (지정하지 않으면 개발용 임시 키를 씀 - 서버 재시작해도 로그인이 풀리지 않도록 고정값으로 둠)
SESSION_SECRET = os.environ.get("SESSION_SECRET") or "dev-only-insecure-secret-change-me"
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)


# ---------- 요청/응답 데이터 모델 ----------

class CustomerIn(BaseModel):
    name: str
    gender: Optional[str] = None
    phone: Optional[str] = None
    phone2: Optional[str] = None
    birth_date: Optional[str] = None
    dominant_eye: Optional[str] = None
    occupation: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    note: Optional[str] = None


class SaleItemIn(BaseModel):
    category: Optional[str] = None
    brand: Optional[str] = None
    product_name: Optional[str] = None
    color: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None


class ReturnItemIn(BaseModel):
    id: Optional[int] = None
    category: Optional[str] = None
    brand: Optional[str] = None
    product_name: Optional[str] = None
    color: Optional[str] = None
    quantity: Optional[float] = None
    unit_price: Optional[float] = None


class ReturnIn(BaseModel):
    return_date: Optional[str] = None
    exam_id: Optional[int] = None
    product_name: Optional[str] = None
    items: Optional[List[ReturnItemIn]] = None
    amount: Optional[float] = 0
    cash_refund: Optional[float] = 0
    card_refund: Optional[float] = 0
    giftcard_refund: Optional[float] = 0
    discount_cancel: Optional[float] = 0
    unpaid_offset: Optional[float] = 0
    staff: Optional[str] = None
    reason: Optional[str] = None
    refund_method: Optional[str] = None


class SettleIn(BaseModel):
    settle_date: Optional[str] = None
    cash_amount: Optional[float] = 0
    card_amount: Optional[float] = 0
    giftcard_amount: Optional[float] = 0
    discount: Optional[float] = 0
    card_type: Optional[str] = None
    giftcard_type: Optional[str] = None
    point_option: Optional[str] = None
    staff: Optional[str] = None
    seller: Optional[str] = None
    cash_receipt: Optional[str] = None
    memo: Optional[str] = None


class ASRecordIn(BaseModel):
    customer_name: Optional[str] = None
    phone1: Optional[str] = None
    phone2: Optional[str] = None
    receive_date: Optional[str] = None
    contact_method: Optional[str] = None
    mobile1: Optional[str] = None
    mobile2: Optional[str] = None
    finish_date: Optional[str] = None
    delivery_method: Optional[str] = None
    address: Optional[str] = None
    brand: Optional[str] = None
    product_name: Optional[str] = None
    part_rim: Optional[bool] = False
    part_bridge: Optional[bool] = False
    part_temple: Optional[bool] = False
    part_nosepad: Optional[bool] = False
    part_etc: Optional[bool] = False
    part_etc_detail: Optional[str] = None
    content: Optional[str] = None
    repair_type: Optional[str] = None
    cash_receipt: Optional[bool] = False
    deposit: Optional[float] = 0
    balance: Optional[float] = 0
    total: Optional[float] = 0
    print_vendor: Optional[bool] = False


AS_RECORD_FIELDS = [f for f in ASRecordIn.__fields__.keys() if f != "receive_date"]


class ExamIn(BaseModel):
    exam_date: Optional[str] = None
    sale_type: Optional[str] = "exam"  # "exam"=검안매출(판매), "general"=일반판매

    # ---- 안경(굴절) - 우안(OD) ----
    od_sph: Optional[float] = None
    od_cyl: Optional[float] = None
    od_axis: Optional[float] = None
    od_far_pd: Optional[float] = None
    od_add: Optional[float] = None
    od_near_pd: Optional[float] = None
    od_oh: Optional[float] = None
    od_prism_h: Optional[float] = None
    od_base_io: Optional[str] = None
    od_prism_v: Optional[float] = None
    od_base_ud: Optional[str] = None
    od_va_uncorrected: Optional[str] = None
    od_va_corrected: Optional[str] = None

    # ---- 안경(굴절) - 좌안(OS) ----
    os_sph: Optional[float] = None
    os_cyl: Optional[float] = None
    os_axis: Optional[float] = None
    os_far_pd: Optional[float] = None
    os_add: Optional[float] = None
    os_near_pd: Optional[float] = None
    os_oh: Optional[float] = None
    os_prism_h: Optional[float] = None
    os_base_io: Optional[str] = None
    os_prism_v: Optional[float] = None
    os_base_ud: Optional[str] = None
    os_va_uncorrected: Optional[str] = None
    os_va_corrected: Optional[str] = None

    # ---- 콘택트렌즈 - 우안(OD) ----
    od_cl_sph: Optional[float] = None
    od_cl_cyl: Optional[float] = None
    od_cl_axis: Optional[float] = None
    od_cl_add: Optional[float] = None
    od_cl_bc: Optional[float] = None
    od_cl_dia: Optional[float] = None
    od_cl_kerato: Optional[str] = None

    # ---- 콘택트렌즈 - 좌안(OS) ----
    os_cl_sph: Optional[float] = None
    os_cl_cyl: Optional[float] = None
    os_cl_axis: Optional[float] = None
    os_cl_add: Optional[float] = None
    os_cl_bc: Optional[float] = None
    os_cl_dia: Optional[float] = None
    os_cl_kerato: Optional[str] = None

    prescription_memo: Optional[str] = None

    # ---- 매출/결제 ----
    sale_total: Optional[float] = None
    cash_checked: Optional[bool] = None
    cash_amount: Optional[float] = None
    card_checked: Optional[bool] = None
    card_amount: Optional[float] = None
    giftcard_checked: Optional[bool] = None
    giftcard_amount: Optional[float] = None
    unpaid_amount: Optional[float] = None
    cash_receipt_type: Optional[str] = None
    card_type: Optional[str] = None
    giftcard_type: Optional[str] = None
    discount: Optional[float] = None
    visit_cycle_months: Optional[float] = None
    completion_date: Optional[str] = None
    staff_manager: Optional[str] = None
    staff_seller: Optional[str] = None
    sale_memo: Optional[str] = None

    sale_items: List[SaleItemIn] = []


EXCLUDE_FROM_EXAM_TABLE = {"exam_date", "sale_items"}
EXAM_FIELDS = [f for f in ExamIn.__fields__.keys() if f not in EXCLUDE_FROM_EXAM_TABLE]
# 일반판매(general_sales) 테이블에는 sale_type 컬럼이 없으므로 그 필드만 뺌
GENERAL_SALE_FIELDS = [f for f in EXAM_FIELDS if f != "sale_type"]


# ---------- 검안 수치 범위 검증 ----------
# 안경광학 표준값 기준. 화면(index.html)의 FIELD_SPECS와 같은 값을 사용합니다.
# 프런트엔드에서 이미 확인하지만, API로 직접 들어오는 값도 막기 위해 서버에서도 검사합니다.
FIELD_RANGES = {
    "sph":     (-25, 25),
    "cyl":     (-10, 10),
    "axis":    (1, 180),
    "far_pd":  (20, 80),
    "add":     (0, 4),
    "near_pd": (20, 80),
    "oh":      (5, 40),
    "prism_h": (0, 15),
    "prism_v": (0, 15),
    "cl_sph":  (-25, 25),
    "cl_cyl":  (-10, 10),
    "cl_axis": (1, 180),
    "cl_add":  (0, 4),
    "cl_bc":   (7.5, 10.5),
    "cl_dia":  (12, 15.5),
}


def validate_exam_ranges(exam: "ExamIn") -> None:
    """검안 수치가 물리적으로 불가능한 범위면 400 오류를 돌려줍니다."""
    data = exam.dict(exclude={"sale_items"})
    errors = []
    for field, value in data.items():
        if value is None or not isinstance(value, (int, float)):
            continue
        if not (field.startswith("od_") or field.startswith("os_")):
            continue

        key = field[3:]  # od_ / os_ 접두사 제거
        bounds = FIELD_RANGES.get(key)
        if not bounds:
            continue

        low, high = bounds
        if not (low <= value <= high):
            eye = "OD(우안)" if field.startswith("od_") else "OS(좌안)"
            errors.append(f"{eye} {key}: {value} (허용 범위 {low}~{high})")

    if errors:
        raise HTTPException(
            status_code=400,
            detail="검안 수치가 허용 범위를 벗어났습니다: " + "; ".join(errors),
        )


# ---------- 매장 인증/격리 헬퍼 (백업 등 아래 엔드포인트들이 바로 써야 해서 먼저 정의함) ----------

def get_current_store(request: Request) -> dict:
    """세션 쿠키로 로그인한 매장을 찾음. 로그인 안 되어 있으면 401"""
    store_id = request.session.get("store_id")
    if not store_id:
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    with get_db() as conn:
        row = conn.execute("SELECT * FROM stores WHERE id = ?", (store_id,)).fetchone()
    if not row:
        request.session.clear()
        raise HTTPException(status_code=401, detail="로그인이 필요합니다")
    return dict(row)


def require_admin(store: dict = Depends(get_current_store)) -> dict:
    if not store["is_admin"]:
        raise HTTPException(status_code=403, detail="관리자만 사용할 수 있습니다")
    return store


def get_group_store_ids(store: dict) -> List[int]:
    """이 매장과 같은 그룹(=데이터를 서로 읽기 공유하는 매장들)의 id 목록. 본인도 포함됨"""
    with get_db() as conn:
        rows = conn.execute("SELECT id FROM stores WHERE group_id = ?", (store["group_id"],)).fetchall()
    return [r["id"] for r in rows]


def _in_placeholders(ids: List[int]) -> str:
    return ",".join(["?"] * len(ids)) if ids else "NULL"


# ---------- 백업 ----------
# optical.db 파일 하나를 그대로 복사하면 마침 쓰기 작업 중일 때 깨질 수 있으므로,
# SQLite가 공식으로 제공하는 VACUUM INTO로 항상 손상 없는 완전한 스냅샷을 떠서 backups 폴더에 저장함
BACKUP_DIR = Path("backups")

# ---------- 채팅 사진/파일 첨부 ----------
CHAT_UPLOAD_DIR = Path("chat_uploads")
CHAT_UPLOAD_MAX_SIZE = 10 * 1024 * 1024  # 10MB
# content-type을 신뢰하되 저장 파일명 확장자는 서버가 직접 정함(업로드된 파일명을 그대로 쓰지 않음)
CHAT_UPLOAD_ALLOWED_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
    "application/msword": ".doc",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/vnd.ms-excel": ".xls",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
    "text/plain": ".txt",
    "application/zip": ".zip",
    "application/x-zip-compressed": ".zip",
}


def _do_backup(prefix: str) -> tuple[str, int]:
    BACKUP_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"optical_backup_{prefix}_{timestamp}.db"
    backup_path = BACKUP_DIR / filename
    with get_db() as conn:
        conn.execute(f"VACUUM INTO '{backup_path.as_posix()}'")
    return filename, backup_path.stat().st_size


def _prune_auto_backups(keep: int = 30):
    """자동 백업은 매일 쌓이므로 오래된 것부터 정리함 (수동 백업은 사용자가 일부러 남긴 것이라 절대 지우지 않음)"""
    autos = sorted(BACKUP_DIR.glob("optical_backup_auto_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in autos[keep:]:
        old.unlink(missing_ok=True)


@app.post("/api/backup")
def create_backup(admin: dict = Depends(require_admin)):
    """지금 이 순간 전체 데이터(모든 매장의 고객/검안/매출/반품/미수 등 전부)의 스냅샷을 backups 폴더에 저장함
    (여러 매장 데이터가 한 파일에 다 들어있으므로 관리자만 실행할 수 있음)"""
    filename, size = _do_backup("manual")
    return {"filename": filename, "size": size}


@app.get("/api/backups")
def list_backups(admin: dict = Depends(require_admin)):
    if not BACKUP_DIR.exists():
        return []
    files = sorted(BACKUP_DIR.glob("optical_backup_*.db"), key=lambda p: p.stat().st_mtime, reverse=True)
    return [
        {
            "filename": f.name,
            "size": f.stat().st_size,
            "created_at": datetime.fromtimestamp(f.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "kind": "manual" if "_manual_" in f.name else "auto",
        }
        for f in files
    ]


# ---------- 시작 시 DB 초기화 + 하루 한 번 자동 백업 ----------

@app.on_event("startup")
def on_startup():
    init_db()
    try:
        BACKUP_DIR.mkdir(exist_ok=True)
        autos = list(BACKUP_DIR.glob("optical_backup_auto_*.db"))
        latest_age_hours = (
            (time.time() - max(p.stat().st_mtime for p in autos)) / 3600 if autos else 999
        )
        if latest_age_hours >= 20:  # 서버를 자주 재시작해도 하루 한 번 정도만 자동 백업함
            _do_backup("auto")
            _prune_auto_backups()
    except Exception as e:
        print(f"[자동 백업 실패 - 무시하고 계속 진행] {e}")


# ---------- 매장 로그인 / 인증 ----------

class LoginIn(BaseModel):
    login_id: str
    password: str


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


class ChangeLoginIdIn(BaseModel):
    current_password: str
    new_login_id: str


class StoreCreateIn(BaseModel):
    name: str
    login_id: str
    password: str
    group_id: Optional[int] = None  # 없으면 이 매장만의 새 그룹을 만듦(=독립 매장)
    is_admin: bool = False


class StoreGroupCreateIn(BaseModel):
    name: str


class StoreGroupUpdateIn(BaseModel):
    group_id: int


class StoreUpdateIn(BaseModel):
    name: str
    login_id: str
    is_admin: bool = False
    new_password: Optional[str] = None  # 비워두면 비밀번호는 그대로 유지


class GroupRenameIn(BaseModel):
    name: str


class ChatMessageIn(BaseModel):
    content: str


@app.post("/api/login")
def login(body: LoginIn, request: Request):
    with get_db() as conn:
        row = conn.execute("SELECT * FROM stores WHERE login_id = ?", (body.login_id,)).fetchone()
    if not row or not bcrypt.checkpw(body.password.encode(), row["password_hash"].encode()):
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 올바르지 않습니다")
    request.session["store_id"] = row["id"]
    return {"ok": True, "name": row["name"]}


@app.post("/api/logout")
def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@app.get("/api/me")
def me(store: dict = Depends(get_current_store)):
    with get_db() as conn:
        group = conn.execute("SELECT name FROM store_groups WHERE id = ?", (store["group_id"],)).fetchone()
    return {
        "id": store["id"], "name": store["name"], "login_id": store["login_id"],
        "is_admin": bool(store["is_admin"]), "group_id": store["group_id"],
        "group_name": group["name"] if group else None,
    }


@app.post("/api/change-password")
def change_password(body: ChangePasswordIn, store: dict = Depends(get_current_store)):
    if not bcrypt.checkpw(body.current_password.encode(), store["password_hash"].encode()):
        raise HTTPException(status_code=400, detail="현재 비밀번호가 올바르지 않습니다")
    new_hash = bcrypt.hashpw(body.new_password.encode(), bcrypt.gensalt()).decode()
    with get_db() as conn:
        conn.execute("UPDATE stores SET password_hash = ? WHERE id = ?", (new_hash, store["id"]))
        conn.commit()
    return {"ok": True}


@app.post("/api/change-login-id")
def change_login_id(body: ChangeLoginIdIn, request: Request, store: dict = Depends(get_current_store)):
    if not bcrypt.checkpw(body.current_password.encode(), store["password_hash"].encode()):
        raise HTTPException(status_code=400, detail="현재 비밀번호가 올바르지 않습니다")
    new_login_id = body.new_login_id.strip()
    if not new_login_id:
        raise HTTPException(status_code=400, detail="새 로그인 ID를 입력해 주세요")
    with get_db() as conn:
        try:
            conn.execute("UPDATE stores SET login_id = ? WHERE id = ?", (new_login_id, store["id"]))
            conn.commit()
        except Exception:
            raise HTTPException(status_code=400, detail="이미 사용 중인 로그인 ID입니다")
    request.session["store_id"] = store["id"]
    return {"ok": True, "login_id": new_login_id}


# ---------- 매장/그룹 관리 (관리자 전용) ----------

@app.get("/api/admin/stores")
def admin_list_stores(admin: dict = Depends(require_admin)):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT s.id, s.name, s.login_id, s.group_id, s.is_admin, g.name AS group_name
            FROM stores s JOIN store_groups g ON g.id = s.group_id
            ORDER BY s.id
        """).fetchall()
    return [dict(r) for r in rows]


@app.post("/api/admin/stores")
def admin_create_store(body: StoreCreateIn, admin: dict = Depends(require_admin)):
    with get_db() as conn:
        group_id = body.group_id
        if not group_id:
            cur = conn.execute("INSERT INTO store_groups (name) VALUES (?)", (f"{body.name} 그룹",))
            group_id = cur.lastrowid
        password_hash = bcrypt.hashpw(body.password.encode(), bcrypt.gensalt()).decode()
        try:
            cur = conn.execute(
                "INSERT INTO stores (name, login_id, password_hash, group_id, is_admin) VALUES (?, ?, ?, ?, ?)",
                (body.name, body.login_id, password_hash, group_id, int(body.is_admin)),
            )
        except Exception:
            raise HTTPException(status_code=400, detail="이미 사용 중인 로그인 ID입니다")
        conn.commit()
        return {"id": cur.lastrowid, "group_id": group_id}


@app.put("/api/admin/stores/{store_id}/group")
def admin_update_store_group(store_id: int, body: StoreGroupUpdateIn, admin: dict = Depends(require_admin)):
    """매장을 다른 그룹으로 옮김 (같은 그룹 매장끼리 데이터를 서로 읽기 공유하게 됨)"""
    with get_db() as conn:
        cur = conn.execute("UPDATE stores SET group_id = ? WHERE id = ?", (body.group_id, store_id))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="매장을 찾을 수 없습니다")
        return {"ok": True}


@app.put("/api/admin/stores/{store_id}")
def admin_update_store(store_id: int, body: StoreUpdateIn, admin: dict = Depends(require_admin)):
    """매장 이름/로그인ID/관리자여부 수정. new_password를 채우면 비밀번호도 함께 재설정(비밀번호 찾기용)"""
    with get_db() as conn:
        row = conn.execute("SELECT id FROM stores WHERE id = ?", (store_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="매장을 찾을 수 없습니다")
        if store_id == admin["id"] and not body.is_admin:
            raise HTTPException(status_code=400, detail="현재 로그인한 관리자 계정의 관리자 권한은 스스로 해제할 수 없습니다")
        try:
            if body.new_password:
                new_hash = bcrypt.hashpw(body.new_password.encode(), bcrypt.gensalt()).decode()
                conn.execute(
                    "UPDATE stores SET name = ?, login_id = ?, is_admin = ?, password_hash = ? WHERE id = ?",
                    (body.name, body.login_id, int(body.is_admin), new_hash, store_id),
                )
            else:
                conn.execute(
                    "UPDATE stores SET name = ?, login_id = ?, is_admin = ? WHERE id = ?",
                    (body.name, body.login_id, int(body.is_admin), store_id),
                )
        except Exception:
            raise HTTPException(status_code=400, detail="이미 사용 중인 로그인 ID입니다")
        conn.commit()
        return {"ok": True}


DATA_TABLES_FOR_STORE = [
    "customers", "exams", "sale_items", "visits", "returns", "settlements",
    "general_sales", "general_sale_items", "general_sale_returns",
]


@app.delete("/api/admin/stores/{store_id}")
def admin_delete_store(store_id: int, admin: dict = Depends(require_admin)):
    if store_id == admin["id"]:
        raise HTTPException(status_code=400, detail="현재 로그인한 계정은 삭제할 수 없습니다")
    with get_db() as conn:
        row = conn.execute("SELECT * FROM stores WHERE id = ?", (store_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="매장을 찾을 수 없습니다")
        for table in DATA_TABLES_FOR_STORE:
            count = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE store_id = ?", (store_id,)).fetchone()[0]
            if count > 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"이 매장에 저장된 데이터가 있어 삭제할 수 없습니다 ({table} {count}건). 데이터를 정리한 뒤 다시 시도해 주세요.",
                )
        if row["is_admin"]:
            other_admins = conn.execute(
                "SELECT COUNT(*) FROM stores WHERE is_admin = 1 AND id != ?", (store_id,)
            ).fetchone()[0]
            if other_admins == 0:
                raise HTTPException(status_code=400, detail="마지막 남은 관리자 계정은 삭제할 수 없습니다")
        conn.execute("DELETE FROM stores WHERE id = ?", (store_id,))
        conn.commit()
        return {"ok": True}


@app.get("/api/admin/groups")
def admin_list_groups(admin: dict = Depends(require_admin)):
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM store_groups ORDER BY id").fetchall()
    return [dict(r) for r in rows]


@app.post("/api/admin/groups")
def admin_create_group(body: StoreGroupCreateIn, admin: dict = Depends(require_admin)):
    with get_db() as conn:
        cur = conn.execute("INSERT INTO store_groups (name) VALUES (?)", (body.name,))
        conn.commit()
        return {"id": cur.lastrowid}


@app.put("/api/admin/groups/{group_id}")
def admin_rename_group(group_id: int, body: GroupRenameIn, admin: dict = Depends(require_admin)):
    with get_db() as conn:
        cur = conn.execute("UPDATE store_groups SET name = ? WHERE id = ?", (body.name, group_id))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="그룹을 찾을 수 없습니다")
        return {"ok": True}


@app.delete("/api/admin/groups/{group_id}")
def admin_delete_group(group_id: int, admin: dict = Depends(require_admin)):
    with get_db() as conn:
        store_count = conn.execute("SELECT COUNT(*) FROM stores WHERE group_id = ?", (group_id,)).fetchone()[0]
        if store_count > 0:
            raise HTTPException(status_code=400, detail="이 그룹에 속한 매장이 있어 삭제할 수 없습니다. 매장을 먼저 다른 그룹으로 옮겨 주세요.")
        cur = conn.execute("DELETE FROM store_groups WHERE id = ?", (group_id,))
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="그룹을 찾을 수 없습니다")
        return {"ok": True}


# ---------- 고객 API ----------

@app.post("/api/customers")
def create_customer(customer: CustomerIn, store: dict = Depends(get_current_store)):
    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO customers
               (name, gender, phone, phone2, birth_date, dominant_eye, occupation, email, address, note, store_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (customer.name, customer.gender, customer.phone, customer.phone2, customer.birth_date,
             customer.dominant_eye, customer.occupation, customer.email,
             customer.address, customer.note, store["id"]),
        )
        conn.commit()
        return {"id": cur.lastrowid}


@app.get("/api/customers")
def search_customers(q: Optional[str] = None, phone_exact: Optional[str] = None,
                      exclude_id: Optional[int] = None, limit: int = 1000,
                      store: dict = Depends(get_current_store)):
    limit = min(max(limit, 1), 1000)  # 한 번에 최대 1000명까지
    group_ids = get_group_store_ids(store)
    ph = _in_placeholders(group_ids)
    with get_db() as conn:
        if phone_exact:
            # 가족목록: 휴대번호(대표)가 정확히 같은 다른 고객 찾기
            rows = conn.execute(
                f"""SELECT * FROM customers WHERE phone = ? AND id != ? AND store_id IN ({ph})
                   ORDER BY id DESC LIMIT ?""",
                (phone_exact, exclude_id or -1, *group_ids, limit),
            ).fetchall()
        elif q:
            # 이름/전화번호 어디에 포함되어도 찾아지도록 부분일치, 결과는 이름 가나다순 정렬
            rows = conn.execute(
                f"""SELECT * FROM customers
                   WHERE (name LIKE ? OR phone LIKE ?) AND store_id IN ({ph})
                   ORDER BY name ASC LIMIT ?""",
                (f"%{q}%", f"%{q}%", *group_ids, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                f"SELECT * FROM customers WHERE store_id IN ({ph}) ORDER BY id DESC LIMIT ?",
                (*group_ids, limit),
            ).fetchall()
        return [dict(r) for r in rows]


@app.get("/api/customers/{customer_id}")
def get_customer(customer_id: int, store: dict = Depends(get_current_store)):
    group_ids = get_group_store_ids(store)
    ph = _in_placeholders(group_ids)
    with get_db() as conn:
        row = conn.execute(
            f"SELECT * FROM customers WHERE id = ? AND store_id IN ({ph})", (customer_id, *group_ids)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="고객을 찾을 수 없습니다")
        return dict(row)


@app.put("/api/customers/{customer_id}")
def update_customer(customer_id: int, customer: CustomerIn, store: dict = Depends(get_current_store)):
    with get_db() as conn:
        owner = conn.execute("SELECT store_id FROM customers WHERE id = ?", (customer_id,)).fetchone()
        if not owner:
            raise HTTPException(status_code=404, detail="고객을 찾을 수 없습니다")
        if owner["store_id"] != store["id"]:
            raise HTTPException(status_code=403, detail="다른 매장의 고객 정보는 수정할 수 없습니다")
        cur = conn.execute(
            """UPDATE customers SET name=?, gender=?, phone=?, phone2=?, birth_date=?,
               dominant_eye=?, occupation=?, email=?, address=?, note=? WHERE id=?""",
            (customer.name, customer.gender, customer.phone, customer.phone2, customer.birth_date,
             customer.dominant_eye, customer.occupation, customer.email,
             customer.address, customer.note, customer_id),
        )
        conn.commit()
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="고객을 찾을 수 없습니다")
        return {"ok": True}


@app.delete("/api/customers/{customer_id}")
def delete_customer(customer_id: int, store: dict = Depends(get_current_store)):
    with get_db() as conn:
        owner = conn.execute("SELECT id, store_id FROM customers WHERE id = ?", (customer_id,)).fetchone()
        if not owner:
            raise HTTPException(status_code=404, detail="고객을 찾을 수 없습니다")
        if owner["store_id"] != store["id"]:
            raise HTTPException(status_code=403, detail="다른 매장의 고객 정보는 삭제할 수 없습니다")

        exam_ids = [r["id"] for r in conn.execute(
            "SELECT id FROM exams WHERE customer_id = ?", (customer_id,)
        ).fetchall()]
        for exam_id in exam_ids:
            conn.execute("DELETE FROM sale_items WHERE exam_id = ?", (exam_id,))
        conn.execute("DELETE FROM exams WHERE customer_id = ?", (customer_id,))
        conn.execute("DELETE FROM visits WHERE customer_id = ?", (customer_id,))
        conn.execute("DELETE FROM customers WHERE id = ?", (customer_id,))
        conn.commit()
        return {"ok": True}


# ---------- 검안정보 + 매출/결제 API (한 번에 저장) ----------

@app.post("/api/customers/{customer_id}/exams")
def create_exam(customer_id: int, exam: ExamIn, store: dict = Depends(get_current_store)):
    validate_exam_ranges(exam)
    exam_date = exam.exam_date or date.today().isoformat()
    group_ids = get_group_store_ids(store)
    ph = _in_placeholders(group_ids)
    with get_db() as conn:
        # 고객은 같은 그룹이면 공유되므로, 그룹 안에만 있으면 새 검안/매출을 등록할 수 있음
        # (다만 이 새 기록 자체는 지금 로그인한 매장 소유로 저장됨)
        owner = conn.execute(
            f"SELECT id FROM customers WHERE id = ? AND store_id IN ({ph})", (customer_id, *group_ids)
        ).fetchone()
        if not owner:
            raise HTTPException(status_code=404, detail="고객을 찾을 수 없습니다")

        data = exam.dict(exclude={"sale_items"})
        cols = ["customer_id", "exam_date", "created_at", "store_id"] + EXAM_FIELDS
        placeholders = ", ".join(["?"] * len(cols))
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        values = [customer_id, exam_date, created_at, store["id"]] + [data[f] for f in EXAM_FIELDS]

        cur = conn.execute(
            f"INSERT INTO exams ({', '.join(cols)}) VALUES ({placeholders})",
            values,
        )
        exam_id = cur.lastrowid
        conn.commit()

        # 매출 라인 아이템 저장 (빈 상품명 행은 건너뜀)
        for item in exam.sale_items:
            if not item.product_name:
                continue
            conn.execute(
                """INSERT INTO sale_items
                   (exam_id, category, brand, product_name, color, quantity, unit_price, store_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (exam_id, item.category, item.brand, item.product_name,
                 item.color, item.quantity, item.unit_price, store["id"]),
            )
        conn.commit()

        conn.execute(
            "INSERT INTO visits (customer_id, visit_date, note, store_id) VALUES (?, ?, ?, ?)",
            (customer_id, exam_date, "검안/매출", store["id"]),
        )
        conn.commit()

        return {"id": exam_id}


@app.get("/api/customers/{customer_id}/exams")
def list_exams(customer_id: int, store: dict = Depends(get_current_store)):
    group_ids = get_group_store_ids(store)
    ph = _in_placeholders(group_ids)
    with get_db() as conn:
        rows = conn.execute(
            f"""SELECT * FROM exams WHERE customer_id = ? AND store_id IN ({ph})
               ORDER BY exam_date DESC, id DESC""",
            (customer_id, *group_ids),
        ).fetchall()
        result = []
        for r in rows:
            record = dict(r)
            items = conn.execute(
                "SELECT * FROM sale_items WHERE exam_id = ?", (record["id"],)
            ).fetchall()
            record["sale_items"] = [dict(i) for i in items]
            result.append(record)
        return result


@app.put("/api/customers/{customer_id}/exams/{exam_id}")
def update_exam(customer_id: int, exam_id: int, exam: ExamIn, store: dict = Depends(get_current_store)):
    validate_exam_ranges(exam)
    exam_date = exam.exam_date or date.today().isoformat()
    with get_db() as conn:
        owner = conn.execute(
            "SELECT id, store_id FROM exams WHERE id = ? AND customer_id = ?",
            (exam_id, customer_id),
        ).fetchone()
        if not owner:
            raise HTTPException(status_code=404, detail="검안 기록을 찾을 수 없습니다")
        if owner["store_id"] != store["id"]:
            raise HTTPException(status_code=403, detail="다른 매장의 기록은 수정할 수 없습니다")

        data = exam.dict(exclude={"sale_items"})
        set_clause = ", ".join([f"{f}=?" for f in EXAM_FIELDS])
        values = [data[f] for f in EXAM_FIELDS] + [exam_date, exam_id]

        conn.execute(
            f"UPDATE exams SET {set_clause}, exam_date=? WHERE id=?",
            values,
        )
        conn.commit()

        # 기존 매출 항목을 지우고 새로 입력된 내용으로 교체
        conn.execute("DELETE FROM sale_items WHERE exam_id = ?", (exam_id,))
        for item in exam.sale_items:
            if not item.product_name:
                continue
            conn.execute(
                """INSERT INTO sale_items
                   (exam_id, category, brand, product_name, color, quantity, unit_price, store_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (exam_id, item.category, item.brand, item.product_name,
                 item.color, item.quantity, item.unit_price, store["id"]),
            )
        conn.commit()
        return {"id": exam_id}


@app.delete("/api/customers/{customer_id}/exams/{exam_id}")
def delete_exam(customer_id: int, exam_id: int, store: dict = Depends(get_current_store)):
    with get_db() as conn:
        owner = conn.execute(
            "SELECT * FROM exams WHERE id = ? AND customer_id = ?",
            (exam_id, customer_id),
        ).fetchone()
        if not owner:
            raise HTTPException(status_code=404, detail="검안 기록을 찾을 수 없습니다")
        if owner["store_id"] != store["id"]:
            raise HTTPException(status_code=403, detail="다른 매장의 기록은 삭제할 수 없습니다")

        conn.execute("DELETE FROM sale_items WHERE exam_id = ?", (exam_id,))
        conn.execute("DELETE FROM exams WHERE id = ?", (exam_id,))
        # 방문내역(visits)은 exam과 1:1로 연결된 id가 없어 같은 날짜의 방문 기록을 함께 지움
        conn.execute(
            "DELETE FROM visits WHERE customer_id = ? AND visit_date = ? AND store_id = ?",
            (customer_id, owner["exam_date"], store["id"]),
        )
        conn.commit()
        return {"ok": True}


@app.get("/api/customers/{customer_id}/visits")
def list_visits(customer_id: int, store: dict = Depends(get_current_store)):
    group_ids = get_group_store_ids(store)
    ph = _in_placeholders(group_ids)
    with get_db() as conn:
        rows = conn.execute(
            f"""SELECT * FROM visits WHERE customer_id = ? AND store_id IN ({ph})
               ORDER BY visit_date DESC, id DESC""",
            (customer_id, *group_ids),
        ).fetchall()
        return [dict(r) for r in rows]


# ---------- 일반판매 API (고객/비회원 어디에도 연결하지 않는 독립된 판매 기록) ----------
# 매출현황에서만 조회·수정할 수 있고, 고객 목록/방문내역/미수금현황 등 고객 관련 화면에는 전혀 나타나지 않음

@app.post("/api/general-sales")
def create_general_sale(sale: ExamIn, store: dict = Depends(get_current_store)):
    validate_exam_ranges(sale)
    sale_date = sale.exam_date or date.today().isoformat()
    with get_db() as conn:
        data = sale.dict(exclude={"sale_items"})
        cols = ["sale_date", "created_at", "store_id"] + GENERAL_SALE_FIELDS
        placeholders = ", ".join(["?"] * len(cols))
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        values = [sale_date, created_at, store["id"]] + [data[f] for f in GENERAL_SALE_FIELDS]

        cur = conn.execute(
            f"INSERT INTO general_sales ({', '.join(cols)}) VALUES ({placeholders})", values,
        )
        gs_id = cur.lastrowid
        conn.commit()

        for item in sale.sale_items:
            if not item.product_name:
                continue
            conn.execute(
                """INSERT INTO general_sale_items
                   (general_sale_id, category, brand, product_name, color, quantity, unit_price, store_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (gs_id, item.category, item.brand, item.product_name, item.color, item.quantity, item.unit_price,
                 store["id"]),
            )
        conn.commit()
        return {"id": gs_id}


@app.get("/api/general-sales")
def list_general_sales(store: dict = Depends(get_current_store)):
    group_ids = get_group_store_ids(store)
    ph = _in_placeholders(group_ids)
    with get_db() as conn:
        rows = conn.execute(f"SELECT * FROM general_sales WHERE store_id IN ({ph}) ORDER BY id DESC", group_ids).fetchall()
        result = []
        for r in rows:
            record = dict(r)
            items = conn.execute(
                "SELECT * FROM general_sale_items WHERE general_sale_id = ?", (record["id"],)
            ).fetchall()
            record["sale_items"] = [dict(i) for i in items]
            result.append(record)
        return result


@app.put("/api/general-sales/{gs_id}")
def update_general_sale(gs_id: int, sale: ExamIn, store: dict = Depends(get_current_store)):
    validate_exam_ranges(sale)
    sale_date = sale.exam_date or date.today().isoformat()
    with get_db() as conn:
        owner = conn.execute("SELECT id, store_id FROM general_sales WHERE id = ?", (gs_id,)).fetchone()
        if not owner:
            raise HTTPException(status_code=404, detail="일반판매 기록을 찾을 수 없습니다")
        if owner["store_id"] != store["id"]:
            raise HTTPException(status_code=403, detail="다른 매장의 기록은 수정할 수 없습니다")

        data = sale.dict(exclude={"sale_items"})
        set_clause = ", ".join([f"{f}=?" for f in GENERAL_SALE_FIELDS])
        values = [data[f] for f in GENERAL_SALE_FIELDS] + [sale_date, gs_id]
        conn.execute(f"UPDATE general_sales SET {set_clause}, sale_date=? WHERE id=?", values)
        conn.commit()

        conn.execute("DELETE FROM general_sale_items WHERE general_sale_id = ?", (gs_id,))
        for item in sale.sale_items:
            if not item.product_name:
                continue
            conn.execute(
                """INSERT INTO general_sale_items
                   (general_sale_id, category, brand, product_name, color, quantity, unit_price, store_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (gs_id, item.category, item.brand, item.product_name, item.color, item.quantity, item.unit_price,
                 store["id"]),
            )
        conn.commit()
        return {"id": gs_id}


@app.get("/api/general-sales/{gs_id}/returns")
def list_general_sale_returns(gs_id: int, store: dict = Depends(get_current_store)):
    group_ids = get_group_store_ids(store)
    ph = _in_placeholders(group_ids)
    with get_db() as conn:
        rows = conn.execute(
            f"""SELECT r.* FROM general_sale_returns r JOIN general_sales g ON g.id = r.general_sale_id
               WHERE r.general_sale_id = ? AND g.store_id IN ({ph}) ORDER BY r.id DESC""",
            (gs_id, *group_ids),
        ).fetchall()
        return [dict(r) for r in rows]


@app.post("/api/general-sales/{gs_id}/returns")
def create_general_sale_return(gs_id: int, ret: ReturnIn, store: dict = Depends(get_current_store)):
    with get_db() as conn:
        owner = conn.execute("SELECT id, store_id FROM general_sales WHERE id = ?", (gs_id,)).fetchone()
        if not owner:
            raise HTTPException(status_code=404, detail="일반판매 기록을 찾을 수 없습니다")
        if owner["store_id"] != store["id"]:
            raise HTTPException(status_code=403, detail="다른 매장의 기록은 반품 처리할 수 없습니다")

        return_date = ret.return_date or date.today().isoformat()
        items_json = json.dumps([i.dict() for i in ret.items], ensure_ascii=False) if ret.items else None
        cur = conn.execute(
            """INSERT INTO general_sale_returns
               (general_sale_id, return_date, product_name, amount, reason,
                items_detail, cash_refund, card_refund, giftcard_refund, discount_cancel, staff, store_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (gs_id, return_date, ret.product_name, ret.amount, ret.reason, items_json,
             ret.cash_refund or 0, ret.card_refund or 0, ret.giftcard_refund or 0, ret.discount_cancel or 0,
             ret.staff, store["id"]),
        )
        conn.commit()
        return {"id": cur.lastrowid}


@app.put("/api/general-sales/{gs_id}/returns/{return_id}")
def update_general_sale_return(gs_id: int, return_id: int, ret: ReturnIn, store: dict = Depends(get_current_store)):
    with get_db() as conn:
        row = conn.execute(
            "SELECT id, store_id FROM general_sale_returns WHERE id = ? AND general_sale_id = ?", (return_id, gs_id)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="반품 기록을 찾을 수 없습니다")
        if row["store_id"] != store["id"]:
            raise HTTPException(status_code=403, detail="다른 매장의 기록은 수정할 수 없습니다")

        return_date = ret.return_date or date.today().isoformat()
        items_json = json.dumps([i.dict() for i in ret.items], ensure_ascii=False) if ret.items else None
        conn.execute(
            """UPDATE general_sale_returns SET return_date=?, product_name=?, amount=?, reason=?,
               items_detail=?, cash_refund=?, card_refund=?, giftcard_refund=?, discount_cancel=?, staff=?
               WHERE id=?""",
            (return_date, ret.product_name, ret.amount, ret.reason, items_json,
             ret.cash_refund or 0, ret.card_refund or 0, ret.giftcard_refund or 0, ret.discount_cancel or 0,
             ret.staff, return_id),
        )
        conn.commit()
        return {"ok": True}


@app.delete("/api/general-sales/{gs_id}/returns/{return_id}")
def delete_general_sale_return(gs_id: int, return_id: int, store: dict = Depends(get_current_store)):
    with get_db() as conn:
        row = conn.execute(
            "SELECT store_id FROM general_sale_returns WHERE id = ? AND general_sale_id = ?", (return_id, gs_id)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="반품 기록을 찾을 수 없습니다")
        if row["store_id"] != store["id"]:
            raise HTTPException(status_code=403, detail="다른 매장의 기록은 삭제할 수 없습니다")
        conn.execute("DELETE FROM general_sale_returns WHERE id = ?", (return_id,))
        conn.commit()
        return {"ok": True}


# ---------- A/S전표 API ----------
# A/S 접수는 고객/비회원 어디에도 연결하지 않는 독립된 기록(as_records 테이블)로 저장됨

@app.post("/api/as-records")
def create_as_record(rec: ASRecordIn, store: dict = Depends(get_current_store)):
    receive_date = rec.receive_date or date.today().isoformat()
    with get_db() as conn:
        data = rec.dict()
        cols = ["receive_date", "created_at", "store_id"] + AS_RECORD_FIELDS
        placeholders = ", ".join(["?"] * len(cols))
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        values = [receive_date, created_at, store["id"]] + [data[f] for f in AS_RECORD_FIELDS]
        cur = conn.execute(f"INSERT INTO as_records ({', '.join(cols)}) VALUES ({placeholders})", values)
        conn.commit()
        return {"id": cur.lastrowid}


@app.get("/api/as-records")
def list_as_records(search_type: Optional[str] = None, keyword: Optional[str] = None,
                     date_type: Optional[str] = None, date_from: Optional[str] = None,
                     date_to: Optional[str] = None, store: dict = Depends(get_current_store)):
    group_ids = get_group_store_ids(store)
    ph = _in_placeholders(group_ids)
    query = f"SELECT * FROM as_records WHERE store_id IN ({ph})"
    params: list = list(group_ids)

    if keyword:
        like = f"%{keyword}%"
        if search_type == "고객번호":
            query += " AND id = ?"
            params.append(keyword)
        elif search_type == "전화번호":
            query += " AND (phone1 || phone2 LIKE ? OR mobile1 || mobile2 LIKE ?)"
            params += [like, like]
        else:
            query += " AND customer_name LIKE ?"
            params.append(like)

    date_col = "finish_date" if date_type == "완성일자" else "receive_date"
    if date_from:
        query += f" AND {date_col} >= ?"
        params.append(date_from)
    if date_to:
        query += f" AND {date_col} <= ?"
        params.append(date_to)

    query += " ORDER BY id DESC"
    with get_db() as conn:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


@app.get("/api/as-records/{as_id}")
def get_as_record(as_id: int, store: dict = Depends(get_current_store)):
    group_ids = get_group_store_ids(store)
    ph = _in_placeholders(group_ids)
    with get_db() as conn:
        row = conn.execute(
            f"SELECT * FROM as_records WHERE id = ? AND store_id IN ({ph})", (as_id, *group_ids)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="A/S 기록을 찾을 수 없습니다")
        return dict(row)


@app.put("/api/as-records/{as_id}")
def update_as_record(as_id: int, rec: ASRecordIn, store: dict = Depends(get_current_store)):
    receive_date = rec.receive_date or date.today().isoformat()
    with get_db() as conn:
        owner = conn.execute("SELECT store_id FROM as_records WHERE id = ?", (as_id,)).fetchone()
        if not owner:
            raise HTTPException(status_code=404, detail="A/S 기록을 찾을 수 없습니다")
        if owner["store_id"] != store["id"]:
            raise HTTPException(status_code=403, detail="다른 매장의 기록은 수정할 수 없습니다")

        data = rec.dict()
        set_clause = ", ".join([f"{f}=?" for f in AS_RECORD_FIELDS])
        values = [data[f] for f in AS_RECORD_FIELDS] + [receive_date, as_id]
        conn.execute(f"UPDATE as_records SET {set_clause}, receive_date=? WHERE id=?", values)
        conn.commit()
        return {"id": as_id}


@app.delete("/api/as-records/{as_id}")
def delete_as_record(as_id: int, store: dict = Depends(get_current_store)):
    with get_db() as conn:
        owner = conn.execute("SELECT store_id FROM as_records WHERE id = ?", (as_id,)).fetchone()
        if not owner:
            raise HTTPException(status_code=404, detail="A/S 기록을 찾을 수 없습니다")
        if owner["store_id"] != store["id"]:
            raise HTTPException(status_code=403, detail="다른 매장의 기록은 삭제할 수 없습니다")
        conn.execute("DELETE FROM as_records WHERE id = ?", (as_id,))
        conn.commit()
        return {"ok": True}


# ---------- 반품 / 미수 API ----------

@app.get("/api/customers/{customer_id}/unpaid")
def list_unpaid(customer_id: int, store: dict = Depends(get_current_store)):
    """미수(아직 못 받은 돈)가 남아있는 방문 기록만 골라서 보여줌"""
    group_ids = get_group_store_ids(store)
    ph = _in_placeholders(group_ids)
    with get_db() as conn:
        rows = conn.execute(
            f"""SELECT id, exam_date, sale_total, unpaid_amount FROM exams
               WHERE customer_id = ? AND unpaid_amount IS NOT NULL AND unpaid_amount > 0 AND store_id IN ({ph})
               ORDER BY exam_date DESC, id DESC""",
            (customer_id, *group_ids),
        ).fetchall()
        return [dict(r) for r in rows]


@app.post("/api/customers/{customer_id}/exams/{exam_id}/settle")
def settle_unpaid(customer_id: int, exam_id: int, body: SettleIn, store: dict = Depends(get_current_store)):
    """미수금을 결제정보(현금/카드/상품권/할인)로 정산. 한 번에 다 못 받아도 부분 정산이 가능하도록
    입력한 금액만큼만 미수금에서 차감하고, 언제/얼마를/무엇으로 받았는지 기록을 남김"""
    with get_db() as conn:
        owner = conn.execute(
            "SELECT * FROM exams WHERE id = ? AND customer_id = ?", (exam_id, customer_id),
        ).fetchone()
        if not owner:
            raise HTTPException(status_code=404, detail="검안 기록을 찾을 수 없습니다")
        if owner["store_id"] != store["id"]:
            raise HTTPException(status_code=403, detail="다른 매장의 기록은 정산할 수 없습니다")

        cash = body.cash_amount or 0
        card = body.card_amount or 0
        gift = body.giftcard_amount or 0
        disc = body.discount or 0
        total_paid = cash + card + gift + disc
        current_unpaid = owner["unpaid_amount"] or 0
        remaining_unpaid = max(current_unpaid - total_paid, 0)

        settle_date = body.settle_date or date.today().isoformat()
        cur = conn.execute(
            """INSERT INTO settlements
               (customer_id, exam_id, settle_date, cash_amount, card_amount, giftcard_amount, discount, amount,
                card_type, giftcard_type, point_option, staff, seller, cash_receipt, memo, store_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (customer_id, exam_id, settle_date, cash, card, gift, disc, total_paid,
             body.card_type, body.giftcard_type, body.point_option, body.staff, body.seller,
             body.cash_receipt, body.memo, store["id"]),
        )
        conn.execute("UPDATE exams SET unpaid_amount = ? WHERE id = ?", (remaining_unpaid, exam_id))
        conn.commit()
        return {"ok": True, "remaining_unpaid": remaining_unpaid, "id": cur.lastrowid}


@app.put("/api/customers/{customer_id}/settlements/{settlement_id}")
def update_settlement(customer_id: int, settlement_id: int, body: SettleIn, store: dict = Depends(get_current_store)):
    """이미 저장된 납입 내역을 수정. 납입액이 바뀐 만큼 해당 방문의 미수금을 다시 계산함"""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM settlements WHERE id = ? AND customer_id = ?", (settlement_id, customer_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="납입 기록을 찾을 수 없습니다")
        if row["store_id"] != store["id"]:
            raise HTTPException(status_code=403, detail="다른 매장의 기록은 수정할 수 없습니다")

        cash = body.cash_amount or 0
        card = body.card_amount or 0
        gift = body.giftcard_amount or 0
        disc = body.discount or 0
        new_total = cash + card + gift + disc
        old_total = row["amount"] or 0

        if row["exam_id"]:
            exam = conn.execute("SELECT unpaid_amount FROM exams WHERE id = ?", (row["exam_id"],)).fetchone()
            if exam:
                adjusted = max((exam["unpaid_amount"] or 0) + old_total - new_total, 0)
                conn.execute("UPDATE exams SET unpaid_amount = ? WHERE id = ?", (adjusted, row["exam_id"]))

        settle_date = body.settle_date or row["settle_date"]
        conn.execute(
            """UPDATE settlements SET settle_date=?, cash_amount=?, card_amount=?, giftcard_amount=?, discount=?,
               amount=?, card_type=?, giftcard_type=?, point_option=?, staff=?, seller=?, cash_receipt=?, memo=?
               WHERE id=?""",
            (settle_date, cash, card, gift, disc, new_total,
             body.card_type, body.giftcard_type, body.point_option, body.staff, body.seller,
             body.cash_receipt, body.memo, settlement_id),
        )
        conn.commit()
        return {"ok": True}


@app.delete("/api/customers/{customer_id}/settlements/{settlement_id}")
def delete_settlement(customer_id: int, settlement_id: int, store: dict = Depends(get_current_store)):
    """납입 내역을 삭제하고, 그만큼 미수금을 다시 복원함"""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM settlements WHERE id = ? AND customer_id = ?", (settlement_id, customer_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="납입 기록을 찾을 수 없습니다")
        if row["store_id"] != store["id"]:
            raise HTTPException(status_code=403, detail="다른 매장의 기록은 삭제할 수 없습니다")
        if row["exam_id"]:
            exam = conn.execute("SELECT unpaid_amount FROM exams WHERE id = ?", (row["exam_id"],)).fetchone()
            if exam:
                restored = (exam["unpaid_amount"] or 0) + (row["amount"] or 0)
                conn.execute("UPDATE exams SET unpaid_amount = ? WHERE id = ?", (restored, row["exam_id"]))
        conn.execute("DELETE FROM settlements WHERE id = ?", (settlement_id,))
        conn.commit()
        return {"ok": True}


@app.get("/api/customers/{customer_id}/settlements")
def list_settlements(customer_id: int, store: dict = Depends(get_current_store)):
    group_ids = get_group_store_ids(store)
    ph = _in_placeholders(group_ids)
    with get_db() as conn:
        rows = conn.execute(
            f"""SELECT * FROM settlements WHERE customer_id = ? AND store_id IN ({ph})
               ORDER BY settle_date DESC, id DESC""",
            (customer_id, *group_ids),
        ).fetchall()
        return [dict(r) for r in rows]


@app.get("/api/customers/{customer_id}/returns")
def list_returns(customer_id: int, store: dict = Depends(get_current_store)):
    group_ids = get_group_store_ids(store)
    ph = _in_placeholders(group_ids)
    with get_db() as conn:
        rows = conn.execute(
            f"""SELECT * FROM returns WHERE customer_id = ? AND store_id IN ({ph})
               ORDER BY return_date DESC, id DESC""",
            (customer_id, *group_ids),
        ).fetchall()
        return [dict(r) for r in rows]


@app.post("/api/customers/{customer_id}/returns")
def create_return(customer_id: int, ret: ReturnIn, store: dict = Depends(get_current_store)):
    group_ids = get_group_store_ids(store)
    ph = _in_placeholders(group_ids)
    with get_db() as conn:
        if not conn.execute(
            f"SELECT id FROM customers WHERE id = ? AND store_id IN ({ph})", (customer_id, *group_ids)
        ).fetchone():
            raise HTTPException(status_code=404, detail="고객을 찾을 수 없습니다")
        if ret.exam_id:
            exam = conn.execute("SELECT store_id FROM exams WHERE id = ?", (ret.exam_id,)).fetchone()
            if not exam or exam["store_id"] != store["id"]:
                raise HTTPException(status_code=403, detail="다른 매장의 방문 기록은 반품 처리할 수 없습니다")

        return_date = ret.return_date or date.today().isoformat()
        items_json = json.dumps([i.dict() for i in ret.items], ensure_ascii=False) if ret.items else None
        unpaid_offset = ret.unpaid_offset or 0
        cur = conn.execute(
            """INSERT INTO returns
               (customer_id, exam_id, return_date, product_name, amount, reason, refund_method,
                items_detail, cash_refund, card_refund, giftcard_refund, discount_cancel, unpaid_offset, staff,
                store_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (customer_id, ret.exam_id, return_date, ret.product_name, ret.amount, ret.reason, ret.refund_method,
             items_json, ret.cash_refund or 0, ret.card_refund or 0, ret.giftcard_refund or 0,
             ret.discount_cancel or 0, unpaid_offset, ret.staff, store["id"]),
        )
        if ret.exam_id and unpaid_offset > 0:
            exam = conn.execute("SELECT unpaid_amount FROM exams WHERE id = ?", (ret.exam_id,)).fetchone()
            if exam:
                new_unpaid = max((exam["unpaid_amount"] or 0) - unpaid_offset, 0)
                conn.execute("UPDATE exams SET unpaid_amount = ? WHERE id = ?", (new_unpaid, ret.exam_id))
        conn.commit()
        return {"id": cur.lastrowid}


@app.put("/api/customers/{customer_id}/returns/{return_id}")
def update_return(customer_id: int, return_id: int, ret: ReturnIn, store: dict = Depends(get_current_store)):
    """이미 저장된 반품 내역을 수정. 미수공제 금액이 바뀐 만큼 해당 방문의 미수금을 다시 계산함"""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM returns WHERE id = ? AND customer_id = ?", (return_id, customer_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="반품 기록을 찾을 수 없습니다")
        if row["store_id"] != store["id"]:
            raise HTTPException(status_code=403, detail="다른 매장의 기록은 수정할 수 없습니다")

        old_offset = row["unpaid_offset"] or 0
        new_offset = ret.unpaid_offset or 0
        exam_id = row["exam_id"]
        if exam_id:
            exam = conn.execute("SELECT unpaid_amount FROM exams WHERE id = ?", (exam_id,)).fetchone()
            if exam:
                restored = (exam["unpaid_amount"] or 0) + old_offset
                new_unpaid = max(restored - new_offset, 0)
                conn.execute("UPDATE exams SET unpaid_amount = ? WHERE id = ?", (new_unpaid, exam_id))

        return_date = ret.return_date or row["return_date"]
        items_json = json.dumps([i.dict() for i in ret.items], ensure_ascii=False) if ret.items else row["items_detail"]
        conn.execute(
            """UPDATE returns SET return_date=?, product_name=?, amount=?, reason=?,
               items_detail=?, cash_refund=?, card_refund=?, giftcard_refund=?, discount_cancel=?,
               unpaid_offset=?, staff=? WHERE id=?""",
            (return_date, ret.product_name, ret.amount, ret.reason,
             items_json, ret.cash_refund or 0, ret.card_refund or 0, ret.giftcard_refund or 0,
             ret.discount_cancel or 0, new_offset, ret.staff, return_id),
        )
        conn.commit()
        return {"ok": True}


@app.delete("/api/customers/{customer_id}/returns/{return_id}")
def delete_return(customer_id: int, return_id: int, store: dict = Depends(get_current_store)):
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM returns WHERE id = ? AND customer_id = ?", (return_id, customer_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="반품 기록을 찾을 수 없습니다")
        if row["store_id"] != store["id"]:
            raise HTTPException(status_code=403, detail="다른 매장의 기록은 삭제할 수 없습니다")
        if row["exam_id"] and (row["unpaid_offset"] or 0) > 0:
            exam = conn.execute("SELECT unpaid_amount FROM exams WHERE id = ?", (row["exam_id"],)).fetchone()
            if exam:
                restored = (exam["unpaid_amount"] or 0) + row["unpaid_offset"]
                conn.execute("UPDATE exams SET unpaid_amount = ? WHERE id = ?", (restored, row["exam_id"]))
        conn.execute("DELETE FROM returns WHERE id = ?", (return_id,))
        conn.commit()
        return {"ok": True}


# ---------- 매출현황 / 미수금현황 (전체 고객 통합 조회) ----------

@app.get("/api/sales-status")
def sales_status(store: dict = Depends(get_current_store)):
    """이 매장(및 같은 그룹 매장)의 판매(검안매출/일반판매)·반품·미수금납입 내역을 하나의 표로 합쳐서 보여줌"""
    group_ids = get_group_store_ids(store)
    ph = _in_placeholders(group_ids)
    with get_db() as conn:
        rows = []

        exam_rows = conn.execute(f"""
            SELECT e.*, c.name AS customer_name, c.birth_date, c.gender,
                   (SELECT COUNT(*) FROM exams e2 WHERE e2.customer_id = e.customer_id) AS visit_count
            FROM exams e JOIN customers c ON c.id = e.customer_id
            WHERE e.store_id IN ({ph})
            ORDER BY e.id DESC
        """, group_ids).fetchall()
        for e in exam_rows:
            sale_total = e["sale_total"] or 0
            discount = e["discount"] or 0
            cash = e["cash_amount"] or 0
            card = e["card_amount"] or 0
            gift = e["giftcard_amount"] or 0
            rows.append({
                "id": e["id"], "kind": "exam", "exam_id": e["id"],
                "customer_id": e["customer_id"], "customer_name": e["customer_name"],
                "sale_date": e["created_at"] or (f"{e['exam_date']} 00:00" if e["exam_date"] else None),
                "sale_type": "판매",
                "gross_amount": sale_total, "net_amount": sale_total - discount,
                "paid_amount": cash + card + gift,
                "cash_amount": cash, "cash_receipt": e["cash_receipt_type"],
                "card_amount": card, "card_type": e["card_type"],
                "giftcard_amount": gift, "giftcard_type": e["giftcard_type"],
                "discount": discount, "point_amount": 0,
                "unpaid_amount": e["unpaid_amount"] or 0, "unpaid_paid": 0,
                "seller": e["staff_seller"], "manager": e["staff_manager"],
                "birth_date": e["birth_date"], "gender": e["gender"], "visit_count": e["visit_count"],
            })

        general_rows = conn.execute(
            f"SELECT * FROM general_sales WHERE store_id IN ({ph}) ORDER BY id DESC", group_ids
        ).fetchall()
        for g in general_rows:
            sale_total = g["sale_total"] or 0
            discount = g["discount"] or 0
            cash = g["cash_amount"] or 0
            card = g["card_amount"] or 0
            gift = g["giftcard_amount"] or 0
            rows.append({
                "id": g["id"], "kind": "general_sale", "exam_id": None,
                "customer_id": None, "customer_name": "비회원",
                "sale_date": g["created_at"] or (f"{g['sale_date']} 00:00" if g["sale_date"] else None),
                "sale_type": "일반",
                "gross_amount": sale_total, "net_amount": sale_total - discount,
                "paid_amount": cash + card + gift,
                "cash_amount": cash, "cash_receipt": g["cash_receipt_type"],
                "card_amount": card, "card_type": g["card_type"],
                "giftcard_amount": gift, "giftcard_type": g["giftcard_type"],
                "discount": discount, "point_amount": 0,
                "unpaid_amount": g["unpaid_amount"] or 0, "unpaid_paid": 0,
                "seller": g["staff_seller"], "manager": g["staff_manager"],
                "birth_date": None, "gender": None, "visit_count": None,
            })

        general_return_rows = conn.execute(
            f"SELECT * FROM general_sale_returns WHERE store_id IN ({ph}) ORDER BY id DESC", group_ids
        ).fetchall()
        for r in general_return_rows:
            amount = r["amount"] or 0
            cash = r["cash_refund"] or 0
            card = r["card_refund"] or 0
            gift = r["giftcard_refund"] or 0
            disc = r["discount_cancel"] or 0
            rows.append({
                "id": r["id"], "kind": "general_return", "exam_id": None,
                "general_sale_id": r["general_sale_id"],
                "customer_id": None, "customer_name": "비회원",
                "sale_date": r["created_at"] or (f"{r['return_date']} 00:00" if r["return_date"] else None),
                "sale_type": "반품",
                "gross_amount": -amount, "net_amount": -amount + disc,
                "paid_amount": -(cash + card + gift),
                "cash_amount": -cash, "cash_receipt": None,
                "card_amount": -card, "card_type": None,
                "giftcard_amount": -gift, "giftcard_type": None,
                "discount": -disc, "point_amount": 0,
                "unpaid_amount": 0, "unpaid_paid": 0,
                "seller": None, "manager": r["staff"],
                "birth_date": None, "gender": None, "visit_count": None,
            })

        return_rows = conn.execute(f"""
            SELECT r.*, c.name AS customer_name, c.birth_date, c.gender,
                   (SELECT COUNT(*) FROM exams e2 WHERE e2.customer_id = r.customer_id) AS visit_count
            FROM returns r JOIN customers c ON c.id = r.customer_id
            WHERE r.store_id IN ({ph})
            ORDER BY r.id DESC
        """, group_ids).fetchall()
        for r in return_rows:
            amount = r["amount"] or 0
            cash = r["cash_refund"] or 0
            card = r["card_refund"] or 0
            gift = r["giftcard_refund"] or 0
            disc = r["discount_cancel"] or 0
            offset = r["unpaid_offset"] or 0
            rows.append({
                "id": r["id"], "kind": "return", "exam_id": r["exam_id"],
                "customer_id": r["customer_id"], "customer_name": r["customer_name"],
                "sale_date": r["created_at"] or (f"{r['return_date']} 00:00" if r["return_date"] else None),
                "sale_type": "반품",
                "gross_amount": -amount, "net_amount": -amount + disc,
                "paid_amount": -(cash + card + gift),
                "cash_amount": -cash, "cash_receipt": None,
                "card_amount": -card, "card_type": None,
                "giftcard_amount": -gift, "giftcard_type": None,
                "discount": -disc, "point_amount": 0,
                "unpaid_amount": -offset, "unpaid_paid": 0,
                "seller": None, "manager": r["staff"],
                "birth_date": r["birth_date"], "gender": r["gender"], "visit_count": r["visit_count"],
            })

        settle_rows = conn.execute(f"""
            SELECT s.*, c.name AS customer_name, c.birth_date, c.gender,
                   (SELECT COUNT(*) FROM exams e2 WHERE e2.customer_id = s.customer_id) AS visit_count
            FROM settlements s JOIN customers c ON c.id = s.customer_id
            WHERE s.store_id IN ({ph})
            ORDER BY s.id DESC
        """, group_ids).fetchall()
        for s in settle_rows:
            cash = s["cash_amount"] or 0
            card = s["card_amount"] or 0
            gift = s["giftcard_amount"] or 0
            disc = s["discount"] or 0
            total = s["amount"] or 0
            rows.append({
                "id": s["id"], "kind": "settle", "exam_id": s["exam_id"],
                "customer_id": s["customer_id"], "customer_name": s["customer_name"],
                "sale_date": s["created_at"] or (f"{s['settle_date']} 00:00" if s["settle_date"] else None),
                "sale_type": "미수금납입",
                "gross_amount": 0, "net_amount": 0, "paid_amount": cash + card + gift,
                "cash_amount": cash, "cash_receipt": s["cash_receipt"],
                "card_amount": card, "card_type": s["card_type"],
                "giftcard_amount": gift, "giftcard_type": s["giftcard_type"],
                "discount": disc, "point_amount": 0,
                "unpaid_amount": 0, "unpaid_paid": total,
                "seller": s["seller"], "manager": s["staff"],
                "birth_date": s["birth_date"], "gender": s["gender"], "visit_count": s["visit_count"],
            })

        rows.sort(key=lambda r: r["sale_date"] or "", reverse=True)
        return rows


@app.get("/api/unpaid-status")
def unpaid_status(store: dict = Depends(get_current_store)):
    """방문별 미수금이 남아있는 고객들을 누적미수금 기준으로 모아서 보여줌"""
    group_ids = get_group_store_ids(store)
    ph = _in_placeholders(group_ids)
    with get_db() as conn:
        rows = conn.execute(f"""
            SELECT c.id AS customer_id, c.name AS customer_name,
                   SUM(COALESCE(e.unpaid_amount, 0)) AS total_unpaid
            FROM customers c JOIN exams e ON e.customer_id = c.id
            WHERE e.store_id IN ({ph})
            GROUP BY c.id
            HAVING total_unpaid > 0
            ORDER BY total_unpaid DESC
        """, group_ids).fetchall()
        return [dict(r) for r in rows]


# ---------- 매장 채팅 API ----------
# 같은 그룹 안에서 매장이 원하는 상대(들)만 골라 채팅방을 만듦.
# 1번 매장이 2번 매장 한 곳에만 요청할 수도 있고, 여러 매장을 한 방에 초대할 수도 있음.
# 초대받은 매장은 수락(joined)하기 전까지는 그 방의 대화를 읽거나 쓸 수 없음(invited 상태로만 존재)

def _get_room_or_404(conn, room_id: int):
    room = conn.execute("SELECT * FROM chat_rooms WHERE id = ?", (room_id,)).fetchone()
    if not room:
        raise HTTPException(status_code=404, detail="채팅방을 찾을 수 없습니다")
    return room


def _get_joined_membership_or_403(conn, room_id: int, store_id: int):
    m = conn.execute(
        "SELECT * FROM chat_room_members WHERE room_id = ? AND store_id = ? AND status = 'joined'",
        (room_id, store_id),
    ).fetchone()
    if not m:
        raise HTTPException(status_code=403, detail="참여 중인 채팅방이 아닙니다")
    return m


def _room_display_name(conn, room, my_store_id: int) -> str:
    if room["name"]:
        return room["name"]
    others = conn.execute(
        """SELECT s.name FROM chat_room_members crm JOIN stores s ON s.id = crm.store_id
           WHERE crm.room_id = ? AND crm.store_id != ?""",
        (room["id"], my_store_id),
    ).fetchall()
    names = [r["name"] for r in others]
    return ", ".join(names) if names else "(나만 있는 채팅방)"


class ChatRoomCreateIn(BaseModel):
    name: Optional[str] = None
    store_ids: List[int]


class ChatRoomInviteIn(BaseModel):
    store_ids: List[int]


@app.get("/api/chat/group-stores")
def list_chat_group_stores(store: dict = Depends(get_current_store)):
    """채팅방을 만들거나 초대할 때 고를 수 있는, 같은 그룹의 다른 매장 목록"""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT id, name FROM stores WHERE group_id = ? AND id != ? ORDER BY name",
            (store["group_id"], store["id"]),
        ).fetchall()
        return [dict(r) for r in rows]


@app.post("/api/chat/rooms")
def create_chat_room(body: ChatRoomCreateIn, store: dict = Depends(get_current_store)):
    if not body.store_ids:
        raise HTTPException(status_code=400, detail="초대할 매장을 한 곳 이상 선택해 주세요")
    with get_db() as conn:
        ph = _in_placeholders(body.store_ids)
        valid_ids = {
            r["id"] for r in conn.execute(
                f"SELECT id FROM stores WHERE group_id = ? AND id IN ({ph})",
                (store["group_id"], *body.store_ids),
            ).fetchall()
        }
        invite_ids = [sid for sid in dict.fromkeys(body.store_ids) if sid in valid_ids and sid != store["id"]]
        if not invite_ids:
            raise HTTPException(status_code=400, detail="초대할 수 있는 같은 그룹 매장이 없습니다")

        cur = conn.execute(
            "INSERT INTO chat_rooms (group_id, name, created_by) VALUES (?, ?, ?)",
            (store["group_id"], (body.name or "").strip() or None, store["id"]),
        )
        room_id = cur.lastrowid
        conn.execute(
            """INSERT INTO chat_room_members (room_id, store_id, status, invited_by, joined_at)
               VALUES (?, ?, 'joined', ?, datetime('now','localtime'))""",
            (room_id, store["id"], store["id"]),
        )
        for sid in invite_ids:
            conn.execute(
                "INSERT INTO chat_room_members (room_id, store_id, status, invited_by) VALUES (?, ?, 'invited', ?)",
                (room_id, sid, store["id"]),
            )
        conn.commit()
        return {"id": room_id}


@app.get("/api/chat/rooms")
def list_chat_rooms(store: dict = Depends(get_current_store)):
    """내가 참여 중이거나(joined) 초대받은(invited) 채팅방 목록 + 마지막 메시지/안읽은 개수"""
    with get_db() as conn:
        my_memberships = conn.execute(
            "SELECT * FROM chat_room_members WHERE store_id = ? AND status IN ('joined','invited')",
            (store["id"],),
        ).fetchall()

        result = []
        for m in my_memberships:
            room = conn.execute("SELECT * FROM chat_rooms WHERE id = ?", (m["room_id"],)).fetchone()
            if not room:
                continue
            members = conn.execute(
                """SELECT crm.store_id, crm.status, s.name AS store_name
                   FROM chat_room_members crm JOIN stores s ON s.id = crm.store_id
                   WHERE crm.room_id = ?""",
                (room["id"],),
            ).fetchall()
            last_msg = conn.execute(
                "SELECT content, created_at, store_id FROM chat_messages WHERE room_id = ? ORDER BY id DESC LIMIT 1",
                (room["id"],),
            ).fetchone()
            unread = 0
            if m["status"] == "joined":
                unread = conn.execute(
                    "SELECT COUNT(*) FROM chat_messages WHERE room_id = ? AND id > ?",
                    (room["id"], m["last_read_message_id"] or 0),
                ).fetchone()[0]
            result.append({
                "id": room["id"],
                "name": _room_display_name(conn, room, store["id"]),
                "my_status": m["status"],
                "created_by": room["created_by"],
                "members": [dict(mm) for mm in members],
                "last_message": dict(last_msg) if last_msg else None,
                "last_activity": (last_msg["created_at"] if last_msg else room["created_at"]),
                "unread_count": unread,
            })
        result.sort(key=lambda r: r["last_activity"] or "", reverse=True)
        return result


@app.post("/api/chat/rooms/{room_id}/accept")
def accept_chat_room(room_id: int, store: dict = Depends(get_current_store)):
    with get_db() as conn:
        m = conn.execute(
            "SELECT * FROM chat_room_members WHERE room_id = ? AND store_id = ?", (room_id, store["id"]),
        ).fetchone()
        if not m:
            raise HTTPException(status_code=404, detail="채팅 요청을 찾을 수 없습니다")
        conn.execute(
            "UPDATE chat_room_members SET status='joined', joined_at=datetime('now','localtime') WHERE id=?",
            (m["id"],),
        )
        conn.commit()
        return {"ok": True}


@app.post("/api/chat/rooms/{room_id}/decline")
def decline_chat_room(room_id: int, store: dict = Depends(get_current_store)):
    with get_db() as conn:
        m = conn.execute(
            "SELECT * FROM chat_room_members WHERE room_id = ? AND store_id = ?", (room_id, store["id"]),
        ).fetchone()
        if not m:
            raise HTTPException(status_code=404, detail="채팅 요청을 찾을 수 없습니다")
        conn.execute("UPDATE chat_room_members SET status='declined' WHERE id=?", (m["id"],))
        conn.commit()
        return {"ok": True}


@app.post("/api/chat/rooms/{room_id}/invite")
def invite_to_chat_room(room_id: int, body: ChatRoomInviteIn, store: dict = Depends(get_current_store)):
    if not body.store_ids:
        raise HTTPException(status_code=400, detail="초대할 매장을 한 곳 이상 선택해 주세요")
    with get_db() as conn:
        room = _get_room_or_404(conn, room_id)
        _get_joined_membership_or_403(conn, room_id, store["id"])

        ph = _in_placeholders(body.store_ids)
        valid_ids = {
            r["id"] for r in conn.execute(
                f"SELECT id FROM stores WHERE group_id = ? AND id IN ({ph})",
                (room["group_id"], *body.store_ids),
            ).fetchall()
        }
        existing_ids = {
            r["store_id"] for r in
            conn.execute("SELECT store_id FROM chat_room_members WHERE room_id=?", (room_id,)).fetchall()
        }

        added = []
        for sid in dict.fromkeys(body.store_ids):
            if sid in valid_ids and sid not in existing_ids:
                conn.execute(
                    "INSERT INTO chat_room_members (room_id, store_id, status, invited_by) VALUES (?, ?, 'invited', ?)",
                    (room_id, sid, store["id"]),
                )
                added.append(sid)
        conn.commit()
        return {"added": added}


@app.get("/api/chat/rooms/{room_id}/messages")
def list_room_messages(room_id: int, after_id: int = 0, limit: int = 150, store: dict = Depends(get_current_store)):
    """after_id가 0이면 최신 메시지 limit개를 시간순으로, after_id가 있으면(폴링) 그 이후 새 메시지만 돌려줌.
    (참여 중인 방에서만 조회 가능, 조회하는 즉시 그 지점까지 읽음 처리됨)"""
    limit = min(max(limit, 1), 300)
    with get_db() as conn:
        m = _get_joined_membership_or_403(conn, room_id, store["id"])

        if after_id:
            rows = conn.execute(
                """SELECT cm.*, s.name AS store_name FROM chat_messages cm JOIN stores s ON s.id = cm.store_id
                   WHERE cm.room_id = ? AND cm.id > ? ORDER BY cm.id ASC LIMIT ?""",
                (room_id, after_id, limit),
            ).fetchall()
            messages = [dict(r) for r in rows]
        else:
            rows = conn.execute(
                """SELECT cm.*, s.name AS store_name FROM chat_messages cm JOIN stores s ON s.id = cm.store_id
                   WHERE cm.room_id = ? ORDER BY cm.id DESC LIMIT ?""",
                (room_id, limit),
            ).fetchall()
            messages = [dict(r) for r in reversed(rows)]

        latest_id = conn.execute(
            "SELECT MAX(id) FROM chat_messages WHERE room_id = ?", (room_id,)
        ).fetchone()[0] or 0
        if latest_id > (m["last_read_message_id"] or 0):
            conn.execute("UPDATE chat_room_members SET last_read_message_id=? WHERE id=?", (latest_id, m["id"]))
            conn.commit()
        return messages


@app.post("/api/chat/rooms/{room_id}/messages")
def send_room_message(room_id: int, body: ChatMessageIn, store: dict = Depends(get_current_store)):
    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="메시지 내용을 입력해 주세요")
    if len(content) > 2000:
        raise HTTPException(status_code=400, detail="메시지가 너무 깁니다 (최대 2000자)")
    with get_db() as conn:
        m = _get_joined_membership_or_403(conn, room_id, store["id"])
        cur = conn.execute(
            "INSERT INTO chat_messages (room_id, store_id, content) VALUES (?, ?, ?)",
            (room_id, store["id"], content),
        )
        latest_id = cur.lastrowid
        conn.execute("UPDATE chat_room_members SET last_read_message_id=? WHERE id=?", (latest_id, m["id"]))
        conn.commit()
        row = conn.execute("SELECT * FROM chat_messages WHERE id=?", (latest_id,)).fetchone()
        return {**dict(row), "store_name": store["name"]}


@app.post("/api/chat/rooms/{room_id}/upload")
async def upload_chat_attachment(
    room_id: int, file: UploadFile = File(...), caption: str = Form(""),
    store: dict = Depends(get_current_store),
):
    with get_db() as conn:
        m = _get_joined_membership_or_403(conn, room_id, store["id"])

    content_type = (file.content_type or "").split(";")[0].strip().lower()
    ext = CHAT_UPLOAD_ALLOWED_TYPES.get(content_type)
    if not ext:
        raise HTTPException(
            status_code=400,
            detail="지원하지 않는 파일 형식입니다 (이미지, PDF, 워드/엑셀, 텍스트, zip만 가능)",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="빈 파일은 보낼 수 없습니다")
    if len(data) > CHAT_UPLOAD_MAX_SIZE:
        raise HTTPException(status_code=400, detail="파일이 너무 큽니다 (최대 10MB)")

    CHAT_UPLOAD_DIR.mkdir(exist_ok=True)
    stored_name = f"{uuid.uuid4().hex}{ext}"
    (CHAT_UPLOAD_DIR / stored_name).write_bytes(data)

    original_name = (file.filename or "file").strip()[:255]
    caption_text = caption.strip()[:2000]

    with get_db() as conn:
        cur = conn.execute(
            """INSERT INTO chat_messages
               (room_id, store_id, content, attachment_stored_name, attachment_original_name,
                attachment_mime, attachment_size)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (room_id, store["id"], caption_text, stored_name, original_name, content_type, len(data)),
        )
        latest_id = cur.lastrowid
        conn.execute("UPDATE chat_room_members SET last_read_message_id=? WHERE id=?", (latest_id, m["id"]))
        conn.commit()
        row = conn.execute("SELECT * FROM chat_messages WHERE id=?", (latest_id,)).fetchone()
        return {**dict(row), "store_name": store["name"]}


@app.get("/api/chat/attachments/{message_id}")
def get_chat_attachment(message_id: int, store: dict = Depends(get_current_store)):
    with get_db() as conn:
        msg = conn.execute("SELECT * FROM chat_messages WHERE id = ?", (message_id,)).fetchone()
        if not msg or not msg["attachment_stored_name"]:
            raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
        # 그 방에 참여 중인 매장만 열람 가능 (방 격리와 동일한 기준)
        _get_joined_membership_or_403(conn, msg["room_id"], store["id"])

    file_path = CHAT_UPLOAD_DIR / msg["attachment_stored_name"]
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    return FileResponse(
        file_path,
        media_type=msg["attachment_mime"] or "application/octet-stream",
        filename=msg["attachment_original_name"] or "file",
    )


# ---------- 프론트엔드 서빙 ----------
# index.html은 main.py와 같은 폴더에 둡니다 (하위 폴더 없이 단순화)

@app.get("/")
def index():
    # 개발 중 파일을 자주 바꾸므로 브라우저가 옛 버전을 캐시해서 보여주는 일이 없도록 설정
    return FileResponse("index.html", headers={"Cache-Control": "no-store"})


@app.get("/admin")
def admin_page():
    return FileResponse("admin.html", headers={"Cache-Control": "no-store"})
