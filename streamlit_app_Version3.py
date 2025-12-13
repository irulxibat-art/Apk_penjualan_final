import streamlit as st
import sqlite3
import pandas as pd
import hashlib
import datetime

st.set_page_config(page_title="Inventory System", layout="wide")

# ================= UI RINGAN =================
st.markdown("""
<style>
.stApp {
    background: radial-gradient(circle at 20% 20%, #a78bfa, #8b5cf6, #3b82f6, #0ea5e9);
}
div[data-testid="stVerticalBlock"] > div,
div[data-testid="stColumn"] > div {
    background: rgba(255,255,255,0.92);
    padding: 16px;
    border-radius: 14px;
    box-shadow: 0 4px 10px rgba(0,0,0,.15);
}
section[data-testid="stSidebar"] {
    background: rgba(255,255,255,0.95);
}
input, textarea, select {
    background: white !important;
    color: black !important;
}
.stButton button {
    background: linear-gradient(90deg,#7c3aed,#3b82f6);
    color: white;
    border-radius: 10px;
    padding: 8px 16px;
    font-weight: 600;
}
h1,h2,h3,h4,p,label,span { color:black; font-weight:700; }
</style>
""", unsafe_allow_html=True)

# ================= DATABASE =================
DB = "inventory.db"
def get_conn():
    return sqlite3.connect(DB, check_same_thread=False)

conn = get_conn()
c = conn.cursor()

c.execute("""CREATE TABLE IF NOT EXISTS users (
id INTEGER PRIMARY KEY AUTOINCREMENT,
username TEXT UNIQUE,
password TEXT,
role TEXT,
created_at TEXT)""")

c.execute("""CREATE TABLE IF NOT EXISTS products (
id INTEGER PRIMARY KEY AUTOINCREMENT,
sku TEXT,
name TEXT,
cost REAL,
price REAL,
stock INTEGER DEFAULT 0,
warehouse_stock INTEGER DEFAULT 0,
created_at TEXT)""")

c.execute("""CREATE TABLE IF NOT EXISTS sales (
id INTEGER PRIMARY KEY AUTOINCREMENT,
product_id INTEGER,
qty INTEGER,
cost_each REAL,
price_each REAL,
total REAL,
profit REAL,
sold_by INTEGER,
sold_at TEXT)""")

c.execute("""CREATE TABLE IF NOT EXISTS store_status (
id INTEGER PRIMARY KEY,
status TEXT)""")

c.execute("SELECT COUNT(*) FROM store_status")
if c.fetchone()[0] == 0:
    c.execute("INSERT INTO store_status VALUES (1,'open')")

conn.commit()

# ================= AUTH =================
def hash_pw(p): 
    return hashlib.sha256(p.encode()).hexdigest()

c.execute("SELECT * FROM users WHERE username='boss'")
if not c.fetchone():
    c.execute("INSERT INTO users VALUES (NULL,?,?,?,?)",
              ("boss", hash_pw("boss123"), "boss",
               datetime.datetime.utcnow().isoformat()))
    conn.commit()

def login(u, p):
    c.execute("SELECT * FROM users WHERE username=? AND password=?",
              (u, hash_pw(p)))
    return c.fetchone()

# ================= STORE =================
def store_status():
    c.execute("SELECT status FROM store_status WHERE id=1")
    return c.fetchone()[0]

def set_store(s):
    c.execute("UPDATE store_status SET status=? WHERE id=1", (s,))
    conn.commit()

# ================= PRODUCT =================
def get_products():
    return pd.read_sql("SELECT * FROM products ORDER BY name", conn)

def add_product(sku, name, cost, price):
    c.execute("""INSERT INTO products
    (sku,name,cost,price,created_at)
    VALUES (?,?,?,?,?)""",
    (sku,name,cost,price,datetime.datetime.utcnow().isoformat()))
    conn.commit()

def update_product(pid, sku, name, cost, price):
    c.execute("""UPDATE products
    SET sku=?, name=?, cost=?, price=?
    WHERE id=?""",
    (sku,name,cost,price,pid))
    conn.commit()

def delete_product(pid):
    c.execute("SELECT COUNT(*) FROM sales WHERE product_id=?", (pid,))
    if c.fetchone()[0] > 0:
        return False, "Produk sudah pernah terjual"
    c.execute("DELETE FROM products WHERE id=?", (pid,))
    conn.commit()
    return True, "Produk berhasil dihapus"

def add_warehouse_stock(pid, qty):
    c.execute("UPDATE products SET warehouse_stock=warehouse_stock+? WHERE id=?",
              (qty,pid))
    conn.commit()

def move_stock(pid, qty):
    c.execute("SELECT warehouse_stock FROM products WHERE id=?", (pid,))
    ws = c.fetchone()[0]
    if qty > ws:
        return False, "Stok gudang tidak cukup"
    c.execute("""UPDATE products
    SET warehouse_stock=warehouse_stock-?, stock=stock+?
    WHERE id=?""",
    (qty,qty,pid))
    conn.commit()
    return True, "Stok dipindahkan"

# ================= SALES =================
def record_sale(pid, qty, uid):
    c.execute("SELECT stock,cost,price FROM products WHERE id=?", (pid,))
    stock,cost,price = c.fetchone()
    if qty > stock:
        return False, "Stok tidak cukup"
    total = qty * price
    profit = (price-cost) * qty
    c.execute("""INSERT INTO sales
    (product_id,qty,cost_each,price_each,total,profit,sold_by,sold_at)
    VALUES (?,?,?,?,?,?,?,?)""",
    (pid,qty,cost,price,total,profit,uid,
     datetime.datetime.utcnow().isoformat()))
    c.execute("UPDATE products SET stock=stock-? WHERE id=?", (qty,pid))
    conn.commit()
    return True, "Penjualan berhasil"

# ================= SESSION =================
if "user" not in st.session_state:
    st.session_state.user = None
if "selected_product" not in st.session_state:
    st.session_state.selected_product = None

# ================= LOGIN =================
if st.session_state.user is None:
    st.title("Login Sistem")
    u = st.text_input("Username")
    p = st.text_input("Password", type="password")
    if st.button("Login"):
        user = login(u,p)
        if user:
            if user[3]=="karyawan" and store_status()=="closed":
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

# ================= MAIN =================
else:
    user = st.session_state.user
    role = user["role"]

    st.sidebar.write(f"{user['username']} ({role})")
    if st.sidebar.button("Logout"):
        st.session_state.user=None
        st.rerun()

    menu = st.sidebar.selectbox(
        "Menu",
        ["Home","Stok Gudang","Produk & Stok","Penjualan","Histori Penjualan","Manajemen User"]
        if role=="boss"
        else ["Home","Penjualan","Histori Penjualan"]
    )

    # ---------- HOME ----------
    if menu=="Home":
        st.header("Dashboard")
        st.subheader(f"Status Toko: {store_status().upper()}")
        if role=="boss":
            col1,col2 = st.columns(2)
            if col1.button("Toko Buka"):
                set_store("open"); st.rerun()
            if col2.button("Toko Tutup"):
                set_store("closed"); st.rerun()

    # ---------- STOK GUDANG ----------
    elif menu=="Stok Gudang":
        st.header("Stok Gudang")

        st.subheader("Tambah Produk")
        with st.form("add_prod"):
            sku = st.text_input("SKU")
            name = st.text_input("Nama Produk")
            cost = st.number_input("Harga Modal")
            price = st.number_input("Harga Jual")
            if st.form_submit_button("Tambah"):
                add_product(sku,name,cost,price)
                st.success("Produk ditambahkan")
                st.rerun()

        df = get_products()
        if not df.empty:
            prod_map = df.set_index("id")["name"].to_dict()
            pid = st.selectbox("Pilih Produk", prod_map.keys(),
                               format_func=lambda x: prod_map[x])
            row = df[df.id==pid].iloc[0]

            st.subheader("Edit Produk")
            with st.form("edit_prod"):
                sku = st.text_input("SKU", value=row["sku"])
                name = st.text_input("Nama", value=row["name"])
                cost = st.number_input("Modal", value=float(row["cost"]))
                price = st.number_input("Harga", value=float(row["price"]))
                if st.form_submit_button("Update"):
                    update_product(pid,sku,name,cost,price)
                    st.success("Produk diperbarui")
                    st.rerun()

            st.subheader("Tambah Stok Gudang")
            qty = st.number_input("Jumlah Tambah", min_value=1)
            if st.button("Tambah Stok"):
                add_warehouse_stock(pid,qty)
                st.success("Stok ditambahkan")
                st.rerun()

            st.subheader("Hapus Produk")
            if st.button("Hapus Produk"):
                ok,msg = delete_product(pid)
                st.success(msg) if ok else st.error(msg)
                if ok: st.rerun()

            st.dataframe(df[["sku","name","warehouse_stock"]])

    # ---------- PRODUK & STOK ----------
    elif menu=="Produk & Stok":
        st.header("Ambil Stok Harian dari Gudang")
        df = get_products()
        pid = st.selectbox("Produk", df["id"],
                           format_func=lambda x: df[df.id==x]["name"].iloc[0])
        qty = st.number_input("Jumlah Ambil", min_value=1)
        if st.button("Ambil Stok"):
            ok,msg = move_stock(pid,qty)
            st.success(msg) if ok else st.error(msg)
            if ok: st.rerun()
        st.dataframe(df[["sku","name","stock","warehouse_stock"]])

    # ---------- PENJUALAN ----------
    elif menu=="Penjualan":
        st.header("Penjualan")
        df = get_products()
        cols = st.columns(3)
        for i,row in df.iterrows():
            with cols[i%3]:
                if st.button(f"{row['name']}\nStok: {row['stock']}",
                             key=f"p{row['id']}"):
                    st.session_state.selected_product = row["id"]

        if st.session_state.selected_product:
            prod = df[df.id==st.session_state.selected_product].iloc[0]
            qty = st.number_input("Qty", min_value=1)
            if st.button("Simpan Penjualan"):
                ok,msg = record_sale(prod["id"],qty,user["id"])
                st.success(msg) if ok else st.error(msg)
                if ok:
                    st.session_state.selected_product=None
                    st.rerun()

    # ---------- HISTORI ----------
    elif menu=="Histori Penjualan":
        st.header("Histori Penjualan")
        if role=="boss":
            c.execute("SELECT SUM(total),SUM(profit) FROM sales WHERE date(sold_at)=date('now')")
            t,p = c.fetchone()
            st.metric("Total Hari Ini", f"Rp {int(t or 0):,}")
            st.metric("P&L Hari Ini", f"Rp {int(p or 0):,}")
        q = """SELECT s.id,p.name,s.qty,s.total,s.sold_at
               FROM sales s JOIN products p ON s.product_id=p.id"""
        if role=="boss":
            q = q.replace("s.total","s.total,s.profit")
        st.dataframe(pd.read_sql(q, conn))

    # ---------- USER ----------
    elif menu=="Manajemen User":
        st.header("Manajemen User")
        with st.form("user"):
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            r = st.selectbox("Role", ["boss","karyawan"])
            if st.form_submit_button("Tambah"):
                try:
                    c.execute("INSERT INTO users VALUES (NULL,?,?,?,?)",
                              (u,hash_pw(p),r,
                               datetime.datetime.utcnow().isoformat()))
                    conn.commit(); st.rerun()
                except:
                    st.error("Username sudah ada")
        st.dataframe(pd.read_sql("SELECT id,username,role FROM users", conn))
