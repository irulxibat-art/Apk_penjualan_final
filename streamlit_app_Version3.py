import streamlit as st
import sqlite3
import pandas as pd
import hashlib
import datetime
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4

# =============================
# PAGE CONFIG
# =============================
st.set_page_config(page_title="Inventory System", layout="wide")

# =============================
# SESSION STATE
# =============================
if "user" not in st.session_state:
    st.session_state.user = None

if "edit_product_id" not in st.session_state:
    st.session_state.edit_product_id = None

# =============================
# DATABASE
# =============================
DB_NAME = "inventory.db"

def get_conn():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

conn = get_conn()

def init_db():
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
        sku TEXT UNIQUE,
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
        c.execute("INSERT INTO store_status VALUES (1,'open')")

    conn.commit()

init_db()

# =============================
# AUTH
# =============================
def hash_password(p):
    return hashlib.sha256(p.encode()).hexdigest()

def create_default_user():
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username='boss'")
    if not c.fetchone():
        c.execute(
            "INSERT INTO users VALUES (NULL,?,?,?,?)",
            ("boss", hash_password("boss123"), "boss",
             datetime.datetime.utcnow().isoformat())
        )
        conn.commit()

create_default_user()

def login_user(u, p):
    c = conn.cursor()
    c.execute(
        "SELECT * FROM users WHERE username=? AND password=?",
        (u, hash_password(p))
    )
    return c.fetchone()

# =============================
# STORE STATUS
# =============================
def get_store_status():
    c = conn.cursor()
    c.execute("SELECT status FROM store_status WHERE id=1")
    return c.fetchone()[0]

def set_store_status(status):
    conn.cursor().execute(
        "UPDATE store_status SET status=? WHERE id=1", (status,))
    conn.commit()

# =============================
# PRODUCT FUNCTIONS
# =============================
def add_product(sku, name, cost, price):
    conn.cursor().execute("""
        INSERT INTO products
        (sku,name,cost,price,stock,warehouse_stock,created_at)
        VALUES (?,?,?,?,0,0,?)
    """, (sku, name, cost, price,
          datetime.datetime.utcnow().isoformat()))
    conn.commit()

def update_product(pid, sku, name, cost, price, role):
    c = conn.cursor()
    if role != "boss":
        c.execute("""
            UPDATE products SET sku=?, name=? WHERE id=?
        """, (sku, name, pid))
    else:
        c.execute("""
            UPDATE products
            SET sku=?, name=?, cost=?, price=?
            WHERE id=?
        """, (sku, name, cost, price, pid))
    conn.commit()

def delete_product(pid):
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM sales WHERE product_id=?", (pid,))
    if c.fetchone()[0] > 0:
        return False, "Produk sudah pernah dijual"
    c.execute("DELETE FROM products WHERE id=?", (pid,))
    conn.commit()
    return True, "Produk dihapus"

def add_warehouse_stock(pid, qty):
    conn.cursor().execute("""
        UPDATE products
        SET warehouse_stock = warehouse_stock + ?
        WHERE id=?
    """, (qty, pid))
    conn.commit()

def move_stock(pid, qty):
    c = conn.cursor()
    c.execute("SELECT warehouse_stock FROM products WHERE id=?", (pid,))
    if qty > c.fetchone()[0]:
        return False, "Stok gudang tidak cukup"
    c.execute("""
        UPDATE products
        SET warehouse_stock = warehouse_stock - ?,
            stock = stock + ?
        WHERE id=?
    """, (qty, qty, pid))
    conn.commit()
    return True, "Stok dipindahkan"

def get_products():
    return pd.read_sql("SELECT * FROM products ORDER BY name", conn)

# =============================
# SALES
# =============================
def record_sale(pid, qty, user_id):
    c = conn.cursor()
    c.execute("SELECT stock,cost,price FROM products WHERE id=?", (pid,))
    stock, cost, price = c.fetchone()

    if qty > stock:
        return False, "Stok tidak cukup"

    total = qty * price
    profit = (price - cost) * qty

    c.execute("""
        INSERT INTO sales
        (product_id,qty,cost_each,price_each,total,profit,sold_by,sold_at)
        VALUES (?,?,?,?,?,?,?,?)
    """, (pid, qty, cost, price, total, profit,
          user_id, datetime.datetime.utcnow().isoformat()))

    c.execute("UPDATE products SET stock = stock - ? WHERE id=?",
              (qty, pid))
    conn.commit()
    return True, "Penjualan berhasil"

def get_sales(role):
    if role == "boss":
        q = """SELECT p.name, s.qty, s.total, s.profit, s.sold_at
               FROM sales s JOIN products p ON s.product_id=p.id"""
    else:
        q = """SELECT p.name, s.qty, s.total, s.sold_at
               FROM sales s JOIN products p ON s.product_id=p.id"""
    return pd.read_sql(q, conn)

def get_today_summary():
    today = datetime.datetime.utcnow().date().isoformat()
    c = conn.cursor()
    c.execute("""
        SELECT COALESCE(SUM(total),0), COALESCE(SUM(profit),0)
        FROM sales WHERE date(sold_at)=?
    """, (today,))
    return c.fetchone()

# =============================
# LOGIN
# =============================
if st.session_state.user is None:
    st.title("Login Sistem")
    u = st.text_input("Username")
    p = st.text_input("Password", type="password")

    if st.button("Login"):
        user = login_user(u, p)
        if user:
            if user[3] == "karyawan" and get_store_status() == "closed":
                st.error("Toko sedang tutup")
            else:
                st.session_state.user = {
                    "id": user[0],
                    "username": user[1],
                    "role": user[3]
                }
                st.rerun()
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
        st.rerun()

    menu = st.sidebar.selectbox(
        "Menu",
        ["Home", "Stok Gudang", "Produk & Stok",
         "Penjualan", "Histori Penjualan", "Manajemen User"]
        if role == "boss"
        else ["Home", "Penjualan", "Histori Penjualan"]
    )

    # =============================
    # PENJUALAN (IMPROVED UX)
    # =============================
    if menu == "Penjualan":
        st.header("Penjualan Produk")

        df = get_products()
        if df.empty:
            st.info("Belum ada produk")
        else:
            mapping = {
                f"{r['name']} (Sisa: {r['stock']})": r['id']
                for _, r in df.iterrows()
            }

            pilih = st.selectbox("Pilih Produk", mapping.keys())
            pid = mapping[pilih]
            sisa = int(df[df["id"] == pid]["stock"].values[0])

            if sisa == 0:
                st.warning("Stok produk ini HABIS")

            qty = st.number_input(
                "Qty",
                min_value=1,
                max_value=max(1, sisa),
                disabled=(sisa == 0)
            )

            if st.button("Simpan Penjualan"):
                ok, msg = record_sale(pid, qty, user["id"])
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
