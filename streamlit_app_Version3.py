import streamlit as st
import sqlite3
import pandas as pd
import hashlib
import datetime

st.set_page_config(page_title="Inventory Gudang", layout="wide")

DB_NAME = "inventory.db"

def get_conn():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT,
        created_at TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sku TEXT UNIQUE,
        name TEXT,
        cost REAL,
        price REAL,
        stock INTEGER DEFAULT 0,
        warehouse_stock INTEGER DEFAULT 0,
        created_at TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS sales (
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
        c.execute("INSERT INTO users (username, password, role, created_at) VALUES (?, ?, ?, ?)",
                  ("boss", hash_password("boss123"), "boss", now))
        conn.commit()
create_default_user()

def login_user(u, p):
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username=? AND password=?",
              (u, hash_password(p)))
    return c.fetchone()

# ================= STOCK FLOW =================
def add_product(sku, name, cost, price):
    c = conn.cursor()
    now = datetime.datetime.utcnow().isoformat()
    c.execute("""
        INSERT INTO products (sku, name, cost, price, stock, warehouse_stock, created_at)
        VALUES (?, ?, ?, ?, 0, 0, ?)
    """, (sku, name, cost, price, now))
    conn.commit()

def add_warehouse_stock(product_id, qty):
    c = conn.cursor()
    c.execute("UPDATE products SET warehouse_stock = warehouse_stock + ? WHERE id=?", (qty, product_id))
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
        return False, "Stok tidak cukup"

    total = price * qty
    profit = (price - cost) * qty
    sold_at = datetime.datetime.utcnow().isoformat()

    c.execute("""INSERT INTO sales
    (product_id, qty, cost_each, price_each, total, profit, sold_by, sold_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
    (product_id, qty, cost, price, total, profit, sold_by, sold_at))

    c.execute("UPDATE products SET stock = stock - ? WHERE id=?", (qty, product_id))
    conn.commit()
    return True, "Penjualan berhasil"

# ================= UI =================
if "user" not in st.session_state:
    st.session_state.user = None

if st.session_state.user is None:
    st.title("Login")
    u = st.text_input("Username")
    p = st.text_input("Password", type="password")
    if st.button("Login"):
        user = login_user(u, p)
        if user:
            st.session_state.user = {"id": user[0], "username": user[1], "role": user[3]}
            st.rerun()
        else:
            st.error("Login gagal")

else:
    user = st.session_state.user
    role = user["role"]

    st.sidebar.write(f"Login: {user['username']} ({role})")

    if role == "boss":
        menu = st.sidebar.selectbox("Menu", ["Home", "Stok Gudang", "Produk & Stok", "Penjualan"])
    else:
        menu = st.sidebar.selectbox("Menu", ["Home", "Penjualan"])

    if menu == "Home":
        st.header("Dashboard")

    elif menu == "Stok Gudang":
        st.subheader("Input Stok Gudang")

        df = get_products()
        if df.empty:
            st.info("Belum ada produk")
        else:
            st.dataframe(df[["sku", "name", "warehouse_stock"]])

            prod_map = df.set_index("id")["name"].to_dict()
            pid = st.selectbox("Pilih Produk", list(prod_map.keys()), format_func=lambda x: prod_map[x])
            qty = st.number_input("Jumlah tambah ke gudang", min_value=1, step=1)

            if st.button("Tambah Stok Gudang"):
                add_warehouse_stock(pid, qty)
                st.success("Stok gudang ditambahkan")
                st.rerun()

    elif menu == "Produk & Stok":
        st.subheader("Ambil Stok untuk Penjualan Harian")

        df = get_products()
        if df.empty:
            st.info("Belum ada produk")
        else:
            st.dataframe(df[["sku", "name", "stock", "warehouse_stock"]])

            prod_map = df.set_index("id")["name"].to_dict()
            pid = st.selectbox("Pilih Produk", list(prod_map.keys()), format_func=lambda x: prod_map[x])
            qty = st.number_input("Jumlah ambil dari gudang", min_value=1, step=1)

            if st.button("Ambil ke Stok Harian"):
                ok, msg = move_stock_from_warehouse(pid, qty)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

    elif menu == "Penjualan":
        st.subheader("Input Penjualan")

        df = get_products()
        if df.empty:
            st.info("Belum ada produk")
        else:
            mapping = {f"{r['name']} (stok:{r['stock']})": r['id'] for _, r in df.iterrows()}
            pilih = st.selectbox("Pilih Produk", list(mapping.keys()))
            qty = st.number_input("Qty", min_value=1, step=1)

            if st.button("Simpan"):
                pid = mapping[pilih]
                ok, msg = record_sale(pid, qty, user["id"])
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
