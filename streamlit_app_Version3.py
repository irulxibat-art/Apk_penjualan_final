import streamlit as st
import sqlite3
import pandas as pd
import hashlib
import datetime

st.set_page_config(page_title="Inventory System", layout="wide")

# ===================================================
#  CUSTOM UI – GALAXY GRADIENT (Blue–Purple–Pink)
# ===================================================
page_bg_css = """
<style>
/* Galaxy Background */
.stApp {
    background: radial-gradient(circle at 20% 20%, #a78bfa 0%, #8b5cf6 25%, #3b82f6 60%, #0ea5e9 100%) !important;
    background-attachment: fixed;
}

/* Card */
div[data-testid="stColumn"] > div {
    background: rgba(255, 255, 255, 0.45);
    padding: 20px;
    border-radius: 16px;
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    box-shadow: 0px 6px 25px rgba(0,0,0,0.25);
    color: black !important;
}

/* Header text */
h1, h2, h3, h4 {
    color: black !important;
    font-weight: 800;
}

/* Sidebar */
section[data-testid="stSidebar"] {
    background: rgba(255,255,255,0.30) !important;
    backdrop-filter: blur(16px);
}
section[data-testid="stSidebar"] * {
    color: black !important;
}

/* Inputs */
input, select, textarea, .stNumberInput input {
    border-radius: 10px !important;
    color: black !important;
}

/* Buttons */
.stButton button {
    background: linear-gradient(90deg, #7c3aed, #3b82f6);
    color: white !important;
    border-radius: 12px;
    padding: 8px 20px;
    font-weight: 600;
    border: none;
}
.stButton button:hover {
    transform: scale(1.03);
    opacity: 0.92;
}

/* Metrics */
[data-testid="stMetricValue"], 
[data-testid="stMetricDelta"], 
[data-testid="stMetricLabel"] {
    color: black !important;
}

/* Table */
.dataframe {
    background: white !important;
    color: black !important;
    border-radius: 10px;
}

/* Forms */
form {
    background: rgba(255,255,255,0.40);
    padding: 20px;
    border-radius: 12px;
    color: black !important;
}

/* General text black */
p, label, span, div {
    color: black !important;
}

</style>
"""
st.markdown(page_bg_css, unsafe_allow_html=True)



# ===================================================
#  DATABASE INITIALIZATION
# ===================================================

DB_NAME = "inventory.db"

def get_conn():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_conn()
    c = conn.cursor()

    # USERS
    c.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT,
        created_at TEXT
    )""")

    # PRODUCTS
    c.execute("""
    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sku TEXT UNIQUE,
        name TEXT,
        cost REAL,
        price REAL,
        stock INTEGER DEFAULT 0,
        warehouse_stock INTEGER DEFAULT 0,
        created_at TEXT
    )""")

    # SALES
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

    # STORE STATUS
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
#  STORE STATUS OPERATIONS
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
#  AUTH & USER MANAGEMENT
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
    c.execute("SELECT * FROM users WHERE username=? AND password=?",
              (u, hash_password(p)))
    return c.fetchone()



# ===================================================
#  PRODUCT OPERATIONS
# ===================================================

def add_product(sku, name, cost, price):
    c = conn.cursor()
    c.execute("""
        INSERT INTO products (sku, name, cost, price, stock, warehouse_stock, created_at)
        VALUES (?, ?, ?, ?, 0, 0, ?)
    """, (sku, name, cost, price, datetime.datetime.utcnow().isoformat()))
    conn.commit()

def update_product(product_id, sku, name, cost, price):
    c = conn.cursor()
    c.execute("""
        UPDATE products SET sku=?, name=?, cost=?, price=? WHERE id=?
    """, (sku, name, cost, price, product_id))
    conn.commit()

def delete_product(product_id):
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM sales WHERE product_id=?", (product_id,))
    used = c.fetchone()[0]

    if used > 0:
        return False, "Produk sudah dipakai transaksi"

    c.execute("DELETE FROM products WHERE id=?", (product_id,))
    conn.commit()
    return True, "Produk dihapus"

def add_warehouse_stock(product_id, qty):
    c = conn.cursor()
    c.execute("UPDATE products SET warehouse_stock = warehouse_stock + ? WHERE id=?",
              (qty, product_id))
    conn.commit()

def move_stock_from_warehouse(product_id, qty):
    c = conn.cursor()
    c.execute("SELECT warehouse_stock FROM products WHERE id=?", (product_id,))
    ws = c.fetchone()[0]

    if qty > ws:
        return False, "Stok gudang tidak cukup"

    c.execute("""
        UPDATE products SET warehouse_stock = warehouse_stock - ?, stock = stock + ? WHERE id=?
    """, (qty, qty, product_id))

    conn.commit()
    return True, "Stok dipindah ke stok harian"

def get_products():
    return pd.read_sql_query("SELECT * FROM products ORDER BY name", conn)



# ===================================================
#  SALES OPERATIONS
# ===================================================

def record_sale(product_id, qty, sold_by):
    c = conn.cursor()
    c.execute("SELECT stock, cost, price FROM products WHERE id=?", (product_id,))
    stock, cost, price = c.fetchone()

    if qty > stock:
        return False, "Stok tidak cukup"

    total = qty * price
    profit = (price - cost) * qty

    c.execute("""
        INSERT INTO sales (product_id, qty, cost_each, price_each, total, profit, sold_by, sold_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (product_id, qty, cost, price, total, profit, sold_by,
          datetime.datetime.utcnow().isoformat()))

    c.execute("UPDATE products SET stock = stock - ? WHERE id=?", (qty, product_id))
    conn.commit()

    return True, "Penjualan berhasil"

def get_sales(role):
    if role == "boss":
        q = """SELECT s.id, p.name, s.qty, s.price_each, s.total, s.profit, s.sold_at
               FROM sales s JOIN products p ON s.product_id=p.id"""
    else:
        q = """SELECT s.id, p.name, s.qty, s.price_each, s.total, s.sold_at
               FROM sales s JOIN products p ON s.product_id=p.id"""
    return pd.read_sql_query(q, conn)

def get_today_sales_total_by_user(user_id):
    today = datetime.datetime.utcnow().date().isoformat()

    q = """
        SELECT COALESCE(SUM(total),0)
        FROM sales WHERE sold_by=? AND date(sold_at)=?
    """

    c = conn.cursor()
    c.execute(q, (user_id, today))
    return c.fetchone()[0]

def get_today_summary():
    today = datetime.datetime.utcnow().date().isoformat()

    q = """
        SELECT COALESCE(SUM(total),0), COALESCE(SUM(profit),0)
        FROM sales WHERE date(sold_at)=?
    """

    c = conn.cursor()
    c.execute(q, (today,))
    return c.fetchone()



# ===================================================
#  SESSION HANDLER
# ===================================================
if "user" not in st.session_state:
    st.session_state.user = None



# ===================================================
#  LOGIN SCREEN
# ===================================================
if st.session_state.user is None:

    st.title("Login Sistem")

    u = st.text_input("Username")
    p = st.text_input("Password", type="password")

    if st.button("Login"):

        user = login_user(u, p)

        if user:
            status = get_store_status()

            if user[3] == "karyawan" and status == "closed":
                st.error("Toko sedang tutup. Karyawan tidak bisa login.")
            else:
                st.session_state.user = {
                    "id": user[0],
                    "username": user[1],
                    "role": user[3]
                }
                st.rerun()

        else:
            st.error("Login gagal")



# ===================================================
#  MAIN APPLICATION
# ===================================================
else:

    user = st.session_state.user
    role = user["role"]

    st.sidebar.write(f"Login: {user['username']} ({role})")

    if role == "karyawan":
        total_today = get_today_sales_total_by_user(user["id"])
        st.sidebar.metric("Total Hari Ini", f"Rp {int(total_today):,}")

    if st.sidebar.button("Logout"):
        st.session_state.user = None
        st.rerun()

    # MENU
    if role == "boss":
        menu = st.sidebar.selectbox("Menu", [
            "Home", "Stok Gudang", "Produk & Stok",
            "Penjualan", "Histori Penjualan", "Manajemen User"
        ])
    else:
        menu = st.sidebar.selectbox("Menu", [
            "Home", "Penjualan", "Histori Penjualan"
        ])

    # ========== HOME ==========
    if menu == "Home":

        st.header("Dashboard Galaxy Theme")

        status = get_store_status()
        st.subheader(f"Status Toko: {status.upper()}")

        if role == "boss":
            col1, col2 = st.columns(2)

            if col1.button("Toko Buka"):
                set_store_status("open")
                st.success("Toko berhasil dibuka")
                st.rerun()

            if col2.button("Toko Tutup"):
                set_store_status("closed")
                st.warning("Toko ditutup")
                st.rerun()

    # ========== STOK GUDANG ==========
    elif menu == "Stok Gudang":

        st.header("Stok Gudang")

        st.subheader("Tambah Produk")
        with st.form("add_prod"):
            sku = st.text_input("SKU")
            name = st.text_input("Nama Produk")
            cost = st.number_input("Harga Modal", min_value=0.0)
            price = st.number_input("Harga Jual", min_value=0.0)

            if st.form_submit_button("Tambah Produk"):
                add_product(sku, name, cost, price)
                st.success("Produk ditambahkan")
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
                price = st.number_input("Harga Jual", value=float(row["price"]))

                if st.form_submit_button("Update"):
                    update_product(pid, sku, name, cost, price)
                    st.success("Produk diperbarui")
                    st.rerun()

            st.subheader("Tambah Stok Gudang")
            qty = st.number_input("Jumlah Tambah", min_value=1)
            if st.button("Tambah Stok"):
                add_warehouse_stock(pid, qty)
                st.success("Stok ditambahkan")
                st.rerun()

            st.subheader("Hapus Produk")
            if st.button("Hapus Produk"):
                ok, msg = delete_product(pid)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

            st.subheader("Daftar Produk")
            st.dataframe(df[["sku", "name", "warehouse_stock"]])

    # ========== PRODUK & STOK ==========
    elif menu == "Produk & Stok":

        st.header("Ambil Stok Harian dari Gudang")

        df = get_products()

        if df.empty:
            st.info("Belum ada produk")
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

    # ========== PENJUALAN ==========
    elif menu == "Penjualan":

        st.header("Penjualan Produk")

        df = get_products()

        if not df.empty:
            mapping = {f"{r['name']} ({r['stock']})": r["id"]
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

    # ========== HISTORI PENJUALAN ==========
    elif menu == "Histori Penjualan":

        st.header("Histori Penjualan")

        if role == "boss":
            total_sales, total_profit = get_today_summary()

            col1, col2 = st.columns(2)
            col1.metric("Total Hari Ini",
                        f"Rp {int(total_sales):,}")
            col2.metric("P&L Hari Ini",
                        f"Rp {int(total_profit):,}")

            st.markdown("---")

        df = get_sales(role)

        if df.empty:
            st.info("Belum ada transaksi")
        else:
            st.dataframe(df)

    # ========== USER MANAGEMENT ==========
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
                    st.success("User berhasil dibuat")
                    st.rerun()

                except sqlite3.IntegrityError:
                    st.error("Username sudah digunakan")

        df = pd.read_sql_query("SELECT id, username, role FROM users", conn)
        st.dataframe(df)

        if not df.empty:
            mapping = df.set_index("id")["username"].to_dict()
            uid = st.selectbox("Pilih User", mapping.keys(),
                               format_func=lambda x: mapping[x])

            if st.button("Hapus User"):
                if uid == user["id"]:
                    st.error("Tidak bisa hapus akun sendiri")
                else:
                    c = conn.cursor()
                    c.execute("DELETE FROM users WHERE id=?", (uid,))
                    conn.commit()
                    st.success("User dihapus")
                    st.rerun()
