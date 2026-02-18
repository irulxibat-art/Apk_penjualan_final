import streamlit as st
import requests

# =====================================
# CONFIG
# =====================================
BASE_URL = st.secrets["BASE_URL"]


def api_call(params):
    try:
        response = requests.get(BASE_URL, params=params, timeout=10)
        return response.json()
    except Exception as e:
        return {"status": "error", "message": "API tidak dapat diakses"}


# =====================================
# AUTH
# =====================================
def login(username, password):
    return api_call({
        "action": "login",
        "username": username,
        "password": password
    })


# =====================================
# DATA FUNCTIONS
# =====================================
def get_summary_today(username):
    return api_call({
        "action": "summary_today",
        "username": username
    })


def get_weekly(username):
    return api_call({
        "action": "history_weekly",
        "username": username
    })


def jual_produk(username, product_id, qty):
    return api_call({
        "action": "jual",
        "username": username,
        "product_id": product_id,
        "qty": qty
    })


def add_product(username, product_id, name, harga_modal, harga_jual, stok_awal):
    return api_call({
        "action": "add_product",
        "username": username,
        "product_id": product_id,
        "name": name,
        "harga_modal": harga_modal,
        "harga_jual": harga_jual,
        "stok_awal": stok_awal
    })


def ambil_stok_harian(username):
    return api_call({
        "action": "ambil_stok_harian",
        "username": username
    })


# =====================================
# UI
# =====================================
st.set_page_config(page_title="Aplikasi Penjualan", layout="centered")
st.title("📊 Aplikasi Penjualan")

# =====================================
# LOGIN PAGE
# =====================================
if "user" not in st.session_state:

    st.subheader("Login")

    username = st.text_input("Username")
    password = st.text_input("Password", type="password")

    if st.button("Login"):
        result = login(username, password)

        if result.get("status") == "success":
            st.session_state.user = result
            st.success("Login berhasil")
            st.rerun()
        else:
            st.error(result.get("message", "Login gagal"))

# =====================================
# DASHBOARD
# =====================================
else:

    user = st.session_state.user
    username = user["username"]
    role = user["role"]

    st.sidebar.write(f"Login sebagai: **{username}** ({role})")

    if st.sidebar.button("Logout"):
        del st.session_state.user
        st.rerun()

    # =====================================
    # TRANSAKSI
    # =====================================
    st.subheader("Transaksi")

    product_id = st.text_input("Product ID")
    qty = st.number_input("Qty", min_value=1, step=1)

    if st.button("Jual Produk"):
        result = jual_produk(username, product_id, qty)

        if result.get("status") == "success":
            st.success("Transaksi berhasil")
        else:
            st.error(result.get("message", "Gagal transaksi"))

    st.divider()

    # =====================================
    # SUMMARY TODAY (SEMUA ROLE)
    # =====================================
    st.subheader("Total Penjualan Hari Ini")

    summary = get_summary_today(username)

    if summary.get("status") == "success":
        st.metric("Total Sales", f"Rp {summary['total_sales']:,}")
        st.metric("Total Profit", f"Rp {summary['total_profit']:,}")
        st.metric("Total Transaksi", summary["total_transaksi"])
    else:
        st.error("Gagal mengambil data")

    # =====================================
    # FITUR KHUSUS BOSS
    # =====================================
    if role == "boss":

        st.divider()
        st.subheader("History Weekly")

        weekly = get_weekly(username)

        if weekly.get("status") == "success":
            st.metric("Total Sales Mingguan", f"Rp {weekly['total_sales']:,}")
            st.metric("Total Profit Mingguan", f"Rp {weekly['total_profit']:,}")
            st.metric("Total Transaksi Mingguan", weekly["total_transaksi"])

            if weekly.get("data"):
                st.json(weekly["data"])
        else:
            st.error("Gagal mengambil history")

        # =====================================
        # AMBIL STOK HARIAN
        # =====================================
        st.divider()
        st.subheader("Ambil Stok Harian")

        if st.button("Ambil Stok dari Gudang"):
            result = ambil_stok_harian(username)

            if result.get("status") == "success":
                st.success("Stok harian berhasil diambil")
            else:
                st.error(result.get("message", "Gagal ambil stok"))

        # =====================================
        # TAMBAH PRODUK
        # =====================================
        st.divider()
        st.subheader("Tambah Produk Baru")

        new_id = st.text_input("Product ID Baru")
        new_name = st.text_input("Nama Produk")
        harga_modal = st.number_input("Harga Modal", min_value=0, step=1000)
        harga_jual = st.number_input("Harga Jual", min_value=0, step=1000)
        stok_awal = st.number_input("Stok Awal Gudang", min_value=0, step=1)

        if st.button("Tambah Produk"):
            result = add_product(
                username,
                new_id,
                new_name,
                harga_modal,
                harga_jual,
                stok_awal
            )

            if result.get("status") == "success":
                st.success("Produk berhasil ditambahkan")
            else:
                st.error(result.get("message", "Gagal menambahkan produk"))
