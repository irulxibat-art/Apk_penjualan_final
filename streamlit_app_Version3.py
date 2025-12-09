import streamlit as st
import sqlite3
import pandas as pd
import hashlib
import datetime

st.set_page_config(page_title="Inventory & Sales App", layout="wide")

DB_NAME = "inventory.db"

# ================= DATABASE =================
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
        stock INTEGER,
        warehouse_stock INTEGER,
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

# Jika migrate dari versi lama tanpa kolom warehouse_stock
try:
    conn.execute("ALTER TABLE products ADD COLUMN warehouse_stock INTEGER DEFAULT 0")
    conn.commit()
except Exception:
    # sudah ada atau gagal -> aman diabaikan
    pass

# ================= AUTH =================
def hash_password(password):
    return hashlib.sha256(password.encode()).hexdigest()

def create_default_user():
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username='boss'")
    if not c.fetchone():
        now = datetime.datetime.utcnow().isoformat()
        c.execute("INSERT INTO users (username, password, role, created_at) VALUES (?, ?, ?, ?)",
                  ("boss", hash_password("boss123"), "boss", now))
        conn.commit()
create_default_user()

def login_user(username, password):
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE username=? AND password=?",
              (username, hash_password(password)))
    return c.fetchone()

def create_user(username, password, role):
    try:
        now = datetime.datetime.utcnow().isoformat()
        c = conn.cursor()
        c.execute("INSERT INTO users (username, password, role, created_at) VALUES (?, ?, ?, ?)",
                  (username, hash_password(password), role, now))
        conn.commit()
        return True, "User berhasil dibuat"
    except sqlite3.IntegrityError:
        return False, "Username sudah digunakan"

def delete_user(user_id, current_user_id):
    if user_id == current_user_id:
        return False, "Tidak bisa hapus akun sendiri"
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id=?", (user_id,))
    conn.commit()
    return True, "User berhasil dihapus"

# ================= PRODUCT =================
def add_product(sku, name, cost, price, stock, warehouse_stock):
    c = conn.cursor()
    now = datetime.datetime.utcnow().isoformat()
    c.execute("""
        INSERT INTO products (sku, name, cost, price, stock, warehouse_stock, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (sku, name, cost, price, stock, warehouse_stock, now))
    conn.commit()

def update_product(product_id, sku, name, cost, price, stock, warehouse_stock):
    c = conn.cursor()
    c.execute("""
        UPDATE products
        SET sku=?, name=?, cost=?, price=?, stock=?, warehouse_stock=?
        WHERE id=?
    """, (sku, name, cost, price, stock, warehouse_stock, product_id))
    conn.commit()

def delete_product(product_id):
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM sales WHERE product_id=?", (product_id,))
    used = c.fetchone()[0]
    if used > 0:
        return False, "Produk sudah pernah dipakai di penjualan, tidak bisa dihapus"
    c.execute("DELETE FROM products WHERE id=?", (product_id,))
    conn.commit()
    return True, "Produk berhasil dihapus"

def move_stock_from_warehouse(product_id, qty):
    c = conn.cursor()
    c.execute("SELECT warehouse_stock FROM products WHERE id=?", (product_id,))
    row = c.fetchone()
    if not row:
        return False, "Produk tidak ditemukan"
    gudang = row[0] or 0
    if qty > gudang:
        return False, "Stok gudang tidak cukup"
    c.execute("""
        UPDATE products
        SET 
            warehouse_stock = warehouse_stock - ?,
            stock = stock + ?
        WHERE id=?
    """, (qty, qty, product_id))
    conn.commit()
    return True, "Stok berhasil dipindahkan dari gudang"

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
    stock = stock or 0
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
    return True, "Transaksi berhasil"

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
    username = st.text_input("Username")
    password = st.text_input("Password", type="password")
    if st.button("Login"):
        user = login_user(username, password)
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

    # Sidebar menu (boss punya akses Stok Gudang)
    if role == "boss":
        menu = st.sidebar.selectbox(
            "Menu",
            ["Home", "Produk & Stok", "Stok Gudang", "Penjualan", "Histori Penjualan", "Manajemen User"]
        )
    else:
        menu = st.sidebar.selectbox("Menu", ["Home", "Penjualan", "Histori Penjualan"])

    if menu == "Home":
        st.header("Dashboard")

    elif menu == "Produk & Stok":
        if role != "boss":
            st.error("Akses ditolak")
            st.stop()

        st.subheader("Tambah Produk")
        with st.form("add_prod"):
            sku = st.text_input("SKU")
            name = st.text_input("Nama Produk")
            cost = st.number_input("Harga Modal", min_value=0.0)
            price = st.number_input("Harga Jual", min_value=0.0)
            stock = st.number_input("Stok Harian", min_value=0, step=1)
            warehouse_stock = st.number_input("Stok Gudang (inisialisasi)", min_value=0, step=1)
            if st.form_submit_button("Tambah Produk"):
                add_product(sku, name, cost, price, stock, warehouse_stock)
                st.success("Produk berhasil ditambahkan")
                st.rerun()

        st.markdown("---")
        st.subheader("Edit Produk")

        df = get_products()
        if df.empty:
            st.info("Belum ada produk")
        else:
            prod_map = df.set_index("id")["name"].to_dict()
            pilih_id = st.selectbox(
                "Pilih produk",
                options=list(prod_map.keys()),
                format_func=lambda x: f"{x} - {prod_map[x]}"
            )
            row = df[df["id"] == pilih_id].iloc[0]
            with st.form("edit_prod"):
                sku = st.text_input("SKU", value=row["sku"])
                name = st.text_input("Nama Produk", value=row["name"])
                cost = st.number_input("Harga Modal", min_value=0.0, value=float(row["cost"]))
                price = st.number_input("Harga Jual", min_value=0.0, value=float(row["price"]))
                stock = st.number_input("Stok Harian", min_value=0, step=1, value=int(row["stock"] or 0))
                warehouse_stock = st.number_input("Stok Gudang", min_value=0, step=1, value=int(row["warehouse_stock"] or 0))
                if st.form_submit_button("Update Produk"):
                    update_product(pilih_id, sku, name, cost, price, stock, warehouse_stock)
                    st.success("Produk berhasil diupdate")
                    st.rerun()

        st.markdown("---")
        st.subheader("Hapus Produk")
        df = get_products()
        if df.empty:
            st.info("Belum ada produk")
        else:
            del_map = df.set_index("id")["name"].to_dict()
            del_id = st.selectbox(
                "Pilih produk untuk dihapus",
                options=list(del_map.keys()),
                format_func=lambda x: f"{x} - {del_map[x]}",
                key="hapus_produk"
            )
            if st.button("Hapus Produk"):
                ok, msg = delete_product(del_id)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

        st.markdown("---")
        st.subheader("Daftar Produk")
        st.dataframe(get_products())

    elif menu == "Stok Gudang":
        if role != "boss":
            st.error("Akses ditolak")
            st.stop()

        st.subheader("Manajemen Stok Gudang")
        df = get_products()
        if df.empty:
            st.info("Belum ada produk")
        else:
            st.dataframe(df[["sku", "name", "warehouse_stock"]])

            st.markdown("### Tambah Stok Gudang")
            gudang_map = df.set_index("id")["name"].to_dict()
            gid = st.selectbox(
                "Pilih Produk",
                options=list(gudang_map.keys()),
                format_func=lambda x: f"{x} - {gudang_map[x]}",
                key="gudang_add"
            )
            qty_add = st.number_input("Jumlah tambah ke gudang", min_value=1, step=1, key="gudang_add_qty")
            if st.button("Tambah ke Gudang"):
                c = conn.cursor()
                c.execute("UPDATE products SET warehouse_stock = warehouse_stock + ? WHERE id=?", (qty_add, gid))
                conn.commit()
                st.success("Stok gudang berhasil ditambah")
                st.rerun()

        st.markdown("---")
        st.subheader("Transfer Gudang → Etalase (Pindahkan ke Stok Harian)")
        df = get_products()
        if df.empty:
            st.info("Belum ada produk")
        else:
            gudang_map = df.set_index("id")["name"].to_dict()
            tid = st.selectbox(
                "Pilih Produk (Transfer)",
                options=list(gudang_map.keys()),
                format_func=lambda x: f"{x} - {gudang_map[x]}",
                key="transfer_gudang"
            )
            qty_move = st.number_input("Jumlah pindahkan ke display", min_value=1, step=1, key="gudang_move_qty")
            if st.button("Transfer ke Etalase"):
                ok, msg = move_stock_from_warehouse(tid, qty_move)
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
            pilih = st.selectbox("Pilih produk", list(mapping.keys()))
            qty = st.number_input("Qty", min_value=1, step=1)
            if st.button("Simpan"):
                pid = mapping[pilih]
                ok, msg = record_sale(pid, qty, user["id"])
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

    elif menu == "Histori Penjualan":
        st.subheader("Histori Penjualan")
        df = get_sales(role)
        if df.empty:
            st.info("Belum ada data")
        else:
            df["sold_at"] = pd.to_datetime(df["sold_at"])
            df["tanggal"] = df["sold_at"].dt.date
            st.dataframe(df)
            if role == "boss":
                daily = df.groupby("tanggal").agg(
                    total_penjualan=("total", "sum"),
                    total_profit=("profit", "sum")
                ).reset_index()
                st.markdown("### P&L Harian (Boss)")
                st.dataframe(daily)
            else:
                daily = df.groupby("tanggal").agg(
                    total_penjualan=("total", "sum")
                ).reset_index()
                st.markdown("### Total Penjualan Harian")
                st.dataframe(daily)

    elif menu == "Manajemen User":
        if role != "boss":
            st.error("Tidak diizinkan")
            st.stop()

        st.subheader("Manajemen User")
        with st.form("add_user"):
            username = st.text_input("Username")
            password = st.text_input("Password", type="password")
            role_user = st.selectbox("Role", ["boss", "karyawan"])
            if st.form_submit_button("Tambah User"):
                ok, msg = create_user(username, password, role_user)
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)

        st.markdown("---")
        user_df = pd.read_sql_query("SELECT id, username, role FROM users", conn)
        st.dataframe(user_df)
        if not user_df.empty:
            user_map = user_df.set_index("id")["username"].to_dict()
            pilih_user = st.selectbox(
                "Pilih user untuk dihapus",
                options=list(user_map.keys()),
                format_func=lambda x: f"{x} - {user_map[x]}"
            )
            if st.button("Hapus User"):
                ok, msg = delete_user(int(pilih_user), user["id"])
                if ok:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)
