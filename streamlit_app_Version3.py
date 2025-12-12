import streamlit as st
import sqlite3
import pandas as pd
import hashlib
import datetime

st.set_page_config(page_title="Inventory System", layout="wide")

# ===================================================
#  UI THEME — GALAXY + GLASSMORPHISM (Opsi 1)
# ===================================================
page_bg_css = """
<style>

/* BACKGROUND GALAXY */
.stApp {
    background: radial-gradient(circle at 20% 20%, #a78bfa 0%, #8b5cf6 25%, #3b82f6 60%, #0ea5e9 100%) !important;
    background-attachment: fixed;
}

/* CARD + COLUMN STYLE — Glassmorphism (Putih Transparan) */
div[data-testid="stVerticalBlock"] > div,
div[data-testid="stColumn"] > div,
.stForm {
    background: rgba(255, 255, 255, 0.40) !important;
    padding: 20px !important;
    border-radius: 16px !important;
    backdrop-filter: blur(12px) !important;
    -webkit-backdrop-filter: blur(12px) !important;
    box-shadow: 0 6px 25px rgba(0,0,0,0.25) !important;
    color: black !important;
}

/* HEADER TEXT */
h1, h2, h3, h4 {
    color: black !important;
    font-weight: 800 !important;
}

/* SIDEBAR */
section[data-testid="stSidebar"] {
    background: rgba(255,255,255,0.35) !important;
    backdrop-filter: blur(16px);
}
section[data-testid="stSidebar"] * {
    color: black !important;
}

/* INPUT FIELDS */
input, select, textarea, .stNumberInput input {
    color: black !important;
    border-radius: 12px !important;
    background: rgba(255,255,255,0.65) !important;
}

/* BUTTONS */
.stButton button {
    background: linear-gradient(90deg, #7c3aed, #3b82f6);
    color: white !important;
    border-radius: 12px;
    padding: 10px 22px;
    font-weight: 600;
    border: none;
}
.stButton button:hover {
    transform: scale(1.04);
    opacity: .92;
}

/* TABLE */
.dataframe {
    background: rgba(255,255,255,0.85) !important;
    color: black !important;
    border-radius: 12px;
}

/* GENERAL TEXT */
label, span, p, div {
    color: black !important;
}

</style>
"""
st.markdown(page_bg_css, unsafe_allow_html=True)



# ===================================================
#  DATABASE INIT
# ===================================================

DB_NAME = "inventory.db"

def get_conn():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT,
        created_at TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sku TEXT,
        name TEXT,
        cost REAL,
        price REAL,
        stock INTEGER DEFAULT 0,
        warehouse_stock INTEGER DEFAULT 0,
        created_at TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER,
        qty INTEGER,
        cost_each REAL,
        price_each REAL,
        total REAL,
        profit REAL,
        sold_by INTEGER,
        sold_at TEXT
    )""")

    c.execute("""
    CREATE TABLE IF NOT EXISTS store_status (
        id INTEGER PRIMARY KEY,
        status TEXT
    )""")

    c.execute("SELECT COUNT(*) FROM store_status")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO store_status VALUES (1, 'open')")

    conn.commit()
    return conn

conn = init_db()



# ===================================================
#  STORE STATUS
# ===================================================
def get_store_status():
    c = conn.cursor()
    c.execute("SELECT status FROM store_status WHERE id=1")
    return c.fetchone()[0]

def set_store_status(status):
    c = conn.cursor()
    c.execute("UPDATE store_status SET status=? WHERE id=1", (status,))
    conn.commit()



# ===================================================
#  AUTH
# ===================================================
def hash_password(p):
    return hashlib.sha256(p.encode()).hexdigest()

def create_default_user():
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username='boss'")
    if not c.fetchone():
        c.execute("INSERT INTO users VALUES (NULL,?,?,?,?)",
                  ("boss", hash_password("boss123"), "boss",
                   datetime.datetime.utcnow().isoformat()))
        conn.commit()
create_default_user()

def login_user(u, p):
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username=? AND password=?", (u, hash_password(p)))
    return c.fetchone()



# ===================================================
#  PRODUCT FUNCTIONS
# ===================================================
def add_product(sku, name, cost, price):
    c = conn.cursor()
    c.execute("""
        INSERT INTO products (sku, name, cost, price, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (sku, name, cost, price, datetime.datetime.utcnow().isoformat()))
    conn.commit()

def update_product(pid, sku, name, cost, price):
    c = conn.cursor()
    c.execute("UPDATE products SET sku=?, name=?, cost=?, price=? WHERE id=?",
              (sku, name, cost, price, pid))
    conn.commit()

def delete_product(pid):
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM sales WHERE product_id=?", (pid,))
    used = c.fetchone()[0]

    if used > 0:
        return False, "Produk tidak bisa dihapus karena sudah ada transaksi."

    c.execute("DELETE FROM products WHERE id=?", (pid,))
    conn.commit()
    return True, "Produk berhasil dihapus."

def add_warehouse_stock(pid, qty):
    c = conn.cursor()
    c.execute("UPDATE products SET warehouse_stock = warehouse_stock + ? WHERE id=?",
              (qty, pid))
    conn.commit()

def move_stock_from_warehouse(pid, qty):
    c = conn.cursor()
    c.execute("SELECT warehouse_stock FROM products WHERE id=?", (pid,))
    ws = c.fetchone()[0]

    if qty > ws:
        return False, "Stok gudang tidak cukup."

    c.execute("""
        UPDATE products
        SET warehouse_stock = warehouse_stock - ?, stock = stock + ?
        WHERE id=?
    """, (qty, qty, pid))
    conn.commit()
    return True, "Stok dipindah ke stok harian."

def get_products():
    return pd.read_sql_query("SELECT * FROM products ORDER BY name", conn)



# ===================================================
#  SALES
# ===================================================
def record_sale(pid, qty, uid):
    c = conn.cursor()
    c.execute("SELECT stock, cost, price FROM products WHERE id=?", (pid,))
    stock, cost, price = c.fetchone()

    if qty > stock:
        return False, "Stok tidak cukup."

    total = qty * price
    profit = (price - cost) * qty

    c.execute("""
        INSERT INTO sales (product_id, qty, cost_each, price_each,
                           total, profit, sold_by, sold_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (pid, qty, cost, price, total, profit, uid,
          datetime.datetime.utcnow().isoformat()))

    c.execute("UPDATE products SET stock = stock - ? WHERE id=?", (qty, pid))
    conn.commit()

    return True, "Penjualan berhasil."

def get_sales(role):
    if role == "boss":
        query = """
            SELECT s.id, p.name, s.qty, s.price_each, s.total, s.profit, s.sold_at
            FROM sales s
            JOIN products p ON s.product_id=p.id
        """
    else:
        query = """
            SELECT s.id, p.name, s.qty, s.price_each, s.total, s.sold_at
            FROM sales s
            JOIN products p ON s.product_id=p.id
        """

    return pd.read_sql_query(query, conn)

def get_today_sales_total_by_user(uid):
    today = datetime.date.today().isoformat()

    c = conn.cursor()
    c.execute("""
        SELECT COALESCE(SUM(total),0)
        FROM sales WHERE sold_by=? AND date(sold_at)=?
    """, (uid, today))
    return c.fetchone()[0]

def get_today_summary():
    today = datetime.date.today().isoformat()

    c = conn.cursor()
    c.execute("""
        SELECT COALESCE(SUM(total),0), COALESCE(SUM(profit),0)
        FROM sales WHERE date(sold_at)=?
    """, (today,))
    return c.fetchone()



# ===================================================
#  SESSION
# ===================================================
if "user" not in st.session_state:
    st.session_state.user = None



# ===================================================
#  LOGIN PAGE
# ===================================================
if st.session_state.user is None:

    st.title("Login Sistem Inventory")

    u = st.text_input("Username")
    p = st.text_input("Password", type="password")

    if st.button("Login"):
        user = login_user(u, p)

        if user:
            status = get_store_status()

            if user[3] == "karyawan" and status == "closed":
                st.error("Toko sedang TUTUP. Karyawan tidak dapat login.")
            else:
                st.session_state.user = {
                    "id": user[0],
                    "username": user[1],
                    "role": user[3]
                }
                st.rerun()

        else:
            st.error("Username atau password salah.")



# ===================================================
#  MAIN APPLICATION
# ===================================================
else:

    user = st.session_state.user
    role = user["role"]

    st.sidebar.write(f"Login sebagai: {user['username']} ({role})")

    if role == "karyawan":
        total_today = get_today_sales_total_by_user(user["id"])
        st.sidebar.metric("Total Penjualan Hari Ini", f"Rp {int(total_today):,}")

    if st.sidebar.button("Logout"):
        st.session_state.user = None
        st.rerun()



    # Menu
    if role == "boss":
        menu = st.sidebar.selectbox("Menu", [
            "Home", "Stok Gudang", "Produk & Stok",
            "Penjualan", "Histori Penjualan", "Manajemen User"
        ])
    else:
        menu = st.sidebar.selectbox("Menu", [
            "Home", "Penjualan", "Histori Penjualan"
        ])

    # --- HOME ---
    if menu == "Home":
        st.header("Dashboard Utama — Galaxy Glass Theme")

        status = get_store_status()
        st.subheader(f"Status Toko: {status.upper()}")

        if role == "boss":
            col1, col2 = st.columns(2)

            if col1.button("Toko Buka"):
                set_store_status("open")
                st.success("Toko dibuka.")
                st.rerun()

            if col2.button("Toko Tutup"):
                set_store_status("closed")
                st.warning("Toko ditutup.")
                st.rerun()



    # --- STOK GUDANG ---
    elif menu == "Stok Gudang":

        st.header("Stok Gudang")

        st.subheader("Tambah Produk Baru")
        with st.form("add_prod"):
            sku = st.text_input("SKU Produk")
            name = st.text_input("Nama Produk")
            cost = st.number_input("Harga Modal")
            price = st.number_input("Harga Jual")

            if st.form_submit_button("Tambah Produk"):
                add_product(sku, name, cost, price)
                st.success("Produk ditambahkan.")
                st.rerun()

        df = get_products()

        if not df.empty:
            prod_map = df.set_index("id")["name"].to_dict()
            pid = st.selectbox("Pilih Produk", prod_map.keys(),
                               format_func=lambda x: prod_map[x])

            row = df[df["id"] == pid].iloc[0]

            st.subheader("Edit Produk")
            with st.form("edit_prod"):
                sku = st.text_input("SKU", value=row["sku"])
                name = st.text_input("Nama", value=row["name"])
                cost = st.number_input("Modal", value=float(row["cost"]))
                price = st.number_input("Jual", value=float(row["price"]))

                if st.form_submit_button("Update"):
                    update_product(pid, sku, name, cost, price)
                    st.success("Produk diperbarui.")
                    st.rerun()

            st.subheader("Tambah Stok Gudang")
            qty = st.number_input("Jumlah Tambah", min_value=1)

            if st.button("Tambah Stok"):
                add_warehouse_stock(pid, qty)
                st.success("Stok gudang ditambah.")
                st.rerun()

            st.subheader("Hapus Produk")
            if st.button("Hapus Produk"):
                ok, msg = delete_product(pid)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

            st.subheader("Daftar Stok Gudang")
            st.dataframe(df[["sku", "name", "warehouse_stock"]])



    # --- PRODUK & STOK (HARlAN) ---
    elif menu == "Produk & Stok":

        st.header("Ambil Stok Harian")

        df = get_products()

        if df.empty:
            st.info("Belum ada produk.")
        else:
            prod_map = df.set_index("id")["name"].to_dict()
            pid = st.selectbox("Produk", prod_map.keys(),
                               format_func=lambda x: prod_map[x])

            qty = st.number_input("Jumlah Ambil", min_value=1)

            if st.button("Ambil"):
                ok, msg = move_stock_from_warehouse(pid, qty)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

            st.subheader("Stok Harian")
            st.dataframe(df[["sku", "name", "stock"]])



    # --- PENJUALAN ---
    elif menu == "Penjualan":

        st.header("Penjualan Produk")

        df = get_products()

        if not df.empty:
            mapping = {f"{r['name']} (stok: {r['stock']})": r["id"]
                       for _, r in df.iterrows()}

            pilih = st.selectbox("Produk", mapping.keys())
            qty = st.number_input("Qty", min_value=1)

            if st.button("Simpan Penjualan"):
                pid = mapping[pilih]
                ok, msg = record_sale(pid, qty, user["id"])
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)



    # --- HISTORI ---
    elif menu == "Histori Penjualan":

        st.header("Histori Penjualan")

        if role == "boss":
            total, profit = get_today_summary()

            col1, col2 = st.columns(2)
            col1.metric("Total Hari Ini", f"Rp {int(total):,}")
            col2.metric("P&L Hari Ini", f"Rp {int(profit):,}")

            st.markdown("---")

        df = get_sales(role)

        if df.empty:
            st.info("Belum ada transaksi.")
        else:
            st.dataframe(df)



    # --- USER MANAGEMENT ---
    elif menu == "Manajemen User":

        st.header("Manajemen User")

        with st.form("add_user"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            r = st.selectbox("Role", ["boss", "karyawan"])

            if st.form_submit_button("Tambah User"):
                try:
                    c = conn.cursor()
                    c.execute("""
                        INSERT INTO users VALUES (NULL,?,?,?,?)
                    """, (username, hash_password(password), r,
                          datetime.datetime.utcnow().isoformat()))
                    conn.commit()
                    st.success("User berhasil ditambahkan.")
                    st.rerun()
                except:
                    st.error("Username sudah dipakai.")

        df = pd.read_sql_query("SELECT id, username, role FROM users", conn)
        st.dataframe(df)

        if not df.empty:
            mapping = df.set_index("id")["username"].to_dict()
            uid = st.selectbox("Hapus User", mapping.keys(),
                               format_func=lambda x: mapping[x])

            if st.button("Hapus User"):
                if uid == user["id"]:
                    st.error("Tidak dapat menghapus akun sendiri.")
                else:
                    c = conn.cursor()
                    c.execute("DELETE FROM users WHERE id=?", (uid,))
                    conn.commit()
                    st.success("User dihapus.")
                    st.rerun()
