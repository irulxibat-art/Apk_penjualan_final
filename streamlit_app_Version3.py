import streamlit as st
import sqlite3
import pandas as pd
import hashlib
import datetime

st.set_page_config(page_title="Inventory System", layout="wide")

# ================= UI (NO BOX BACKGROUND) =================
st.markdown("""
<style>
.stApp {
    background: radial-gradient(circle at 20% 20%, #a78bfa 0%, #8b5cf6 30%, #3b82f6 65%, #0ea5e9 100%);
}

/* SIDEBAR */
section[data-testid="stSidebar"] {
    background: rgba(255,255,255,0.95);
}
section[data-testid="stSidebar"] * {
    color: black;
}

/* INPUT */
input, textarea, select {
    background: white !important;
    color: black !important;
    border-radius: 8px !important;
}

/* BUTTON */
.stButton button {
    background: linear-gradient(90deg, #7c3aed, #3b82f6);
    color: white;
    border-radius: 10px;
    padding: 8px 18px;
    font-weight: 600;
    border: none;
}

/* TEXT */
h1, h2, h3, h4, p, span, label {
    color: black;
    font-weight: 700;
}
</style>
""", unsafe_allow_html=True)

# ================= DATABASE =================
DB = "inventory.db"

def conn():
    return sqlite3.connect(DB, check_same_thread=False)

db = conn()
c = db.cursor()

c.execute("""CREATE TABLE IF NOT EXISTS users(
id INTEGER PRIMARY KEY AUTOINCREMENT,
username TEXT UNIQUE,
password TEXT,
role TEXT,
created_at TEXT)""")

c.execute("""CREATE TABLE IF NOT EXISTS products(
id INTEGER PRIMARY KEY AUTOINCREMENT,
sku TEXT,
name TEXT,
cost REAL,
price REAL,
stock INTEGER DEFAULT 0,
warehouse_stock INTEGER DEFAULT 0,
created_at TEXT)""")

c.execute("""CREATE TABLE IF NOT EXISTS sales(
id INTEGER PRIMARY KEY AUTOINCREMENT,
product_id INTEGER,
qty INTEGER,
cost_each REAL,
price_each REAL,
total REAL,
profit REAL,
sold_by INTEGER,
sold_at TEXT)""")

c.execute("""CREATE TABLE IF NOT EXISTS store_status(
id INTEGER PRIMARY KEY,
status TEXT)""")

c.execute("SELECT COUNT(*) FROM store_status")
if c.fetchone()[0] == 0:
    c.execute("INSERT INTO store_status VALUES (1,'open')")
db.commit()

# ================= AUTH =================
def hash_pw(p): return hashlib.sha256(p.encode()).hexdigest()

c.execute("SELECT * FROM users WHERE username='boss'")
if not c.fetchone():
    c.execute("INSERT INTO users VALUES(NULL,?,?,?,?)",
              ("boss",hash_pw("boss123"),"boss",
               datetime.datetime.utcnow().isoformat()))
    db.commit()

def login(u,p):
    c.execute("SELECT * FROM users WHERE username=? AND password=?",(u,hash_pw(p)))
    return c.fetchone()

# ================= STORE =================
def store_status():
    c.execute("SELECT status FROM store_status WHERE id=1")
    return c.fetchone()[0]

def set_store(s):
    c.execute("UPDATE store_status SET status=? WHERE id=1",(s,))
    db.commit()

# ================= PRODUCT =================
def products():
    return pd.read_sql("SELECT * FROM products ORDER BY name",db)

def add_product(sku,name,cost,price):
    c.execute("""INSERT INTO products
    (sku,name,cost,price,created_at)
    VALUES(?,?,?,?,?)""",
    (sku,name,cost,price,datetime.datetime.utcnow().isoformat()))
    db.commit()

def add_warehouse_stock(pid,qty):
    c.execute("UPDATE products SET warehouse_stock=warehouse_stock+? WHERE id=?",(qty,pid))
    db.commit()

def move_stock(pid,qty):
    c.execute("SELECT warehouse_stock FROM products WHERE id=?",(pid,))
    ws=c.fetchone()[0]
    if qty>ws:
        return False,"Stok gudang tidak cukup"
    c.execute("""UPDATE products
    SET warehouse_stock=warehouse_stock-?, stock=stock+?
    WHERE id=?""",(qty,qty,pid))
    db.commit()
    return True,"Stok dipindah"

# ================= SALES (STOCK REDUCED FOR BOSS & KARYAWAN) =================
def sell(pid,qty,uid):
    c.execute("SELECT stock,cost,price FROM products WHERE id=?",(pid,))
    stock,cost,price=c.fetchone()
    if qty>stock:
        return False,"Stok tidak cukup"
    total=qty*price
    profit=(price-cost)*qty
    c.execute("""INSERT INTO sales
    (product_id,qty,cost_each,price_each,total,profit,sold_by,sold_at)
    VALUES(?,?,?,?,?,?,?,?)""",
    (pid,qty,cost,price,total,profit,uid,
     datetime.datetime.utcnow().isoformat()))
    c.execute("UPDATE products SET stock=stock-? WHERE id=?",(qty,pid))
    db.commit()
    return True,"Penjualan berhasil"

# ================= SESSION =================
if "user" not in st.session_state:
    st.session_state.user=None

# ================= LOGIN =================
if st.session_state.user is None:
    st.title("Login Sistem")
    u=st.text_input("Username")
    p=st.text_input("Password",type="password")
    if st.button("Login"):
        user=login(u,p)
        if user:
            if user[3]=="karyawan" and store_status()=="closed":
                st.error("Toko sedang tutup")
            else:
                st.session_state.user={"id":user[0],"username":user[1],"role":user[3]}
                st.rerun()
        else:
            st.error("Login gagal")

# ================= MAIN =================
else:
    user=st.session_state.user
    role=user["role"]

    st.sidebar.write(f"{user['username']} ({role})")
    if st.sidebar.button("Logout"):
        st.session_state.user=None
        st.rerun()

    menu=st.sidebar.selectbox("Menu",
        ["Home","Stok Gudang","Produk & Stok","Penjualan","Histori Penjualan","Manajemen User"]
        if role=="boss"
        else ["Home","Penjualan","Histori Penjualan"]
    )

    if menu=="Home":
        st.header("Dashboard")
        st.subheader(f"Status Toko: {store_status().upper()}")
        if role=="boss":
            c1,c2=st.columns(2)
            if c1.button("Toko Buka"):
                set_store("open"); st.rerun()
            if c2.button("Toko Tutup"):
                set_store("closed"); st.rerun()

    elif menu=="Stok Gudang":
        st.header("Stok Gudang")
        with st.form("add"):
            sku=st.text_input("SKU")
            name=st.text_input("Nama")
            cost=st.number_input("Modal")
            price=st.number_input("Harga")
            if st.form_submit_button("Tambah"):
                add_product(sku,name,cost,price); st.rerun()
        st.dataframe(products()[["sku","name","warehouse_stock"]])

    elif menu=="Produk & Stok":
        st.header("Stok Harian")
        df=products()
        pid=st.selectbox("Produk",df["id"],format_func=lambda x:df[df.id==x]["name"].iloc[0])
        qty=st.number_input("Ambil",min_value=1)
        if st.button("Ambil"):
            ok,msg=move_stock(pid,qty)
            st.success(msg) if ok else st.error(msg)
        st.dataframe(df[["sku","name","stock"]])

    elif menu=="Penjualan":
        st.header("Penjualan")
        df=products()
        pid=st.selectbox("Produk",df["id"],format_func=lambda x:df[df.id==x]["name"].iloc[0])
        qty=st.number_input("Qty",min_value=1)
        if st.button("Simpan"):
            ok,msg=sell(pid,qty,user["id"])
            st.success(msg) if ok else st.error(msg)

    elif menu=="Histori Penjualan":
        st.header("Histori")
        st.dataframe(pd.read_sql("SELECT * FROM sales",db))

    elif menu=="Manajemen User":
        st.header("Manajemen User")
        with st.form("user"):
            u=st.text_input("Username")
            p=st.text_input("Password",type="password")
            r=st.selectbox("Role",["boss","karyawan"])
            if st.form_submit_button("Tambah"):
                try:
                    c.execute("INSERT INTO users VALUES(NULL,?,?,?,?)",
                              (u,hash_pw(p),r,
                               datetime.datetime.utcnow().isoformat()))
                    db.commit(); st.rerun()
                except:
                    st.error("Username sudah ada")
