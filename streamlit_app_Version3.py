import streamlit as st
import sqlite3
import pandas as pd
import hashlib
import datetime

st.set_page_config(page_title="Inventory System", layout="wide")

DB_NAME = "inventory.db"

# ================= DATABASE =================
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

    conn.commit()
    return conn

conn = init_db()

# ================= AUTH =================
def hash_password(p):
    return hashlib.sha256(p.encode()).hexdigest()

def create_default_user():
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username='boss'")
    if not c.fetchone():
        now = datetime.datetime.utcnow().isoformat()
        c.execute(
            "INSERT INTO users VALUES (NULL,?,?,?,?)",
            ("boss", hash_password("boss123"), "boss", now)
        )
        conn.commit()
create_default_user()

def login_user(u, p):
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username=? AND password=?",
              (u, hash_password(p)))
    return c.fetchone()

def create_user(username, password, role):
    try:
        now = datetime.datetime.utcnow().isoformat()
        c = conn.cursor()
        c.execute("INSERT INTO users VALUES (NULL,?,?,?,?)",
                  (username, hash_password(password), role, now))
        conn.commit()
        return True, "User berhasil dibuat"
    except sqlite3.IntegrityError:
        return False, "Username sudah dipakai"

def delete_user(user_id, current_user_id):
    if user_id == current_user_id:
        return False, "Tidak bisa hapus akun sendiri"
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    return True, "User berhasil dihapus"

# ================= PRODUCT =================
def add_product(sku, name, cost, price):
    c = conn.cursor()
    now = datetime.datetime.utcnow().isoformat()
    c.execute("""
        INSERT INTO products (sku, name, cost, price, stock, warehouse_stock, created_at)
        VALUES (?, ?, ?, ?, 0, 0, ?)
    """, (sku, name, cost, price, now))
    conn.commit()

def update_product(product_id, sku, name, cost, price):
    c = conn.cursor()
    c.execute("""
        UPDATE products
        SET sku=?, name=?, cost=?, price=?
        WHERE id=?
    """, (sku, name, cost, price, product_id))
    conn.commit()

def delete_product(product_id):
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM sales WHERE product_id=?", (product_id,))
    used = c.fetchone()[0]
    if used > 0:
        return False, "Produk pernah dipakai transaksi - tidak bisa dihapus"
    c.execute("DELETE FROM products WHERE id=?", (product_id,))
    conn.commit()
    return True, "Produk berhasil dihapus"

def add_warehouse_stock(product_id, qty):
    c = conn.cursor()
    c.execute("""
        UPDATE products
        SET warehouse_stock = warehouse_stock + ?
        WHERE id=?
    """, (qty, product_id))
    conn.commit()

def move_stock_from_warehouse(product_id, qty):
    c = conn.cursor()
    c.execute("SELECT warehouse_stock FROM products WHERE id=?", (product_id,))
    row = c.fetchone()

    if not row:
        return False, "Produk tidak ditemukan"

    if qty > row[0]:
        return False, "Stok gudang tidak cukup"

    c.execute("""
        UPDATE products
        SET warehouse_stock = warehouse_stock - ?,
            stock = stock + ?
        WHERE id=?
    """, (qty, qty, product_id))
    conn.commit()
    return True, "Stok dipindahkan ke stok jual"

def get_products():
    return pd.read_sql_query("SELECT * FROM products ORDER BY name", conn)

# ================= SALES =================
def record_sale(product_id, qty, sold_by):
    c = conn.cursor()
    c.execute("SELECT stock, cost, price FROM products WHERE id=?", (product_id,))
    row = c.fetchone()

    if not row:
        return False, "Produk tidak ditemukan"

    stock, cost, price = row
    if qty > stock:
        return False, "Stok harian tidak cukup"

    total = price * qty
    profit = (price - cost) * qty
    sold_at = datetime.datetime.utcnow().isoformat()

    c.execute("""
        INSERT INTO sales
        (product_id, qty, cost_each, price_each, total, profit, sold_by, sold_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (product_id, qty, cost, price, total, profit, sold_by, sold_at))

    c.execute("UPDATE products SET stock = stock - ? WHERE id=?", (qty, product_id))
    conn.commit()
    return True, "Penjualan berhasil"

def get_sales(role="boss"):
    if role == "boss":
        query = """
        SELECT s.id, p.name, s.qty, s.price_each, s.total, s.profit, s.sold_at, u.username
        FROM sales s
        JOIN products p ON s.product_id = p.id
        JOIN users u ON s.sold_by = u.id
        ORDER BY s.sold_at DESC
        """
    else:
        query = """
        SELECT s.id, p.name, s.qty, s.price_each, s.total, s.sold_at, u.username
        FROM sales s
        JOIN products p ON s.product_id = p.id
        JOIN users u ON s.sold_by = u.id
        ORDER BY s.sold_at DESC
        """
    return pd.read_sql_query(query, conn)

# ================= SESSION =================
if "user" not in st.session_state:
    st.session_state.user = None

# ================= UI =================
if st.session_state.user is None:
    st.title("Login")
    u = st.text_input("Username")
    p = st.text_input("Password", type="password")

    if st.button("Login"):
        user = login_user(u, p)
        if user:
            st.session_state.user = {
                "id": user[0],
                "username": user[1],
                "role": user[3]
            }
            st.rerun()
        else:
            st.error("Login gagal")

else:
    user = st.session_state.user
    role = user["role"]

    st.sidebar.write(f"Login: {user['username']} ({role})")

    if st.sidebar.button("Logout"):
        st.session_state.user = None
        st.rerun()

    if role == "boss":
        menu = st.sidebar.selectbox(
            "Menu",
            ["Home", "Stok Gudang", "Produk & Stok", "Penjualan", "Histori Penjualan", "Manajemen User"]
        )
    else:
        menu = st.sidebar.selectbox("Menu", ["Home", "Penjualan", "Histori Penjualan"])

    if menu == "Home":
        st.header("Dashboard")

    # ================= STOK GUDANG =================
    elif menu == "Stok Gudang":
        st.header("Manajemen Stok Gudang")

        df = get_products()
        if df.empty:
            st.info("Belum ada produk")
        else:
            st.dataframe(df[["sku", "name", "warehouse_stock"]])

            prod_map = df.set_index("id")["name"].to_dict()
            pid = st.selectbox("Pilih Produk", prod_map.keys(), format_func=lambda x: prod_map[x])
            qty = st.number_input("Tambah stok dari supplier", min_value=1, step=1)

            if st.button("Tambah Stok Gudang"):
                add_warehouse_stock(pid, qty)
                st.success("Stok gudang ditambahkan")
                st.rerun()

    # ================= PRODUK & STOK =================
    elif menu == "Produk & Stok":
        st.header("Produk & Stok Harian")

        st.subheader("Tambah Produk Baru")
        with st.form("add_product"):
            sku = st.text_input("SKU")
            name = st.text_input("Nama Produk")
            cost = st.number_input("Harga Modal", min_value=0.0)
            price = st.number_input("Harga Jual", min_value=0.0)
            if st.form_submit_button("Simpan Produk"):
                add_product(sku, name, cost, price)
                st.success("Produk berhasil ditambahkan")
                st.rerun()

        df = get_products()
        if not df.empty:
            st.markdown("---")
            st.subheader("Edit Produk")
            prod_map = df.set_index("id")["name"].to_dict()
            pid = st.selectbox("Pilih Produk", prod_map.keys(), format_func=lambda x: prod_map[x])

            row = df[df["id"] == pid].iloc[0]

            with st.form("edit_form"):
                sku = st.text_input("SKU", value=row["sku"])
                name = st.text_input("Nama", value=row["name"])
                cost = st.number_input("Harga Modal", min_value=0.0, value=float(row["cost"]))
                price = st.number_input("Harga Jual", min_value=0.0, value=float(row["price"]))
                if st.form_submit_button("Update"):
                    update_product(pid, sku, name, cost, price)
                    st.success("Produk diupdate")
                    st.rerun()

            st.markdown("---")
            st.subheader("Ambil Stok dari Gudang ke Etalase")
            qty = st.number_input("Jumlah ambil ke stok harian", min_value=1, step=1)
            if st.button("Ambil Stok"):
                ok, msg = move_stock_from_warehouse(pid, qty)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

            st.markdown("---")
            st.subheader("Hapus Produk")
            if st.button("Hapus Produk Ini"):
                ok, msg = delete_product(pid)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

            st.markdown("---")
            st.subheader("Daftar Produk")
            st.dataframe(df[["sku", "name", "stock", "warehouse_stock"]])

    # ================= PENJUALAN =================
    elif menu == "Penjualan":
        st.header("Input Penjualan")

        df = get_products()
        if df.empty:
            st.info("Belum ada produk")
        else:
            mapping = {f"{r['name']} (stok:{r['stock']})": r['id'] for _, r in df.iterrows()}
            pilih = st.selectbox("Pilih Produk", mapping.keys())
            qty = st.number_input("Qty jual", min_value=1, step=1)

            if st.button("Simpan"):
                pid = mapping[pilih]
                ok, msg = record_sale(pid, qty, user["id"])
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

    # ================= HISTORI =================
    elif menu == "Histori Penjualan":
        st.header("Histori Penjualan")

        df = get_sales(role)
        if df.empty:
            st.info("Belum ada transaksi")
        else:
            st.dataframe(df)

    # ================= MANAJEMEN USER =================
    elif menu == "Manajemen User":
        st.header("Manajemen User")

        with st.form("add_user"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            r = st.selectbox("Role", ["boss", "karyawan"])
            if st.form_submit_button("Tambah User"):
                ok, msg = create_user(username, password, r)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

        user_df = pd.read_sql_query("SELECT id, username, role FROM users", conn)
        st.dataframe(user_df)

        if not user_df.empty:
            user_map = user_df.set_index("id")["username"].to_dict()
            uid = st.selectbox("Pilih user untuk dihapus", user_map.keys(), format_func=lambda x: user_map[x])
            if st.button("Hapus User"):
                ok, msg = delete_user(uid, user["id"])
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
