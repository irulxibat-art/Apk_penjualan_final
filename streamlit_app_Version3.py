import io
import os
import hashlib
import datetime
import typing

import bcrypt
import psycopg2
import pandas as pd
import streamlit as st

from reportlab.platypus import SimpleDocTemplate, Paragraph, Table
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from supabase import create_client

# -------------------------
# CONFIG / SECRETS VALIDATION
# -------------------------
st.set_page_config(page_title="Inventory System", layout="wide")

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_SERVICE_KEY = st.secrets["SUPABASE_SERVICE_KEY"]
ANON_KEY = st.secrets["SUPABASE_ANON_KEY"]
POSTGRES_CONN = st.secrets["SUPABASE_DB_URL"] 
supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# -------------------------
# DATABASE CONNECTION
# -------------------------
@st.cache_resource
def get_connection():
    # psycopg2 accepts a connection string
    return psycopg2.connect(POSTGRES_CONN)

conn = get_connection()

def _exec(query: str, params: tuple = (), fetchone=False, fetchall=False, commit=False):
    cur = conn.cursor()
    try:
        cur.execute(query, params)
        if commit:
            conn.commit()
        if fetchone:
            return cur.fetchone()
        if fetchall:
            return cur.fetchall()
        return None
    finally:
        cur.close()

# -------------------------
# PASSWORD UTIL (bcrypt with SHA256 fallback migration)
# -------------------------
def hash_password_bcrypt(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

def is_probably_sha256(hex_str: str) -> bool:
    return isinstance(hex_str, str) and len(hex_str) == 64 and all(c in "0123456789abcdef" for c in hex_str.lower())

def verify_and_migrate_password(username: str, plain_password: str, stored_hash: str) -> bool:
    """
    Verify password:
    - If stored_hash is bcrypt, verify with bcrypt.
    - If stored_hash looks like SHA256 hex, compare hashed(plain) with stored_hash; if matches, re-hash with bcrypt and update DB.
    Returns True if password OK.
    """
    if stored_hash is None:
        return False

    # bcrypt
    if stored_hash.startswith("$2"):
        try:
            return bcrypt.checkpw(plain_password.encode(), stored_hash.encode())
        except Exception:
            return False

    # SHA256 fallback
    if is_probably_sha256(stored_hash):
        h = hashlib.sha256(plain_password.encode()).hexdigest()
        if h == stored_hash:
            # migrate: re-hash with bcrypt and update DB
            new_hash = hash_password_bcrypt(plain_password)
            try:
                _exec("UPDATE users SET password=%s WHERE username=%s", (new_hash, username), commit=True)
            except Exception:
                # migration best-effort; don't fail login if update fails
                pass
            return True
    return False

# -------------------------
# AUTH / USER MANAGEMENT
# -------------------------
def create_default_user():
    q = "SELECT id FROM users WHERE username=%s"
    if _exec(q, ("boss",), fetchone=True) is None:
        pw = hash_password_bcrypt("boss123")
        _exec("INSERT INTO users (username, password, role, created_at) VALUES (%s, %s, %s, %s)",
              ("boss", pw, "boss", datetime.datetime.utcnow().isoformat()), commit=True)

create_default_user()

def login_user(username: str, password: str) -> typing.Optional[dict]:
    q = "SELECT id, username, password, role FROM users WHERE username=%s"
    row = _exec(q, (username,), fetchone=True)
    if not row:
        return None
    user_id, uname, stored_hash, role = row
    if verify_and_migrate_password(uname, password, stored_hash):
        return {"id": user_id, "username": uname, "role": role}
    return None

def create_user(username: str, password: str, role: str = "karyawan"):
    pw_hash = hash_password_bcrypt(password)
    _exec("INSERT INTO users (username, password, role, created_at) VALUES (%s, %s, %s, %s)",
          (username, pw_hash, role, datetime.datetime.utcnow().isoformat()), commit=True)

# -------------------------
# STORE STATUS
# -------------------------
def get_store_status():
    r = _exec("SELECT status FROM store_status WHERE id=1", fetchone=True)
    return r[0] if r else "closed"

def set_store_status(status: str):
    _exec("UPDATE store_status SET status=%s WHERE id=1", (status,), commit=True)

# -------------------------
# PRODUCT FUNCTIONS
# -------------------------
def add_product(sku: str, name: str, cost: float, price: float):
    q = """
    INSERT INTO products (sku, name, cost, price, stock, warehouse_stock, created_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    _exec(q, (sku, name, cost, price, 0, 0, datetime.datetime.utcnow().isoformat()), commit=True)

def update_product(pid: int, sku: str, name: str, cost: float, price: float, role: str):
    if role != "boss":
        _exec("UPDATE products SET sku=%s, name=%s WHERE id=%s", (sku, name, pid), commit=True)
    else:
        _exec("UPDATE products SET sku=%s, name=%s, cost=%s, price=%s WHERE id=%s", (sku, name, cost, price, pid), commit=True)

def delete_product(pid: int):
    cnt = _exec("SELECT COUNT(*) FROM sales WHERE product_id=%s", (pid,), fetchone=True)
    if cnt and cnt[0] > 0:
        return False, "Produk sudah pernah dijual"
    _exec("DELETE FROM products WHERE id=%s", (pid,), commit=True)
    return True, "Produk dihapus"

def add_warehouse_stock(pid: int, qty: int):
    _exec("UPDATE products SET warehouse_stock = warehouse_stock + %s WHERE id=%s", (qty, pid), commit=True)

def move_stock(pid: int, qty: int):
    row = _exec("SELECT warehouse_stock FROM products WHERE id=%s", (pid,), fetchone=True)
    if not row:
        return False, "Produk tidak ditemukan"
    warehouse_stock = row[0]
    if qty > warehouse_stock:
        return False, "Stok gudang tidak cukup"
    _exec("""
        UPDATE products
        SET warehouse_stock = warehouse_stock - %s, stock = stock + %s
        WHERE id=%s
    """, (qty, qty, pid), commit=True)
    return True, "Stok dipindahkan"

def get_products():
    return pd.read_sql("SELECT * FROM products ORDER BY name", conn)

# -------------------------
# SALES
# -------------------------
def record_sale(pid: int, qty: int, user_id: int):
    row = _exec("SELECT stock, cost, price FROM products WHERE id=%s", (pid,), fetchone=True)
    if not row:
        return False, "Produk tidak ditemukan"
    stock, cost, price = row
    if qty > stock:
        return False, "Stok tidak cukup"
    total = qty * price
    profit = (price - cost) * qty
    _exec("""
        INSERT INTO sales (product_id, qty, cost_each, price_each, total, profit, sold_by, sold_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
    """, (pid, qty, cost, price, total, profit, user_id, datetime.datetime.utcnow().isoformat()), commit=True)
    _exec("UPDATE products SET stock = stock - %s WHERE id=%s", (qty, pid), commit=True)
    return True, "Penjualan berhasil"

def get_sales(role: str):
    if role == "boss":
        q = """SELECT p.name, s.qty, s.total, s.profit, s.sold_at FROM sales s JOIN products p ON s.product_id=p.id"""
    else:
        q = """SELECT p.name, s.qty, s.total, s.sold_at FROM sales s JOIN products p ON s.product_id=p.id"""
    return pd.read_sql(q, conn)

# -------------------------
# PDF EXPORT (in-memory)
# -------------------------
def export_sales_pdf_bytes(df: pd.DataFrame, title: str = None) -> bytes:
    if df is None or df.empty:
        return b""
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    elements = []
    elements.append(Paragraph(title or "LAPORAN PENJUALAN", styles["Title"]))
    elements.append(Paragraph(f"Tanggal Cetak: {datetime.datetime.now().strftime('%d-%m-%Y %H:%M')}", styles["Normal"]))
    elements.append(Paragraph("<br/>", styles["Normal"]))

    df_display = df.copy()
    for col in df_display.columns:
        if pd.api.types.is_datetime64_any_dtype(df_display[col]):
            df_display[col] = df_display[col].dt.strftime("%d-%m-%Y %H:%M")

    table_data = [df_display.columns.tolist()] + df_display.fillna("").values.tolist()
    table = Table(table_data, repeatRows=1)
    elements.append(table)

    total_penjualan = float(df["total"].sum()) if "total" in df.columns else 0.0
    total_profit = float(df["profit"].sum()) if "profit" in df.columns else 0.0

    elements.append(Paragraph("<br/>", styles["Normal"]))
    elements.append(Paragraph(f"<b>Total Penjualan:</b> Rp {int(total_penjualan):,}", styles["Normal"]))
    elements.append(Paragraph(f"<b>Total P&L:</b> Rp {int(total_profit):,}", styles["Normal"]))

    doc = SimpleDocTemplate(buffer, pagesize=A4)
    doc.build(elements)
    buffer.seek(0)
    return buffer.read()

def upload_pdf_to_supabase(file_path, file_name):
    with open(file_path, "rb") as f:
        file_bytes = f.read()

    response = supabase.storage.from_("sales-pdf").upload(
        file_name,
        file_bytes,
        {"content-type": "application/pdf"}
    )

    public_url = supabase.storage.from_("sales-pdf").get_public_url(file_name)
    return public_url

# -------------------------
# ARCHIVE DAILY SALES
# -------------------------
cursor.execute("""
    INSERT INTO sales_archive 
    (archive_date, week_number, month, year, total_sales, total_profit, pdf_url)
    VALUES (%s,%s,%s,%s,%s,%s,%s)
""", (date, week, month, year, total, profit, pdf_url))

def check_and_archive_daily_sales():
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)

    last_archive_row = _exec("SELECT MAX(archive_date) FROM sales_archive", (), fetchone=True)
    last_archive = last_archive_row[0] if last_archive_row else None
    # if already archived for yesterday, return
    if last_archive == yesterday.isoformat():
        return

    sums = _exec("SELECT SUM(total), SUM(profit) FROM sales WHERE DATE(sold_at) = %s", (yesterday.isoformat(),), fetchone=True)
    if not sums or sums[0] is None:
        return

    total_sales, total_profit = sums[0], sums[1] or 0
    week_number = (yesterday.day - 1) // 7 + 1

    df_yesterday = pd.read_sql("""
        SELECT p.name, s.qty, s.total, s.profit, s.sold_at
        FROM sales s JOIN products p ON s.product_id = p.id
        WHERE DATE(s.sold_at) = %s
    """, conn, params=(yesterday.isoformat(),))

    pdf_bytes = export_sales_pdf_bytes(df_yesterday, title=f"Laporan Penjualan Harian {yesterday.strftime('%d-%m-%Y')}")
    if pdf_bytes:
        # save local file (optional) and record filename in DB
        filename = f"Laporan_Harian_{yesterday.strftime('%d-%m-%Y')}_Minggu-{week_number}.pdf"
        with open(filename, "wb") as f:
            f.write(pdf_bytes)

        _exec("""
            INSERT INTO sales_archive (archive_date, week_number, month, year, total_sales, total_profit, pdf_file, archived_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """, (yesterday.isoformat(), week_number, yesterday.month, yesterday.year, total_sales, total_profit, filename, datetime.datetime.utcnow().isoformat()), commit=True)

    # delete archived sales
    _exec("DELETE FROM sales WHERE DATE(sold_at) = %s", (yesterday.isoformat(),), commit=True)

# -------------------------
# UI / LOGIN
# -------------------------
if "user" not in st.session_state:
    st.session_state.user = None
if "edit_product_id" not in st.session_state:
    st.session_state.edit_product_id = None

if st.session_state.user is None:
    st.title("Login Sistem")
    u = st.text_input("Username")
    p = st.text_input("Password", type="password")

    if st.button("Login"):
        user = login_user(u, p)
        if user:
            if user["role"] == "karyawan" and get_store_status() == "closed":
                st.error("Toko sedang tutup")
            else:
                st.session_state.user = user
                st.rerun()
        else:
            st.error("Login gagal")

# -------------------------
# MAIN APP
# -------------------------
else:
    user = st.session_state.user
    role = user["role"]

    st.sidebar.write(f"{user['username']} ({role})")
    if st.sidebar.button("Logout"):
        st.session_state.user = None
        st.rerun()

    menu = st.sidebar.selectbox(
        "Menu",
        ["Home", "Stok Gudang", "Produk & Stok", "Penjualan", "Histori Penjualan", "Manajemen User"]
        if role == "boss"
        else ["Home", "Penjualan", "Histori Penjualan"]
    )

    # Home
    if menu == "Home":
        st.header("Dashboard")
        st.subheader(f"Status Toko: {get_store_status().upper()}")
        if role == "boss":
            col1, col2 = st.columns(2)
            if col1.button("Buka Toko"):
                set_store_status("open")
                st.rerun()
            if col2.button("Tutup Toko"):
                set_store_status("closed")
                st.rerun()

    # Stok Gudang
    elif menu == "Stok Gudang":
        st.header("Stok Gudang")
        with st.form("add_prod"):
            sku = st.text_input("SKU")
            name = st.text_input("Nama Produk")
            cost = st.number_input("Harga Modal", min_value=0.0, format="%.2f")
            price = st.number_input("Harga Jual", min_value=0.0, format="%.2f")
            if st.form_submit_button("Tambah Produk"):
                if not sku or not name:
                    st.error("SKU dan Nama wajib diisi")
                else:
                    add_product(sku, name, cost, price)
                    st.rerun()

        df = get_products()
        if not df.empty:
            pid = st.selectbox("Pilih Produk", df["id"], format_func=lambda x: df[df.id == x]["name"].values[0])
            row = df[df.id == pid].iloc[0]

            if st.button("✏️ Edit Produk"):
                st.session_state.edit_product_id = pid

            if st.session_state.edit_product_id == pid:
                with st.form("edit_prod"):
                    sku = st.text_input("SKU", row["sku"])
                    name = st.text_input("Nama Produk", row["name"])
                    if role == "boss":
                        cost = st.number_input("Harga Modal", value=float(row["cost"]))
                        price = st.number_input("Harga Jual", value=float(row["price"]))
                    else:
                        st.info("Harga hanya bisa diubah oleh boss")
                        cost = row["cost"]
                        price = row["price"]
                    if st.form_submit_button("Simpan"):
                        update_product(pid, sku, name, cost, price, role)
                        st.session_state.edit_product_id = None
                        st.rerun()

            qty = st.number_input("Tambah Stok Gudang", min_value=1, value=1)
            if st.button("Tambah Stok"):
                add_warehouse_stock(pid, int(qty))
                st.rerun()

            if st.button("Hapus Produk"):
                ok, msg = delete_product(pid)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

            st.dataframe(df[["sku", "name", "warehouse_stock"]])

    # Produk & Stok
    elif menu == "Produk & Stok":
        st.header("Stok Harian")
        df = get_products()
        if df.empty:
            st.info("Belum ada produk")
        else:
            pid = st.selectbox("Pilih Produk", df["id"], format_func=lambda x: df[df.id == x]["name"].values[0])
            qty = st.number_input("Jumlah Ambil dari Gudang", min_value=1, value=1)
            if st.button("Ambil ke Stok Harian"):
                ok, msg = move_stock(pid, int(qty))
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
            st.subheader("📦 Tabel Stok Harian")
            st.dataframe(df[["sku", "name", "stock"]])

    # Penjualan
    elif menu == "Penjualan":
        df = get_products()
        if df.empty:
            st.info("Belum ada produk")
        else:
            mapping = {f"{r['name']} (Sisa: {r['stock']})": r['id'] for _, r in df.iterrows()}
            pilih = st.selectbox("Pilih Produk", list(mapping.keys()))
            pid = mapping[pilih]
            sisa = int(df[df["id"] == pid]["stock"].values[0])
            if sisa == 0:
                st.warning("Stok produk ini HABIS")
            qty = st.number_input("Qty", min_value=1, max_value=max(1, sisa), value=1, disabled=(sisa == 0))
            if st.button("Simpan Penjualan"):
                ok, msg = record_sale(pid, int(qty), user["id"])
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

    # Histori Penjualan
    elif menu == "Histori Penjualan":
        try:
            check_and_archive_daily_sales()
        except Exception as e:
            st.warning(f"Archive check gagal: {e}")

        st.header("History Penjualan")
        if role == "boss":
            mode = st.radio("Pilih Mode History", ["History Harian", "History Mingguan"])
            if mode == "History Harian":
                df = pd.read_sql("""
                    SELECT p.name, s.qty, s.total, s.profit, s.sold_at
                    FROM sales s JOIN products p ON s.product_id = p.id
                    WHERE DATE(s.sold_at) = CURRENT_DATE
                """, conn)
                st.subheader("History Harian (Hari Ini)")
                st.dataframe(df)
                total_df = pd.read_sql("""
                    SELECT COALESCE(SUM(total),0) AS total_sales, COALESCE(SUM(profit),0) AS total_profit
                    FROM sales
                    WHERE DATE(sold_at) = CURRENT_DATE
                """, conn)
                total_sales = int(total_df.iloc[0]["total_sales"] or 0)
                total_profit = int(total_df.iloc[0]["total_profit"] or 0)
                col1, col2 = st.columns(2)
                col1.metric(label="Total Penjualan Hari Ini", value=f"💸Rp {total_sales:,}")
                col2.metric(label="Total P&L Hari Ini", value=f"💸Rp {total_profit:,}")
                # download PDF of today's sales (boss)
                if st.button("Export PDF Hari Ini (Boss)"):
                    pdf_df = df.copy()
                    pdf_bytes = export_sales_pdf_bytes(pdf_df, title=f"Laporan Penjualan Hari Ini {datetime.date.today().strftime('%d-%m-%Y')}")
                    if pdf_bytes:
                        st.download_button("Download Laporan Hari Ini (PDF)", data=pdf_bytes, file_name=f"laporan_harian_{datetime.date.today().isoformat()}.pdf", mime="application/pdf")
            else:
                df = pd.read_sql("SELECT archive_date, week_number, total_sales, total_profit, pdf_file FROM sales_archive ORDER BY archive_date DESC", conn)
                st.subheader("History Mingguan")
                st.dataframe(df)
                # allow download of pdf files if present
                if not df.empty:
                    sel = st.selectbox("Pilih archive row untuk download", df.index)
                    pdf_file = df.loc[sel, "pdf_file"]
                    if pdf_file and os.path.exists(pdf_file):
                        with open(pdf_file, "rb") as f:
                            b = f.read()
                        st.download_button("Download PDF Archive", data=b, file_name=pdf_file, mime="application/pdf")
        else:
            df = pd.read_sql("""
                SELECT p.name, s.qty, s.total, s.sold_at
                FROM sales s JOIN products p ON s.product_id = p.id
                WHERE DATE(s.sold_at) = CURRENT_DATE
            """, conn)
            st.subheader("History Harian (Hari Ini)")
            st.dataframe(df)
            total_df = pd.read_sql("SELECT COALESCE(SUM(total),0) AS total_sales FROM sales WHERE DATE(sold_at) = CURRENT_DATE", conn)
            total_sales = int(total_df.iloc[0]["total_sales"] or 0)
            st.metric(label="Total Penjualan Hari Ini", value=f"💸Rp {total_sales:,}")

    # Manajemen User
    elif menu == "Manajemen User":
        st.header("Manajemen User")

        with st.form("add_user"):
            new_user = st.text_input("Username Baru")
            new_pass = st.text_input("Password", type="password")
            role = st.selectbox("Role", ["karyawan", "boss"])
            if st.form_submit_button("Tambah User"):
                if not new_user or not new_pass:
                    st.error("Username dan password wajib diisi")
                else:
                    create_user(new_user, new_pass, role)
                    st.success("User berhasil ditambahkan")
                    st.rerun()

