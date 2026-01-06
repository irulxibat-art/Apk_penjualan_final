import io
import os
import hashlib
import datetime

import psycopg2
import pandas as pd
import streamlit as st

from reportlab.platypus import SimpleDocTemplate, Paragraph, Table
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4

# =============================
# CONFIG / CONNECTION
# =============================
st.set_page_config(page_title="Inventory System", layout="wide")

# Try a few common secret keys for connection string
def _get_conn_string():
    for key in ("postgres_conn", "DATABASE_URL", "POSTGRES_CONN"):
        if key in st.secrets:
            return st.secrets[key]
    return None

conn_str = _get_conn_string()
if conn_str is None:
    st.error(
        "Database connection string not found in st.secrets. "
        "Please add st.secrets['postgres_conn'] or st.secrets['DATABASE_URL']."
    )
    st.stop()

@st.cache_resource
def get_connection():
    return psycopg2.connect(conn_str)

conn = get_connection()

# =============================
# SESSION STATE
# =============================
if "user" not in st.session_state:
    st.session_state.user = None

if "edit_product_id" not in st.session_state:
    st.session_state.edit_product_id = None

# =============================
# HELPERS
# =============================
def hash_password(p: str) -> str:
    return hashlib.sha256(p.encode()).hexdigest()

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

# =============================
# AUTH
# =============================
def create_default_user():
    # Create a default 'boss' user if not exists
    q = "SELECT id FROM users WHERE username=%s"
    if _exec(q, ("boss",), fetchone=True) is None:
        q_ins = "INSERT INTO users (username, password, role, created_at) VALUES (%s, %s, %s, %s)"
        _exec(q_ins, ("boss", hash_password("boss123"), "boss", datetime.datetime.utcnow().isoformat()), commit=True)

create_default_user()

def login_user(username: str, password: str):
    hashed = hash_password(password)
    q = "SELECT id, username, role FROM users WHERE username=%s AND password=%s"
    res = _exec(q, (username, hashed), fetchone=True)
    if res:
        return {"id": res[0], "username": res[1], "role": res[2]}
    return None

# =============================
# STORE STATUS
# =============================
def get_store_status():
    q = "SELECT status FROM store_status WHERE id=1"
    res = _exec(q, (), fetchone=True)
    return res[0] if res else "closed"

def set_store_status(status: str):
    q = "UPDATE store_status SET status=%s WHERE id=1"
    _exec(q, (status,), commit=True)

# =============================
# PRODUCT FUNCTIONS
# =============================
def add_product(sku: str, name: str, cost: float, price: float):
    q = """
        INSERT INTO products (sku, name, cost, price, stock, warehouse_stock, created_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """
    _exec(q, (sku, name, cost, price, 0, 0, datetime.datetime.utcnow().isoformat()), commit=True)

def update_product(pid: int, sku: str, name: str, cost: float, price: float, role: str):
    if role != "boss":
        q = "UPDATE products SET sku=%s, name=%s WHERE id=%s"
        _exec(q, (sku, name, pid), commit=True)
    else:
        q = "UPDATE products SET sku=%s, name=%s, cost=%s, price=%s WHERE id=%s"
        _exec(q, (sku, name, cost, price, pid), commit=True)

def delete_product(pid: int):
    q = "SELECT COUNT(*) FROM sales WHERE product_id=%s"
    cnt = _exec(q, (pid,), fetchone=True)
    if cnt and cnt[0] > 0:
        return False, "Produk sudah pernah dijual"
    q_del = "DELETE FROM products WHERE id=%s"
    _exec(q_del, (pid,), commit=True)
    return True, "Produk dihapus"

def add_warehouse_stock(pid: int, qty: int):
    q = "UPDATE products SET warehouse_stock = warehouse_stock + %s WHERE id=%s"
    _exec(q, (qty, pid), commit=True)

def move_stock(pid: int, qty: int):
    q = "SELECT warehouse_stock FROM products WHERE id=%s"
    res = _exec(q, (pid,), fetchone=True)
    if res is None:
        return False, "Produk tidak ditemukan"
    warehouse_stock = res[0]
    if qty > warehouse_stock:
        return False, "Stok gudang tidak cukup"
    q_update = """
        UPDATE products
        SET warehouse_stock = warehouse_stock - %s,
            stock = stock + %s
        WHERE id=%s
    """
    _exec(q_update, (qty, qty, pid), commit=True)
    return True, "Stok dipindahkan"

def get_products():
    return pd.read_sql("SELECT * FROM products ORDER BY name", conn)

# =============================
# SALES
# =============================
def record_sale(pid: int, qty: int, user_id: int):
    q = "SELECT stock, cost, price FROM products WHERE id=%s"
    res = _exec(q, (pid,), fetchone=True)
    if not res:
        return False, "Produk tidak ditemukan"
    stock, cost, price = res
    if qty > stock:
        return False, "Stok tidak cukup"
    total = qty * price
    profit = (price - cost) * qty
    q_ins = """
        INSERT INTO sales
        (product_id, qty, cost_each, price_each, total, profit, sold_by, sold_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    _exec(q_ins, (pid, qty, cost, price, total, profit, user_id, datetime.datetime.utcnow().isoformat()), commit=True)
    _exec("UPDATE products SET stock = stock - %s WHERE id=%s", (qty, pid), commit=True)
    return True, "Penjualan berhasil"

def get_sales(role: str):
    if role == "boss":
        q = """
            SELECT p.name, s.qty, s.total, s.profit, s.sold_at
            FROM sales s JOIN products p ON s.product_id = p.id
        """
    else:
        q = """
            SELECT p.name, s.qty, s.total, s.sold_at
            FROM sales s JOIN products p ON s.product_id = p.id
        """
    return pd.read_sql(q, conn)

def get_today_summary():
    q = """
        SELECT COALESCE(SUM(total), 0), COALESCE(SUM(profit), 0)
        FROM sales
        WHERE DATE(sold_at) = CURRENT_DATE
    """
    res = _exec(q, (), fetchone=True)
    return res if res else (0, 0)

# =============================
# PDF EXPORT (BOSS ONLY)
# =============================
def export_sales_pdf(df: pd.DataFrame, filename: str, title: str = None):
    if df is None or df.empty:
        return None

    # Ensure filename dir exists
    os.makedirs(os.path.dirname(filename) or ".", exist_ok=True)

    styles = getSampleStyleSheet()
    elements = []

    # Title
    elements.append(Paragraph(title or "LAPORAN PENJUALAN", styles["Title"]))
    elements.append(Paragraph(f"Tanggal Cetak: {datetime.datetime.now().strftime('%d-%m-%Y %H:%M')}", styles["Normal"]))
    elements.append(Paragraph("<br />", styles["Normal"]))

    # Convert datetimes for table display
    df_display = df.copy()
    for col in df_display.columns:
        if df_display[col].dtype == "datetime64[ns]":
            df_display[col] = df_display[col].dt.strftime("%d-%m-%Y %H:%M")

    table_data = [df_display.columns.tolist()] + df_display.fillna("").values.tolist()
    table = Table(table_data, repeatRows=1)
    elements.append(table)

    # Totals
    total_penjualan = df.get("total", pd.Series(dtype=float)).sum()
    total_profit = df.get("profit", pd.Series(dtype=float)).sum() if "profit" in df.columns else 0

    elements.append(Paragraph("<br />", styles["Normal"]))
    elements.append(Paragraph(f"<b>Total Penjualan:</b> Rp {int(total_penjualan):,}", styles["Normal"]))
    elements.append(Paragraph(f"<b>Total P&L:</b> Rp {int(total_profit):,}", styles["Normal"]))

    doc = SimpleDocTemplate(filename, pagesize=A4)
    doc.build(elements)
    return filename

# =============================
# ARCHIVE DAILY SALES
# =============================
def check_and_archive_daily_sales():
    today = datetime.date.today()
    yesterday = today - datetime.timedelta(days=1)

    # Get last archive date
    q = "SELECT MAX(archive_date) FROM sales_archive"
    res = _exec(q, (), fetchone=True)
    last_archive = res[0] if res and res[0] is not None else None

    if last_archive == yesterday.isoformat():
        return

    # Sum totals for yesterday
    q_sum = """
        SELECT SUM(total), SUM(profit)
        FROM sales
        WHERE DATE(sold_at) = %s
    """
    res_sum = _exec(q_sum, (yesterday.isoformat(),), fetchone=True)
    if not res_sum or res_sum[0] is None:
        return

    total_sales = res_sum[0]
    total_profit = res_sum[1] or 0

    # Week number in month (simple)
    week_number = (yesterday.day - 1) // 7 + 1

    pdf_filename = f"Laporan_Harian_{yesterday.strftime('%A')}_{yesterday.strftime('%d-%m-%Y')}_Minggu-{week_number}.pdf"

    df_yesterday = pd.read_sql(
        """
        SELECT p.name, s.qty, s.total, s.profit, s.sold_at
        FROM sales s
        JOIN products p ON s.product_id = p.id
        WHERE DATE(s.sold_at) = %s
        """,
        conn,
        params=(yesterday.isoformat(),)
    )

    exported = export_sales_pdf(df_yesterday, pdf_filename, title=f"Laporan Penjualan Harian {yesterday.strftime('%d-%m-%Y')}")
    inserted_at = datetime.datetime.utcnow().isoformat()

    q_ins = """
        INSERT INTO sales_archive (
            archive_date,
            week_number,
            month,
            year,
            total_sales,
            total_profit,
            pdf_file,
            archived_at
        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    _exec(q_ins, (yesterday.isoformat(), week_number, yesterday.month, yesterday.year, total_sales, total_profit, exported, inserted_at), commit=True)

    # Remove archived sales
    q_del = "DELETE FROM sales WHERE DATE(sold_at) = %s"
    _exec(q_del, (yesterday.isoformat(),), commit=True)

# =============================
# UI / LOGIN
# =============================
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
                st.experimental_rerun()
        else:
            st.error("Login gagal")

# =============================
# MAIN APP
# =============================
else:
    user = st.session_state.user
    role = user["role"]

    st.sidebar.write(f"{user['username']} ({role})")

    if st.sidebar.button("Logout"):
        st.session_state.user = None
        st.experimental_rerun()

    menu = st.sidebar.selectbox(
        "Menu",
        ["Home", "Stok Gudang", "Produk & Stok", "Penjualan", "Histori Penjualan", "Manajemen User"]
        if role == "boss"
        else ["Home", "Penjualan", "Histori Penjualan"]
    )

    # HOME
    if menu == "Home":
        st.header("Dashboard")
        st.subheader(f"Status Toko: {get_store_status().upper()}")

        if role == "boss":
            col1, col2 = st.columns(2)
            if col1.button("Buka Toko"):
                set_store_status("open")
                st.experimental_rerun()
            if col2.button("Tutup Toko"):
                set_store_status("closed")
                st.experimental_rerun()

    # STOK GUDANG
    elif menu == "Stok Gudang":
        st.header("Stok Gudang")

        with st.form("add_prod"):
            sku = st.text_input("SKU")
            name = st.text_input("Nama Produk")
            cost = st.number_input("Harga Modal", min_value=0.0)
            price = st.number_input("Harga Jual", min_value=0.0)
            if st.form_submit_button("Tambah Produk"):
                if not sku or not name:
                    st.error("SKU dan Nama wajib diisi")
                else:
                    add_product(sku, name, cost, price)
                    st.experimental_rerun()

        df = get_products()
        if not df.empty:
            pid = st.selectbox(
                "Pilih Produk",
                df["id"],
                format_func=lambda x: df[df.id == x]["name"].values[0]
            )

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
                        st.experimental_rerun()

            qty = st.number_input("Tambah Stok Gudang", min_value=1, value=1)
            if st.button("Tambah Stok"):
                add_warehouse_stock(pid, int(qty))
                st.experimental_rerun()

            if st.button("Hapus Produk"):
                ok, msg = delete_product(pid)
                if ok:
                    st.success(msg)
                    st.experimental_rerun()
                else:
                    st.error(msg)

            st.dataframe(df[["sku", "name", "warehouse_stock"]])

    # PRODUK & STOK
    elif menu == "Produk & Stok":
        st.header("Stok Harian")

        df = get_products()

        if df.empty:
            st.info("Belum ada produk")
        else:
            pid = st.selectbox(
                "Pilih Produk",
                df["id"],
                format_func=lambda x: df[df.id == x]["name"].values[0]
            )

            qty = st.number_input("Jumlah Ambil dari Gudang", min_value=1, value=1)

            if st.button("Ambil ke Stok Harian"):
                ok, msg = move_stock(pid, int(qty))
                if ok:
                    st.success(msg)
                    st.experimental_rerun()
                else:
                    st.error(msg)

            st.subheader("📦 Tabel Stok Harian")
            st.dataframe(df[["sku", "name", "stock"]])

    # PENJUALAN
    elif menu == "Penjualan":
        df = get_products()
        if df.empty:
            st.info("Belum ada produk")
        else:
            mapping = {
                f"{r['name']} (Sisa: {r['stock']})": r['id']
                for _, r in df.iterrows()
            }

            pilih = st.selectbox("Pilih Produk", list(mapping.keys()))
            pid = mapping[pilih]
            sisa = int(df[df["id"] == pid]["stock"].values[0])
            if sisa == 0:
                st.warning("Stok produk ini HABIS")

            qty = st.number_input(
                "Qty",
                min_value=1,
                max_value=max(1, sisa),
                value=1,
                disabled=(sisa == 0)
            )

            if st.button("Simpan Penjualan"):
                ok, msg = record_sale(pid, int(qty), user["id"])
                if ok:
                    st.success(msg)
                    st.experimental_rerun()
                else:
                    st.error(msg)

    # HISTORI PENJUALAN
    elif menu == "Histori Penjualan":
        # Archive check (non-blocking)
        try:
            check_and_archive_daily_sales()
        except Exception as e:
            st.warning(f"Archive check gagal: {e}")

        st.header("History Penjualan")

        if role == "boss":
            mode = st.radio("Pilih Mode History", ["History Harian", "History Mingguan"])
            if mode == "History Harian":
                df = pd.read_sql(
                    """
                    SELECT p.name, s.qty, s.total, s.profit, s.sold_at
                    FROM sales s
                    JOIN products p ON s.product_id = p.id
                    WHERE DATE(s.sold_at) = CURRENT_DATE
                    """,
                    conn
                )

                st.subheader("History Harian (Hari Ini)")
                st.dataframe(df)

                total_df = pd.read_sql(
                    """
                    SELECT COALESCE(SUM(total),0) AS total_sales, COALESCE(SUM(profit),0) AS total_profit
                    FROM sales
                    WHERE DATE(sold_at) = CURRENT_DATE
                    """,
                    conn
                )

                total_sales = int(total_df.iloc[0]["total_sales"] or 0)
                total_profit = int(total_df.iloc[0]["total_profit"] or 0)

                col1, col2 = st.columns(2)
                col1.metric(label="Total Penjualan Hari Ini", value=f"💸Rp {total_sales:,}")
                col2.metric(label="Total P&L Hari Ini", value=f"💸Rp {total_profit:,}")

            elif mode == "History Mingguan":
                df = pd.read_sql(
                    """
                    SELECT archive_date, week_number, total_sales, total_profit, pdf_file
                    FROM sales_archive
                    ORDER BY archive_date DESC
                    """,
                    conn
                )
                st.subheader("History Mingguan")
                st.dataframe(df)

        else:
            df = pd.read_sql(
                """
                SELECT p.name, s.qty, s.total, s.sold_at
                FROM sales s
                JOIN products p ON s.product_id = p.id
                WHERE DATE(s.sold_at) = CURRENT_DATE
                """,
                conn
            )
            st.subheader("History Harian (Hari Ini)")
            st.dataframe(df)

            total_df = pd.read_sql(
                """
                SELECT COALESCE(SUM(total),0) AS total_sales
                FROM sales
                WHERE DATE(sold_at) = CURRENT_DATE
                """,
                conn
            )

            total_sales = int(total_df.iloc[0]["total_sales"] or 0)
            st.metric(label="Total Penjualan Hari Ini", value=f"💸Rp {total_sales:,}")

    # USER MANAGEMENT (boss only)
    elif menu == "Manajemen User":
        if role != "boss":
            st.error("Hanya boss yang bisa mengelola user")
        else:
            with st.form("add_user"):
                u = st.text_input("Username")
                p = st.text_input("Password", type="password")
                r = st.selectbox("Role", ["boss", "karyawan"])
                if st.form_submit_button("Tambah User"):
                    if not u or not p:
                        st.error("Username dan password wajib")
                    else:
                        try:
                            _exec(
                                "INSERT INTO users (username, password, role, created_at) VALUES (%s, %s, %s, %s)",
                                (u, hash_password(p), r, datetime.datetime.utcnow().isoformat()),
                                commit=True
                            )
                            st.success("User ditambahkan")
                            st.experimental_rerun()
                        except Exception as e:
                            st.error(f"Gagal tambah user: {e}")